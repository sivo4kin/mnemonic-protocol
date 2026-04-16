//! Implementation of the 5 Mnemonic MCP tools.
//!
//! Week 3: sign_memory and verify now use the CBOR/COSE codec pipeline.
//! - Content hash: blake3(canonical_cbor) instead of SHA-256(content)
//! - Arweave payload: COSE_Sign1 envelope (not raw JSON)
//! - Solana anchor: {"h": blake3_hash, "a": arweave_tx, "v": 2}

use solana_sdk::signature::Keypair;

use crate::{
    arweave::ArweaveClient,
    codec::{
        canonical::from_canonical_cbor,
        hash::hash_bytes as blake3_hash,
        schema::{self, ArtifactSchema, ParentRef},
        sign::{sign_artifact, verify_artifact as cose_verify},
    },
    compress::EmbeddingCompressor,
    db::AttestationStore,
    embed::Embedder,
    identity,
    lineage,
    pricing::CostHint,
    solana::SolanaClient,
};

/// Tool 1: whoami (sync — DB only)
pub fn whoami(keypair: &Keypair, store: &AttestationStore, storage_mode: &str) -> serde_json::Value {
    let pubkey = identity::pubkey_base58(keypair);
    let count = store.count(&pubkey).unwrap_or(0);
    serde_json::json!({
        "public_key": pubkey,
        "did_sol": identity::did_sol(keypair),
        "did_key": identity::did_key(keypair),
        "attestation_count": count,
        "storage_mode": storage_mode,
    })
}

/// Tool 2: sign_memory
///
/// Pipeline (full mode):
///   JSON artifact → canonical CBOR → blake3 hash → COSE_Sign1
///   → store COSE bytes on Arweave → anchor blake3 on Solana → SQLite
///
/// Pipeline (local mode):
///   JSON artifact → canonical CBOR → blake3 hash → COSE_Sign1
///   → SQLite only (synthetic tx IDs)
pub async fn sign_memory(
    keypair: &Keypair,
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    embedder: &dyn Embedder,
    compressor: &EmbeddingCompressor,
    content: &str,
    tags: &[String],
    parents: &[ParentRef],
    cost_hint: &CostHint,
    storage_mode: &str,
) -> anyhow::Result<serde_json::Value> {
    let pubkey = identity::pubkey_base58(keypair);
    let attestation_id = uuid::Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();

    // 0. Validate parents (existence + cycle detection) before doing any work
    if !parents.is_empty() {
        let store_guard = store.lock().unwrap();
        lineage::validate_parents(
            store_guard.conn(),
            &attestation_id,
            parents,
            &|id| store_guard.attestation_exists(id),
        ).map_err(|e| anyhow::anyhow!("{e}"))?;
    }

    // 1. Embed content
    let embedding = embedder.embed(content);

    // 2. Compress with TurboQuant
    let compressed = compressor.compress(&embedding);
    let compressed_bytes = compressed.to_bytes();

    // 3. Build artifact JSON for CBOR canonicalization
    let parents_json: Vec<serde_json::Value> = parents.iter().map(|p| {
        let mut obj = serde_json::json!({"artifact_id": p.artifact_id});
        if let Some(ref role) = p.role {
            obj["role"] = serde_json::json!(role);
        }
        obj
    }).collect();

    let mut artifact = serde_json::json!({
        "artifact_id": attestation_id,
        "type": "memory",
        "schema_version": 1,
        "content": content,
        "producer": identity::did_sol(keypair),
        "created_at": now,
        "tags": tags,
        "metadata": {
            "embed_provider": embedder.provider_name(),
            "embed_dim": embedder.dim(),
            "turbo_bits": compressed.bit_width,
            "embedding_compressed": base64::Engine::encode(
                &base64::engine::general_purpose::STANDARD,
                &compressed_bytes,
            ),
        },
    });
    if !parents.is_empty() {
        artifact["parents"] = serde_json::json!(parents_json);
    }

    // 4. Sign with COSE_Sign1 (canonical CBOR → blake3 → Ed25519)
    let signed = sign_artifact(&artifact, &schema::MEMORY_V1, keypair)
        .map_err(|e| anyhow::anyhow!("COSE signing failed: {e}"))?;

    let content_hash = signed.content_hash.clone();
    let embed_model = embedder.model_id().to_string();

    // 5. Store on-chain (or locally)
    let (solana_tx, arweave_tx) = if storage_mode == "local" {
        let local_ar = format!("local:{}", &attestation_id[..8]);
        let local_sol = format!("local:{}", &content_hash[..16]);
        (local_sol, local_ar)
    } else {
        // Arweave: store COSE_Sign1 bytes (not raw JSON)
        let ar_tx = arweave.write_bytes(&signed.cose_bytes, keypair).await?;
        arweave.mine().await?;

        // Solana: anchor blake3 hash + embedding model (v3 format)
        let memo = serde_json::json!({
            "h": content_hash,
            "a": ar_tx,
            "m": embed_model,
            "v": 3,
        });
        let sol_tx = solana.write_memo(keypair, &memo.to_string()).await?;
        (sol_tx, ar_tx)
    };

    // 6. Save locally + record lineage
    {
        let store = store.lock().unwrap();
        store.save_attestation(
            &attestation_id, content, &content_hash, tags,
            &solana_tx, &arweave_tx, &pubkey, &now, &embedding,
        )?;
        // Record parent references in lineage index
        if !parents.is_empty() {
            lineage::record_parents(store.conn(), &attestation_id, parents, &now)?;
        }
        if storage_mode != "local" {
            let _ = store.record_attestation_cost(
                &attestation_id,
                cost_hint.irys_lamports,
                cost_hint.sol_tx_fee_lamports,
                cost_hint.sol_price_usdc,
                cost_hint.charge_micro_usdc,
            );
        }
    }

    let ratio = compressor.compression_ratio();
    let mut result = serde_json::json!({
        "attestation_id": attestation_id,
        "content_hash": content_hash,
        "hash_algorithm": "blake3",
        "encoding": "cbor+cose",
        "solana_tx": solana_tx,
        "arweave_tx": arweave_tx,
        "signer": pubkey,
        "did_sol": identity::did_sol(keypair),
        "timestamp": now,
        "storage_mode": storage_mode,
        "embedding": {
            "model": embed_model,
            "provider": embedder.provider_name(),
            "dim": embedder.dim(),
            "verifiable": embedder.is_open_weights(),
        },
        "compression": {
            "algorithm": "TurboQuant",
            "bits": compressed.bit_width,
            "ratio": format!("{ratio:.1}x"),
            "original_bytes": embedding.len() * 4,
            "compressed_bytes": compressed_bytes.len(),
        },
    });
    if !parents.is_empty() {
        result["parents"] = serde_json::json!(parents);
    }
    Ok(result)
}

/// Tool 3: verify
///
/// Full mode: fetch COSE bytes from Arweave → COSE verify → compare hash with anchor
/// Local mode: SQLite lookup + blake3 recompute
pub async fn verify(
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    solana_tx: Option<&str>,
    arweave_tx: Option<&str>,
    storage_mode: &str,
) -> anyhow::Result<serde_json::Value> {
    if storage_mode == "local" {
        return verify_local(store, solana_tx, arweave_tx);
    }

    // Full mode
    if solana_tx.is_none() && arweave_tx.is_none() {
        return Ok(serde_json::json!({"status": "error", "message": "Provide solana_tx or arweave_tx"}));
    }

    let mut expected_hash: Option<String> = None;
    let mut ar_tx = arweave_tx.map(|s| s.to_string());
    let mut anchor_version: u64 = 1;

    if let Some(sol_tx) = solana_tx {
        match solana.read_memo(sol_tx).await? {
            Some(memo) => {
                expected_hash = memo["h"].as_str().map(|s| s.to_string());
                if ar_tx.is_none() {
                    ar_tx = memo["a"].as_str().map(|s| s.to_string());
                }
                anchor_version = memo["v"].as_u64().unwrap_or(1);
            }
            None => return Ok(serde_json::json!({"status": "anchor_not_found", "solana_tx": sol_tx})),
        }
    }

    let ar_tx_id = ar_tx.as_deref().unwrap_or("");
    let raw_bytes = match arweave.read(ar_tx_id).await {
        Ok(b) => b,
        Err(_) => return Ok(serde_json::json!({"status": "arweave_not_found", "arweave_tx": ar_tx_id})),
    };

    // Detect artifact format:
    // - If anchor_version >= 2 from Solana memo → COSE
    // - If no Solana anchor but payload looks like COSE (CBOR array tag 0x84) → try COSE
    // - Otherwise → legacy JSON + SHA-256
    let is_cose = anchor_version >= 2 || (solana_tx.is_none() && looks_like_cose(&raw_bytes));

    if is_cose {
        return verify_cose(&raw_bytes, expected_hash.as_deref(), solana_tx, ar_tx_id);
    }

    // v1 artifacts (legacy): raw JSON + SHA-256
    verify_legacy_json(&raw_bytes, expected_hash.as_deref(), solana_tx, ar_tx_id)
}

/// Heuristic: COSE_Sign1 is a CBOR 4-element array.
/// CBOR array of 4 items starts with byte 0x84.
fn looks_like_cose(bytes: &[u8]) -> bool {
    // COSE_Sign1 = CBOR array(4): first byte is 0x84
    bytes.first() == Some(&0x84)
}

/// Verify a v2 COSE_Sign1 artifact from Arweave.
fn verify_cose(
    cose_bytes: &[u8],
    expected_hash: Option<&str>,
    solana_tx: Option<&str>,
    arweave_tx: &str,
) -> anyhow::Result<serde_json::Value> {
    let result = cose_verify(cose_bytes, expected_hash)
        .map_err(|e| anyhow::anyhow!("COSE verification failed: {e}"))?;

    // Try to recover content preview from the CBOR payload
    let content_preview = from_canonical_cbor(&result.payload)
        .ok()
        .and_then(|json| json["content"].as_str().map(|s| s[..s.len().min(200)].to_string()))
        .unwrap_or_default();

    Ok(serde_json::json!({
        "status": if result.valid { "verified" } else { "tampered" },
        "encoding": "cbor+cose",
        "checks": {
            "content_integrity": result.content_integrity,
            "cose_signature": result.cose_signature,
            "algorithm_valid": result.algorithm_valid,
        },
        "content_hash": result.content_hash,
        "hash_algorithm": "blake3",
        "solana_tx": solana_tx.unwrap_or(""),
        "arweave_tx": arweave_tx,
        "signer": result.signer,
        "content_preview": content_preview,
    }))
}

/// Verify a v1 legacy artifact (raw JSON + SHA-256).
fn verify_legacy_json(
    raw_bytes: &[u8],
    expected_hash: Option<&str>,
    solana_tx: Option<&str>,
    arweave_tx: &str,
) -> anyhow::Result<serde_json::Value> {
    use sha2::{Sha256, Digest};

    let payload: serde_json::Value = serde_json::from_slice(raw_bytes).unwrap_or_default();
    let content = payload["content"].as_str().unwrap_or("");
    let actual_hash = hex::encode(Sha256::digest(content.as_bytes()));

    if let Some(expected) = expected_hash {
        if actual_hash == expected {
            return Ok(serde_json::json!({
                "status": "verified",
                "encoding": "json+sha256 (legacy v1)",
                "content_hash": actual_hash,
                "hash_algorithm": "sha256",
                "solana_tx": solana_tx.unwrap_or(""),
                "arweave_tx": arweave_tx,
                "signer": payload["signer"].as_str().unwrap_or(""),
                "content_preview": &content[..content.len().min(200)],
            }));
        }
        return Ok(serde_json::json!({
            "status": "tampered",
            "encoding": "json+sha256 (legacy v1)",
            "expected_hash": expected,
            "actual_hash": actual_hash,
        }));
    }

    Ok(serde_json::json!({"status": "hash_computed", "content_hash": actual_hash}))
}

/// Local-mode verification: SQLite lookup + hash check.
///
/// For v2+ artifacts (CBOR+COSE), the content_hash is blake3(canonical_cbor)
/// over the full artifact structure, not just the content string. Local mode
/// cannot fully reconstruct the canonical CBOR (the full artifact JSON is not
/// persisted), so local verify confirms the record exists and reports the
/// stored hash. For full tamper detection, use STORAGE_MODE=full or
/// mnemonic_verify_chain.
///
/// For v1 (legacy) artifacts, content_hash is SHA-256(content), which we can
/// still verify locally.
fn verify_local(
    store: &std::sync::Mutex<AttestationStore>,
    solana_tx: Option<&str>,
    arweave_tx: Option<&str>,
) -> anyhow::Result<serde_json::Value> {
    let lookup_id = solana_tx.or(arweave_tx)
        .ok_or_else(|| anyhow::anyhow!("provide solana_tx or arweave_tx"))?;

    let store = store.lock().unwrap();
    let att = store.find_by_tx(lookup_id)?;

    match att {
        Some(a) => {
            // Try legacy SHA-256 check (v1 artifacts stored SHA-256(content))
            let legacy_match = {
                use sha2::{Sha256, Digest};
                hex::encode(Sha256::digest(a.content.as_bytes())) == a.content_hash
            };

            if legacy_match {
                // v1 artifact: content hash fully verifiable locally
                return Ok(serde_json::json!({
                    "status": "verified",
                    "storage_mode": "local",
                    "encoding": "json+sha256 (legacy v1)",
                    "content_hash": a.content_hash,
                    "hash_algorithm": "sha256",
                    "solana_tx": a.solana_tx,
                    "arweave_tx": a.arweave_tx,
                    "signer": a.signer_pubkey,
                    "content_preview": &a.content[..a.content.len().min(200)],
                }));
            }

            // v2+ artifact (CBOR+COSE): content_hash = blake3(canonical_cbor)
            // We can confirm the record exists but cannot recompute the hash
            // without the full artifact structure. Report as "found" and
            // recommend verify_chain for full verification.
            Ok(serde_json::json!({
                "status": "found",
                "storage_mode": "local",
                "encoding": "cbor+cose",
                "content_hash": a.content_hash,
                "hash_algorithm": "blake3",
                "attestation_id": a.attestation_id,
                "solana_tx": a.solana_tx,
                "arweave_tx": a.arweave_tx,
                "signer": a.signer_pubkey,
                "content_preview": &a.content[..a.content.len().min(200)],
                "note": "local mode cannot recompute blake3(canonical_cbor). Use mnemonic_verify_chain for full DAG verification, or STORAGE_MODE=full for on-chain verification.",
            }))
        }
        None => Ok(serde_json::json!({
            "status": "not_found",
            "storage_mode": "local",
            "lookup_id": lookup_id,
        })),
    }
}

/// Tool 4: lineage (sync — DB only)
///
/// Traverse the lineage DAG from a starting artifact.
pub fn get_lineage(
    store: &AttestationStore,
    artifact_id: &str,
    direction: &str,
    max_depth: usize,
) -> serde_json::Value {
    let node_fn = |id: &str| -> Option<lineage::LineageNode> {
        store.find_by_id(id).ok().flatten().map(|a| lineage::LineageNode {
            artifact_type: "memory.v1".to_string(),
            content_hash: a.content_hash,
            producer: a.signer_pubkey,
            created_at: String::new(), // not stored in AttestationRow currently
            verified: false, // not verified by traversal alone
        })
    };

    match lineage::traverse_lineage(store.conn(), artifact_id, max_depth, direction, &node_fn) {
        Ok(result) => serde_json::to_value(&result).unwrap_or_default(),
        Err(e) => serde_json::json!({"error": e.to_string()}),
    }
}

/// Tool 5: verify_chain
///
/// Full DAG verification: walk ancestors from artifact_id, verify each node's
/// COSE signature, content hash, and on-chain anchor.
pub async fn verify_chain(
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    artifact_id: &str,
    storage_mode: &str,
) -> anyhow::Result<serde_json::Value> {
    // Phase 1: Collect all artifact info from DB (short lock, no await).
    // We must fully release the MutexGuard before any .await to keep the future Send.
    let (artifact_map, local_result) = {
        let store_guard = store.lock().unwrap();

        // For local mode, run verification entirely within the lock and return early data
        if storage_mode == "local" {
            let verifier = lineage::ChainVerifier {
                lookup_artifact: &|id: &str| {
                    store_guard.find_by_id(id).ok().flatten().map(|a| lineage::ArtifactInfo {
                        attestation_id: a.attestation_id,
                        content_hash: a.content_hash,
                        solana_tx: a.solana_tx,
                        arweave_tx: a.arweave_tx,
                        signer: a.signer_pubkey,
                    })
                },
                fetch_cose_bytes: &|_tx: &str| Err("local mode".to_string()),
                fetch_anchor_hash: &|_tx: &str| Err("local mode".to_string()),
            };
            let result = lineage::verify_chain(store_guard.conn(), artifact_id, &verifier);
            (std::collections::HashMap::new(), Some(serde_json::to_value(&result).unwrap_or_default()))
        } else {
            // Full mode: collect all reachable artifact IDs and their info.
            let mut artifact_map: std::collections::HashMap<String, lineage::ArtifactInfo> = std::collections::HashMap::new();
            let mut to_visit = std::collections::VecDeque::new();
            let mut visited = std::collections::HashSet::new();
            to_visit.push_back(artifact_id.to_string());

            while let Some(id) = to_visit.pop_front() {
                if visited.contains(&id) { continue; }
                visited.insert(id.clone());

                if let Ok(Some(a)) = store_guard.find_by_id(&id) {
                    artifact_map.insert(id.clone(), lineage::ArtifactInfo {
                        attestation_id: a.attestation_id,
                        content_hash: a.content_hash,
                        solana_tx: a.solana_tx,
                        arweave_tx: a.arweave_tx,
                        signer: a.signer_pubkey,
                    });
                    if let Ok(parents) = lineage::get_parents(store_guard.conn(), &id) {
                        for p in parents {
                            to_visit.push_back(p.artifact_id);
                        }
                    }
                }
            }
            (artifact_map, None)
        }
    }; // MutexGuard dropped here — before any .await

    // Early return for local mode
    if let Some(result) = local_result {
        return Ok(result);
    }

    // Phase 2: Async fetch COSE bytes and anchor hashes (no lock held)
    let mut cose_cache: std::collections::HashMap<String, Result<Vec<u8>, String>> = std::collections::HashMap::new();
    let mut anchor_cache: std::collections::HashMap<String, Result<Option<String>, String>> = std::collections::HashMap::new();

    for info in artifact_map.values() {
        if !info.arweave_tx.starts_with("local:") && !cose_cache.contains_key(&info.arweave_tx) {
            match arweave.read(&info.arweave_tx).await {
                Ok(bytes) => { cose_cache.insert(info.arweave_tx.clone(), Ok(bytes)); }
                Err(e) => { cose_cache.insert(info.arweave_tx.clone(), Err(e.to_string())); }
            }
        }
        if !info.solana_tx.starts_with("local:") && !anchor_cache.contains_key(&info.solana_tx) {
            match solana.read_memo(&info.solana_tx).await {
                Ok(Some(memo)) => {
                    let hash = memo["h"].as_str().map(|s| s.to_string());
                    anchor_cache.insert(info.solana_tx.clone(), Ok(hash));
                }
                Ok(None) => { anchor_cache.insert(info.solana_tx.clone(), Ok(None)); }
                Err(e) => { anchor_cache.insert(info.solana_tx.clone(), Err(e.to_string())); }
            }
        }
    }

    // Phase 3: Re-acquire lock and run verify_chain with populated caches
    let store_guard = store.lock().unwrap();
    let verifier = lineage::ChainVerifier {
        lookup_artifact: &|id: &str| artifact_map.get(id).cloned(),
        fetch_cose_bytes: &|tx: &str| {
            cose_cache.get(tx).cloned().unwrap_or_else(|| Err("not fetched".into()))
        },
        fetch_anchor_hash: &|tx: &str| {
            anchor_cache.get(tx).cloned().unwrap_or_else(|| Err("not fetched".into()))
        },
    };

    let result = lineage::verify_chain(store_guard.conn(), artifact_id, &verifier);
    Ok(serde_json::to_value(&result).unwrap_or_default())
}

/// Tool 6: prove_identity (sync — pure crypto)
pub fn prove_identity(keypair: &Keypair, challenge: &str) -> serde_json::Value {
    let sig = identity::sign_bytes(keypair, challenge.as_bytes());
    serde_json::json!({
        "public_key": identity::pubkey_base58(keypair),
        "did_sol": identity::did_sol(keypair),
        "challenge": challenge,
        "signature": hex::encode(&sig),
        "algorithm": "Ed25519",
    })
}

/// Tool 5: recall (sync — DB search)
pub fn recall(
    keypair: &Keypair,
    store: &AttestationStore,
    embedder: &dyn Embedder,
    query: &str,
    limit: usize,
) -> serde_json::Value {
    let pubkey = identity::pubkey_base58(keypair);
    let query_emb = embedder.embed(query);
    let results = store.search(&query_emb, &pubkey, limit).unwrap_or_default();
    let total = store.count(&pubkey).unwrap_or(0);
    serde_json::json!({
        "query": query,
        "results": results,
        "total_attestations": total,
        "embed_provider": embedder.provider_name(),
        "embed_model": embedder.model_id(),
        "verifiable": embedder.is_open_weights(),
    })
}
