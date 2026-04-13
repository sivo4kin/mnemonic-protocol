//! SQLite attestation store — local index of signed memories.

use anyhow::Context;
use rusqlite::{Connection, params};
use std::path::Path;

const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS attestations (
    attestation_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    solana_tx TEXT NOT NULL,
    arweave_tx TEXT NOT NULL,
    signer_pubkey TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attestation_embeddings (
    attestation_id TEXT PRIMARY KEY,
    embedding_dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY (attestation_id) REFERENCES attestations(attestation_id)
);
CREATE INDEX IF NOT EXISTS idx_attestations_signer ON attestations(signer_pubkey);

-- Payment: API keys with pre-funded balance (for Cursor / human MCP clients)
CREATE TABLE IF NOT EXISTS api_keys (
    api_key TEXT PRIMARY KEY,
    owner_pubkey TEXT NOT NULL DEFAULT '',
    balance_micro_usdc INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

-- Payment: audit trail for deposits and charges
CREATE TABLE IF NOT EXISTS payment_events (
    event_id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL,
    amount_micro_usdc INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- 'deposit' | 'charge' | 'refund'
    tx_sig TEXT,               -- Solana tx sig (deposits only)
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payment_events_key ON payment_events(api_key);

-- Payment: x402 nonce deduplication (prevents replay attacks)
CREATE TABLE IF NOT EXISTS x402_nonces (
    tx_sig TEXT PRIMARY KEY,
    used_at TEXT NOT NULL
);
"#;

pub struct AttestationStore {
    conn: Connection,
}

impl AttestationStore {
    pub fn open(path: &Path) -> anyhow::Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("creating db directory")?;
        }
        let conn = Connection::open(path).context("opening SQLite")?;
        conn.execute_batch(SCHEMA).context("initializing schema")?;
        Ok(Self { conn })
    }

    pub fn in_memory() -> anyhow::Result<Self> {
        let conn = Connection::open_in_memory()?;
        conn.execute_batch(SCHEMA)?;
        Ok(Self { conn })
    }

    pub fn save_attestation(
        &self,
        attestation_id: &str,
        content: &str,
        content_hash: &str,
        tags: &[String],
        solana_tx: &str,
        arweave_tx: &str,
        signer_pubkey: &str,
        created_at: &str,
        embedding: &[f32],
    ) -> anyhow::Result<()> {
        let tags_json = serde_json::to_string(tags)?;
        self.conn.execute(
            "INSERT OR REPLACE INTO attestations VALUES (?,?,?,?,?,?,?,?)",
            params![attestation_id, content, content_hash, tags_json,
                    solana_tx, arweave_tx, signer_pubkey, created_at],
        )?;

        let emb_bytes = floats_to_bytes(embedding);
        self.conn.execute(
            "INSERT OR REPLACE INTO attestation_embeddings VALUES (?,?,?)",
            params![attestation_id, embedding.len() as i32, emb_bytes],
        )?;
        Ok(())
    }

    // ── API key / balance management ────────────────────────────────────────

    /// Create a new API key with zero balance. Returns the key.
    pub fn create_api_key(&self, owner_pubkey: &str) -> anyhow::Result<String> {
        let key = format!("mnm_{}", hex::encode(random_bytes::<24>()));
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "INSERT INTO api_keys (api_key, owner_pubkey, balance_micro_usdc, created_at) VALUES (?,?,0,?)",
            params![key, owner_pubkey, now],
        )?;
        Ok(key)
    }

    /// Get balance in micro-USDC for an API key. Returns None if key not found.
    pub fn get_balance(&self, api_key: &str) -> anyhow::Result<Option<i64>> {
        let mut stmt = self.conn.prepare(
            "SELECT balance_micro_usdc FROM api_keys WHERE api_key = ?"
        )?;
        let mut rows = stmt.query(params![api_key])?;
        Ok(rows.next()?.map(|r| r.get(0)).transpose()?)
    }

    /// Deduct `amount` from balance. Returns Err if insufficient funds or key not found.
    pub fn deduct_balance(&self, api_key: &str, amount: i64, description: &str) -> anyhow::Result<()> {
        let balance = self.get_balance(api_key)?
            .ok_or_else(|| anyhow::anyhow!("api key not found"))?;
        if balance < amount {
            anyhow::bail!("insufficient balance: have {balance} micro-USDC, need {amount}");
        }
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "UPDATE api_keys SET balance_micro_usdc = balance_micro_usdc - ?, last_used_at = ? WHERE api_key = ?",
            params![amount, now, api_key],
        )?;
        self.conn.execute(
            "INSERT INTO payment_events (event_id, api_key, amount_micro_usdc, event_type, description, created_at) VALUES (?,?,?,'charge',?,?)",
            params![uuid::Uuid::new_v4().to_string(), api_key, amount, description, now],
        )?;
        Ok(())
    }

    /// Credit a deposit. Returns new balance.
    pub fn credit_deposit(&self, api_key: &str, amount: i64, tx_sig: &str) -> anyhow::Result<i64> {
        let now = chrono::Utc::now().to_rfc3339();
        // Idempotent: skip if tx_sig already recorded
        let existing: i64 = self.conn.query_row(
            "SELECT COUNT(*) FROM payment_events WHERE tx_sig = ?",
            params![tx_sig], |r| r.get(0),
        )?;
        if existing > 0 {
            anyhow::bail!("deposit tx already applied: {tx_sig}");
        }
        self.conn.execute(
            "UPDATE api_keys SET balance_micro_usdc = balance_micro_usdc + ? WHERE api_key = ?",
            params![amount, api_key],
        )?;
        if self.conn.changes() == 0 {
            anyhow::bail!("api key not found: {api_key}");
        }
        self.conn.execute(
            "INSERT INTO payment_events (event_id, api_key, amount_micro_usdc, event_type, tx_sig, description, created_at) VALUES (?,?,?,'deposit',?,?,?)",
            params![uuid::Uuid::new_v4().to_string(), api_key, amount, tx_sig, "USDC deposit", now],
        )?;
        let new_balance: i64 = self.conn.query_row(
            "SELECT balance_micro_usdc FROM api_keys WHERE api_key = ?",
            params![api_key], |r| r.get(0),
        )?;
        Ok(new_balance)
    }

    /// Record an x402 tx sig as used (prevents replay). Returns Err if already used.
    pub fn mark_x402_nonce(&self, tx_sig: &str) -> anyhow::Result<()> {
        let now = chrono::Utc::now().to_rfc3339();
        let result = self.conn.execute(
            "INSERT INTO x402_nonces (tx_sig, used_at) VALUES (?,?)",
            params![tx_sig, now],
        );
        match result {
            Ok(_) => Ok(()),
            Err(rusqlite::Error::SqliteFailure(e, _)) if e.code == rusqlite::ErrorCode::ConstraintViolation => {
                anyhow::bail!("x402 payment already used: {tx_sig}")
            }
            Err(e) => Err(e.into()),
        }
    }

    pub fn count(&self, signer: &str) -> anyhow::Result<i64> {
        let count: i64 = self.conn.query_row(
            "SELECT COUNT(*) FROM attestations WHERE signer_pubkey = ?",
            params![signer], |row| row.get(0),
        )?;
        Ok(count)
    }

    pub fn search(
        &self,
        query_embedding: &[f32],
        signer: &str,
        limit: usize,
    ) -> anyhow::Result<Vec<SearchResult>> {
        let mut stmt = self.conn.prepare(
            "SELECT a.attestation_id, a.content, a.content_hash, a.tags,
                    a.solana_tx, a.arweave_tx, a.created_at, ae.embedding
             FROM attestations a
             JOIN attestation_embeddings ae ON a.attestation_id = ae.attestation_id
             WHERE a.signer_pubkey = ?"
        )?;

        let q_norm = l2_norm(query_embedding);
        let q_normalized: Vec<f32> = if q_norm > 0.0 {
            query_embedding.iter().map(|x| x / q_norm).collect()
        } else {
            query_embedding.to_vec()
        };

        let mut results: Vec<SearchResult> = stmt
            .query_map(params![signer], |row| {
                let emb_blob: Vec<u8> = row.get(7)?;
                let emb = bytes_to_floats(&emb_blob);
                let e_norm = l2_norm(&emb);
                let score = if e_norm > 0.0 {
                    q_normalized.iter().zip(emb.iter()).map(|(a, b)| a * b / e_norm).sum::<f32>()
                } else {
                    0.0
                };
                let tags_str: String = row.get(3)?;
                Ok(SearchResult {
                    attestation_id: row.get(0)?,
                    content: row.get(1)?,
                    content_hash: row.get(2)?,
                    tags: serde_json::from_str(&tags_str).unwrap_or_default(),
                    solana_tx: row.get(4)?,
                    arweave_tx: row.get(5)?,
                    created_at: row.get(6)?,
                    relevance_score: score,
                })
            })?
            .filter_map(|r| r.ok())
            .collect();

        results.sort_by(|a, b| b.relevance_score.partial_cmp(&a.relevance_score).unwrap());
        results.truncate(limit);
        Ok(results)
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct SearchResult {
    pub attestation_id: String,
    pub content: String,
    pub content_hash: String,
    pub tags: Vec<String>,
    pub solana_tx: String,
    pub arweave_tx: String,
    pub created_at: String,
    pub relevance_score: f32,
}

fn random_bytes<const N: usize>() -> [u8; N] {
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let t = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos() as u64;
    let pid = std::process::id() as u64;
    let cnt = COUNTER.fetch_add(1, Ordering::Relaxed);
    let mut state = t
        ^ pid.wrapping_mul(0x9e3779b97f4a7c15)
        ^ cnt.wrapping_mul(0x6c62272e07bb0142);
    let mut out = [0u8; N];
    for byte in out.iter_mut() {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        *byte = (state >> 33) as u8;
    }
    out
}

fn floats_to_bytes(v: &[f32]) -> Vec<u8> {
    v.iter().flat_map(|f| f.to_le_bytes()).collect()
}

fn bytes_to_floats(b: &[u8]) -> Vec<f32> {
    b.chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

fn l2_norm(v: &[f32]) -> f32 {
    v.iter().map(|x| x * x).sum::<f32>().sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::embed::{HashEmbedder, Embedder};

    fn embedder() -> HashEmbedder { HashEmbedder::default() }

    #[test]
    fn test_save_and_count() {
        let store = AttestationStore::in_memory().unwrap();
        let emb = embedder().embed("test content");
        store.save_attestation(
            "att-1", "test content", "hash123", &["tag1".into()],
            "sol_tx_1", "ar_tx_1", "signer1", "2026-04-13T00:00:00Z",
            &emb,
        ).unwrap();
        assert_eq!(store.count("signer1").unwrap(), 1);
        assert_eq!(store.count("signer2").unwrap(), 0);
    }

    #[test]
    fn test_search_ranked() {
        let store = AttestationStore::in_memory().unwrap();
        let e = embedder();
        for i in 0..3 {
            let content = format!("finding about topic {i}");
            let emb = e.embed(&content);
            store.save_attestation(
                &format!("att-{i}"), &content, &format!("h{i}"), &[],
                &format!("sol{i}"), &format!("ar{i}"), "agent1", "2026-04-13",
                &emb,
            ).unwrap();
        }
        let query = e.embed("topic 1");
        let results = store.search(&query, "agent1", 2).unwrap();
        assert_eq!(results.len(), 2);
        assert!(results[0].relevance_score >= results[1].relevance_score);
    }
}
