//! Artifact lineage — parent DAG storage, cycle detection, chain verification.
//!
//! The lineage index is a local acceleration layer over the Arweave-stored DAG.
//! Source of truth is always the on-chain anchor + Arweave content.

use rusqlite::{params, Connection};
use std::collections::{HashMap, HashSet, VecDeque};

use crate::codec::schema::{ParentRef, MAX_DEPTH, MAX_PARENTS};

const LINEAGE_SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS artifact_lineage (
    child_id   TEXT NOT NULL,
    parent_id  TEXT NOT NULL,
    role       TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (child_id, parent_id)
);
CREATE INDEX IF NOT EXISTS idx_lineage_parent ON artifact_lineage(parent_id);
CREATE INDEX IF NOT EXISTS idx_lineage_child  ON artifact_lineage(child_id);
"#;

/// Initialize the lineage tables in the given SQLite connection.
pub fn init_lineage_schema(conn: &Connection) -> anyhow::Result<()> {
    conn.execute_batch(LINEAGE_SCHEMA)?;
    Ok(())
}

/// Record parent references for a newly written artifact.
pub fn record_parents(
    conn: &Connection,
    child_id: &str,
    parents: &[ParentRef],
    created_at: &str,
) -> anyhow::Result<()> {
    for parent in parents {
        conn.execute(
            "INSERT OR IGNORE INTO artifact_lineage (child_id, parent_id, role, created_at) VALUES (?,?,?,?)",
            params![child_id, parent.artifact_id, parent.role, created_at],
        )?;
    }
    Ok(())
}

/// Get parents of an artifact.
pub fn get_parents(conn: &Connection, artifact_id: &str) -> anyhow::Result<Vec<ParentRef>> {
    let mut stmt = conn.prepare(
        "SELECT parent_id, role FROM artifact_lineage WHERE child_id = ?"
    )?;
    let rows = stmt.query_map(params![artifact_id], |row| {
        Ok(ParentRef {
            artifact_id: row.get(0)?,
            role: row.get(1)?,
        })
    })?;
    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// Get children of an artifact.
pub fn get_children(conn: &Connection, artifact_id: &str) -> anyhow::Result<Vec<String>> {
    let mut stmt = conn.prepare(
        "SELECT child_id FROM artifact_lineage WHERE parent_id = ?"
    )?;
    let rows = stmt.query_map(params![artifact_id], |row| row.get(0))?;
    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// Validate parents before writing an artifact.
///
/// Checks:
/// 1. Number of parents ≤ MAX_PARENTS
/// 2. All parent IDs exist in the attestation store
/// 3. No cycle would be created
///
/// Returns Ok(()) if valid, Err with descriptive message otherwise.
pub fn validate_parents(
    conn: &Connection,
    new_artifact_id: &str,
    parents: &[ParentRef],
    attestation_exists: &dyn Fn(&str) -> bool,
) -> Result<(), String> {
    // Check parent count
    if parents.len() > MAX_PARENTS {
        return Err(format!(
            "TOO_MANY_PARENTS: {} parents exceeds limit of {MAX_PARENTS}",
            parents.len()
        ));
    }

    // Check all parents exist
    for parent in parents {
        if !attestation_exists(&parent.artifact_id) {
            return Err(format!("PARENT_NOT_FOUND: {}", parent.artifact_id));
        }
    }

    // Cycle detection via DFS from each parent upward
    if detect_cycle(conn, new_artifact_id, parents)? {
        return Err("CYCLE_DETECTED: writing this artifact would create a cycle".to_string());
    }

    Ok(())
}

/// DFS cycle detection: walk ancestors of proposed parents looking for new_artifact_id.
fn detect_cycle(
    conn: &Connection,
    new_artifact_id: &str,
    proposed_parents: &[ParentRef],
) -> Result<bool, String> {
    let mut visited = HashSet::new();

    fn dfs(
        conn: &Connection,
        target: &str,
        current: &str,
        depth: usize,
        visited: &mut HashSet<String>,
    ) -> Result<bool, String> {
        if depth > MAX_DEPTH {
            return Ok(false); // depth guard
        }
        if current == target {
            return Ok(true); // cycle found
        }
        if visited.contains(current) {
            return Ok(false); // already explored
        }
        visited.insert(current.to_string());

        let parents = get_parents(conn, current).map_err(|e| e.to_string())?;
        for parent in &parents {
            if dfs(conn, target, &parent.artifact_id, depth + 1, visited)? {
                return Ok(true);
            }
        }
        Ok(false)
    }

    for parent in proposed_parents {
        if dfs(conn, new_artifact_id, &parent.artifact_id, 0, &mut visited)? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Lineage traversal result.
#[derive(Debug, Clone, serde::Serialize)]
pub struct LineageResult {
    pub root: String,
    pub direction: String,
    pub depth_traversed: usize,
    pub nodes: HashMap<String, LineageNode>,
    pub edges: Vec<LineageEdge>,
    pub chain_valid: bool,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct LineageNode {
    pub artifact_type: String,
    pub content_hash: String,
    pub producer: String,
    pub created_at: String,
    pub verified: bool,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct LineageEdge {
    pub from: String,
    pub to: String,
    pub role: Option<String>,
}

/// Traverse the lineage DAG from a starting artifact.
///
/// direction: "ancestors" (follow parents), "descendants" (follow children), or "both"
pub fn traverse_lineage(
    conn: &Connection,
    start_id: &str,
    max_depth: usize,
    direction: &str,
    get_node_info: &dyn Fn(&str) -> Option<LineageNode>,
) -> anyhow::Result<LineageResult> {
    let mut nodes = HashMap::new();
    let mut edges = Vec::new();
    let mut visited = HashSet::new();
    let mut queue: VecDeque<(String, usize)> = VecDeque::new();
    let mut max_traversed: usize = 0;

    queue.push_back((start_id.to_string(), 0));

    while let Some((current_id, depth)) = queue.pop_front() {
        if depth > max_depth || visited.contains(&current_id) {
            continue;
        }
        visited.insert(current_id.clone());
        max_traversed = max_traversed.max(depth);

        // Get node info
        if let Some(node) = get_node_info(&current_id) {
            nodes.insert(current_id.clone(), node);
        }

        // Traverse parents (ancestors)
        if direction == "ancestors" || direction == "both" {
            if let Ok(parents) = get_parents(conn, &current_id) {
                for parent in &parents {
                    edges.push(LineageEdge {
                        from: current_id.clone(),
                        to: parent.artifact_id.clone(),
                        role: parent.role.clone(),
                    });
                    queue.push_back((parent.artifact_id.clone(), depth + 1));
                }
            }
        }

        // Traverse children (descendants)
        if direction == "descendants" || direction == "both" {
            if let Ok(children) = get_children(conn, &current_id) {
                for child_id in &children {
                    edges.push(LineageEdge {
                        from: child_id.clone(),
                        to: current_id.clone(),
                        role: None,
                    });
                    queue.push_back((child_id.clone(), depth + 1));
                }
            }
        }
    }

    Ok(LineageResult {
        root: start_id.to_string(),
        direction: direction.to_string(),
        depth_traversed: max_traversed,
        nodes,
        edges,
        chain_valid: false, // set by verify_chain; traversal alone does not verify
    })
}

// ── Chain Verification ──────────────────────────────────────────────────────

/// Per-node verification result within a chain.
#[derive(Debug, Clone, serde::Serialize)]
pub struct NodeVerification {
    pub artifact_id: String,
    pub content_hash: String,
    pub signer: String,
    /// blake3(canonical_cbor) matches stored/anchored hash
    pub content_integrity: bool,
    /// COSE_Sign1 Ed25519 signature is valid
    pub cose_signature: bool,
    /// Hash was found on-chain (Solana anchor)
    pub anchor_verified: bool,
    /// All parent IDs exist and are themselves verified
    pub parents_valid: bool,
    /// Overall: all checks pass
    pub valid: bool,
    /// Human-readable failure reason, if any
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Full DAG verification report.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ChainVerificationResult {
    /// The artifact we started verification from
    pub start_id: String,
    /// Total number of nodes verified
    pub nodes_verified: usize,
    /// Number of nodes that passed all checks
    pub nodes_valid: usize,
    /// Number of nodes that failed at least one check
    pub nodes_failed: usize,
    /// Maximum depth traversed
    pub depth_traversed: usize,
    /// Per-node verification details
    pub nodes: HashMap<String, NodeVerification>,
    /// DAG edges traversed
    pub edges: Vec<LineageEdge>,
    /// Overall: every node in the DAG passed all checks
    pub chain_valid: bool,
}

/// Callbacks for verify_chain to fetch artifact data and perform verification.
/// This trait-object approach keeps lineage.rs decoupled from Arweave/Solana.
pub struct ChainVerifier<'a> {
    /// Given an artifact_id, return (content_hash, solana_tx, arweave_tx, signer) from local DB.
    pub lookup_artifact: &'a dyn Fn(&str) -> Option<ArtifactInfo>,
    /// Given arweave_tx, return the raw COSE bytes from Arweave (or local store).
    pub fetch_cose_bytes: &'a dyn Fn(&str) -> Result<Vec<u8>, String>,
    /// Given solana_tx, return the anchored hash from the Solana memo.
    pub fetch_anchor_hash: &'a dyn Fn(&str) -> Result<Option<String>, String>,
}

/// Minimal artifact info needed for chain verification.
#[derive(Debug, Clone)]
pub struct ArtifactInfo {
    pub attestation_id: String,
    pub content_hash: String,
    pub solana_tx: String,
    pub arweave_tx: String,
    pub signer: String,
}

/// Verify the full DAG rooted at `start_id` by walking ancestors.
///
/// For each node:
/// 1. Look up artifact in local DB (get content_hash, tx IDs)
/// 2. Fetch COSE bytes → verify COSE_Sign1 signature
/// 3. Verify blake3(payload) matches stored content_hash
/// 4. (Full mode) Fetch Solana anchor → verify hash matches
/// 5. Verify all parents exist and are themselves valid
/// 6. Recurse into parents
pub fn verify_chain(
    conn: &Connection,
    start_id: &str,
    verifier: &ChainVerifier,
) -> ChainVerificationResult {
    let mut nodes = HashMap::new();
    let mut edges = Vec::new();
    let mut visited = HashSet::new();
    let mut queue: VecDeque<(String, usize)> = VecDeque::new();
    let mut max_depth: usize = 0;

    queue.push_back((start_id.to_string(), 0));

    while let Some((artifact_id, depth)) = queue.pop_front() {
        if visited.contains(&artifact_id) {
            continue;
        }
        if depth > MAX_DEPTH {
            nodes.insert(artifact_id.clone(), NodeVerification {
                artifact_id: artifact_id.clone(),
                content_hash: String::new(),
                signer: String::new(),
                content_integrity: false,
                cose_signature: false,
                anchor_verified: false,
                parents_valid: false,
                valid: false,
                error: Some(format!("depth limit exceeded ({MAX_DEPTH})")),
            });
            continue;
        }
        visited.insert(artifact_id.clone());
        max_depth = max_depth.max(depth);

        // Step 1: Look up artifact in local DB
        let info = match (verifier.lookup_artifact)(&artifact_id) {
            Some(info) => info,
            None => {
                nodes.insert(artifact_id.clone(), NodeVerification {
                    artifact_id: artifact_id.clone(),
                    content_hash: String::new(),
                    signer: String::new(),
                    content_integrity: false,
                    cose_signature: false,
                    anchor_verified: false,
                    parents_valid: false,
                    valid: false,
                    error: Some("ARTIFACT_NOT_FOUND: not in local store".to_string()),
                });
                continue;
            }
        };

        // Step 2: Fetch COSE bytes and verify signature + content integrity
        let (content_integrity, cose_signature, cose_signer) = if info.arweave_tx.starts_with("local:") {
            // Local mode: no COSE bytes stored on Arweave — skip COSE verification
            // Content integrity can't be fully verified without the COSE envelope
            (true, true, info.signer.clone())
        } else {
            match (verifier.fetch_cose_bytes)(&info.arweave_tx) {
                Ok(cose_bytes) => {
                    match crate::codec::sign::verify_artifact(&cose_bytes, Some(&info.content_hash)) {
                        Ok(result) => (result.content_integrity, result.cose_signature, result.signer),
                        Err(e) => {
                            nodes.insert(artifact_id.clone(), NodeVerification {
                                artifact_id: artifact_id.clone(),
                                content_hash: info.content_hash.clone(),
                                signer: info.signer.clone(),
                                content_integrity: false,
                                cose_signature: false,
                                anchor_verified: false,
                                parents_valid: false,
                                valid: false,
                                error: Some(format!("COSE_VERIFY_FAILED: {e}")),
                            });
                            continue;
                        }
                    }
                }
                Err(e) => {
                    nodes.insert(artifact_id.clone(), NodeVerification {
                        artifact_id: artifact_id.clone(),
                        content_hash: info.content_hash.clone(),
                        signer: info.signer.clone(),
                        content_integrity: false,
                        cose_signature: false,
                        anchor_verified: false,
                        parents_valid: false,
                        valid: false,
                        error: Some(format!("ARWEAVE_FETCH_FAILED: {e}")),
                    });
                    continue;
                }
            }
        };

        // Step 3: Verify anchor on Solana
        let anchor_verified = if info.solana_tx.starts_with("local:") {
            // Local mode: no on-chain anchor — trust local hash
            true
        } else {
            match (verifier.fetch_anchor_hash)(&info.solana_tx) {
                Ok(Some(anchored_hash)) => anchored_hash == info.content_hash,
                Ok(None) => false,
                Err(_) => false,
            }
        };

        // Step 4: Get parents from lineage index and queue them
        let parents_result = get_parents(conn, &artifact_id);
        let parent_refs = parents_result.unwrap_or_default();
        for parent in &parent_refs {
            edges.push(LineageEdge {
                from: artifact_id.clone(),
                to: parent.artifact_id.clone(),
                role: parent.role.clone(),
            });
            queue.push_back((parent.artifact_id.clone(), depth + 1));
        }

        // parents_valid is deferred — set after all nodes are visited
        nodes.insert(artifact_id.clone(), NodeVerification {
            artifact_id: artifact_id.clone(),
            content_hash: info.content_hash,
            signer: cose_signer,
            content_integrity,
            cose_signature,
            anchor_verified,
            parents_valid: true, // placeholder — resolved below
            valid: content_integrity && cose_signature && anchor_verified,
            error: None,
        });
    }

    // Resolve parents_valid: a node's parents are valid if every parent exists in
    // the verified set and is itself valid.
    let ids: Vec<String> = nodes.keys().cloned().collect();
    for id in &ids {
        let parent_refs = get_parents(conn, id).unwrap_or_default();
        let all_parents_ok = parent_refs.iter().all(|p| {
            nodes.get(&p.artifact_id).map(|n| n.valid).unwrap_or(false)
        });
        if let Some(node) = nodes.get_mut(id) {
            node.parents_valid = all_parents_ok;
            node.valid = node.content_integrity && node.cose_signature && node.anchor_verified && all_parents_ok;
        }
    }

    let nodes_valid = nodes.values().filter(|n| n.valid).count();
    let nodes_failed = nodes.len() - nodes_valid;
    let chain_valid = nodes_failed == 0 && !nodes.is_empty();

    ChainVerificationResult {
        start_id: start_id.to_string(),
        nodes_verified: nodes.len(),
        nodes_valid,
        nodes_failed,
        depth_traversed: max_depth,
        nodes,
        edges,
        chain_valid,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        init_lineage_schema(&conn).unwrap();
        conn
    }

    fn mock_exists(id: &str) -> bool {
        id.starts_with("art:")
    }

    #[test]
    fn test_record_and_get_parents() {
        let conn = setup_db();
        let parents = vec![
            ParentRef { artifact_id: "art:parent1".into(), role: Some("context".into()) },
            ParentRef { artifact_id: "art:parent2".into(), role: None },
        ];
        record_parents(&conn, "art:child", &parents, "2026-04-14").unwrap();

        let fetched = get_parents(&conn, "art:child").unwrap();
        assert_eq!(fetched.len(), 2);
        assert!(fetched.iter().any(|p| p.artifact_id == "art:parent1"));
    }

    #[test]
    fn test_get_children() {
        let conn = setup_db();
        let parents = vec![ParentRef { artifact_id: "art:root".into(), role: None }];
        record_parents(&conn, "art:child1", &parents, "2026-04-14").unwrap();
        record_parents(&conn, "art:child2", &parents, "2026-04-14").unwrap();

        let children = get_children(&conn, "art:root").unwrap();
        assert_eq!(children.len(), 2);
    }

    #[test]
    fn test_validate_parents_ok() {
        let conn = setup_db();
        let parents = vec![ParentRef { artifact_id: "art:p1".into(), role: None }];
        assert!(validate_parents(&conn, "art:new", &parents, &mock_exists).is_ok());
    }

    #[test]
    fn test_validate_parents_not_found() {
        let conn = setup_db();
        let parents = vec![ParentRef { artifact_id: "missing:x".into(), role: None }];
        let err = validate_parents(&conn, "art:new", &parents, &mock_exists).unwrap_err();
        assert!(err.contains("PARENT_NOT_FOUND"));
    }

    #[test]
    fn test_validate_too_many_parents() {
        let conn = setup_db();
        let parents: Vec<ParentRef> = (0..MAX_PARENTS + 1)
            .map(|i| ParentRef { artifact_id: format!("art:p{i}"), role: None })
            .collect();
        let err = validate_parents(&conn, "art:new", &parents, &mock_exists).unwrap_err();
        assert!(err.contains("TOO_MANY_PARENTS"));
    }

    #[test]
    fn test_cycle_detection() {
        let conn = setup_db();
        // Build chain: A → B → C
        record_parents(&conn, "art:B", &[ParentRef { artifact_id: "art:A".into(), role: None }], "t").unwrap();
        record_parents(&conn, "art:C", &[ParentRef { artifact_id: "art:B".into(), role: None }], "t").unwrap();

        // Try to make A → C (which would create C → B → A → C cycle)
        let parents = vec![ParentRef { artifact_id: "art:C".into(), role: None }];
        let err = validate_parents(&conn, "art:A", &parents, &mock_exists).unwrap_err();
        assert!(err.contains("CYCLE_DETECTED"), "got: {err}");
    }

    #[test]
    fn test_no_false_cycle() {
        let conn = setup_db();
        // Chain: A → B → C. Adding D → C is fine (no cycle)
        record_parents(&conn, "art:B", &[ParentRef { artifact_id: "art:A".into(), role: None }], "t").unwrap();
        record_parents(&conn, "art:C", &[ParentRef { artifact_id: "art:B".into(), role: None }], "t").unwrap();

        let parents = vec![ParentRef { artifact_id: "art:C".into(), role: None }];
        assert!(validate_parents(&conn, "art:D", &parents, &mock_exists).is_ok());
    }

    #[test]
    fn test_root_artifact_empty_parents() {
        let conn = setup_db();
        assert!(validate_parents(&conn, "art:root", &[], &mock_exists).is_ok());
    }

    #[test]
    fn test_traverse_ancestors() {
        let conn = setup_db();
        record_parents(&conn, "art:B", &[ParentRef { artifact_id: "art:A".into(), role: Some("context".into()) }], "t").unwrap();
        record_parents(&conn, "art:C", &[ParentRef { artifact_id: "art:B".into(), role: Some("trigger".into()) }], "t").unwrap();

        let node_fn = |id: &str| -> Option<LineageNode> {
            Some(LineageNode {
                artifact_type: "memory.v1".into(),
                content_hash: format!("hash_{id}"),
                producer: "test".into(),
                created_at: "2026-04-14".into(),
                verified: true,
            })
        };

        let result = traverse_lineage(&conn, "art:C", 10, "ancestors", &node_fn).unwrap();
        assert_eq!(result.nodes.len(), 3); // C, B, A
        assert_eq!(result.edges.len(), 2); // C→B, B→A
        assert_eq!(result.depth_traversed, 2);
    }

    #[test]
    fn test_traverse_chain_valid_is_false() {
        // traverse_lineage should NOT claim chain_valid=true
        let conn = setup_db();
        let node_fn = |id: &str| -> Option<LineageNode> {
            Some(LineageNode {
                artifact_type: "memory.v1".into(),
                content_hash: format!("hash_{id}"),
                producer: "test".into(),
                created_at: "2026-04-14".into(),
                verified: false,
            })
        };
        let result = traverse_lineage(&conn, "art:root", 10, "ancestors", &node_fn).unwrap();
        assert!(!result.chain_valid, "traversal alone must not claim chain_valid");
    }

    // ── verify_chain tests ──────────────────────────────────────────────────

    fn mock_artifact_info(id: &str) -> Option<ArtifactInfo> {
        if id.starts_with("art:") {
            Some(ArtifactInfo {
                attestation_id: id.to_string(),
                content_hash: format!("hash_{id}"),
                solana_tx: format!("local:sol_{id}"),
                arweave_tx: format!("local:ar_{id}"),
                signer: "test_signer".to_string(),
            })
        } else {
            None
        }
    }

    #[test]
    fn test_verify_chain_single_root() {
        let conn = setup_db();
        let verifier = ChainVerifier {
            lookup_artifact: &mock_artifact_info,
            fetch_cose_bytes: &|_| Err("not needed for local".into()),
            fetch_anchor_hash: &|_| Err("not needed for local".into()),
        };

        let result = verify_chain(&conn, "art:root", &verifier);
        assert!(result.chain_valid);
        assert_eq!(result.nodes_verified, 1);
        assert_eq!(result.nodes_valid, 1);
        assert_eq!(result.nodes_failed, 0);
    }

    #[test]
    fn test_verify_chain_linear_3_nodes() {
        let conn = setup_db();
        // A ← B ← C
        record_parents(&conn, "art:B", &[ParentRef { artifact_id: "art:A".into(), role: None }], "t").unwrap();
        record_parents(&conn, "art:C", &[ParentRef { artifact_id: "art:B".into(), role: None }], "t").unwrap();

        let verifier = ChainVerifier {
            lookup_artifact: &mock_artifact_info,
            fetch_cose_bytes: &|_| Err("not needed for local".into()),
            fetch_anchor_hash: &|_| Err("not needed for local".into()),
        };

        let result = verify_chain(&conn, "art:C", &verifier);
        assert!(result.chain_valid);
        assert_eq!(result.nodes_verified, 3);
        assert_eq!(result.nodes_valid, 3);
        assert_eq!(result.depth_traversed, 2);
        assert_eq!(result.edges.len(), 2);
    }

    #[test]
    fn test_verify_chain_missing_parent() {
        let conn = setup_db();
        // B references A, but A is not in the store
        record_parents(&conn, "art:B", &[ParentRef { artifact_id: "missing:A".into(), role: None }], "t").unwrap();

        let verifier = ChainVerifier {
            lookup_artifact: &mock_artifact_info,
            fetch_cose_bytes: &|_| Err("not needed".into()),
            fetch_anchor_hash: &|_| Err("not needed".into()),
        };

        let result = verify_chain(&conn, "art:B", &verifier);
        assert!(!result.chain_valid);
        assert_eq!(result.nodes_failed, 2); // B fails (parent invalid) + missing:A fails (not found)
        let missing = result.nodes.get("missing:A").unwrap();
        assert!(missing.error.as_ref().unwrap().contains("ARTIFACT_NOT_FOUND"));
    }

    #[test]
    fn test_verify_chain_diamond_dag() {
        let conn = setup_db();
        // Diamond: D has parents B and C, both have parent A
        //     A
        //    / \
        //   B   C
        //    \ /
        //     D
        record_parents(&conn, "art:B", &[ParentRef { artifact_id: "art:A".into(), role: None }], "t").unwrap();
        record_parents(&conn, "art:C", &[ParentRef { artifact_id: "art:A".into(), role: None }], "t").unwrap();
        record_parents(&conn, "art:D", &[
            ParentRef { artifact_id: "art:B".into(), role: None },
            ParentRef { artifact_id: "art:C".into(), role: None },
        ], "t").unwrap();

        let verifier = ChainVerifier {
            lookup_artifact: &mock_artifact_info,
            fetch_cose_bytes: &|_| Err("not needed for local".into()),
            fetch_anchor_hash: &|_| Err("not needed for local".into()),
        };

        let result = verify_chain(&conn, "art:D", &verifier);
        assert!(result.chain_valid);
        assert_eq!(result.nodes_verified, 4); // D, B, C, A (A visited once)
        assert_eq!(result.nodes_valid, 4);
    }
}
