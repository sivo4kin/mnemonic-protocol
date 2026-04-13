//! Implementation of the 5 Mnemonic MCP tools.

use sha2::{Sha256, Digest};
use solana_sdk::signature::{Keypair, Signer};

use crate::{arweave::ArweaveClient, db::AttestationStore, embed, identity, solana::SolanaClient};

/// Tool 1: whoami (sync — DB only)
pub fn whoami(keypair: &Keypair, store: &AttestationStore) -> serde_json::Value {
    let pubkey = identity::pubkey_base58(keypair);
    let count = store.count(&pubkey).unwrap_or(0);
    serde_json::json!({
        "public_key": pubkey,
        "did_sol": identity::did_sol(keypair),
        "did_key": identity::did_key(keypair),
        "attestation_count": count,
    })
}

/// Tool 2: sign_memory (async — network + DB)
pub async fn sign_memory(
    keypair: &Keypair,
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    content: &str,
    tags: &[String],
) -> anyhow::Result<serde_json::Value> {
    let pubkey = identity::pubkey_base58(keypair);
    let attestation_id = uuid::Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();

    let embedding = embed::embed_text(content);
    let content_hash = hex::encode(Sha256::digest(content.as_bytes()));

    // Network: Arweave write
    let payload = serde_json::json!({
        "content": content, "content_hash": content_hash,
        "tags": tags, "signer": pubkey, "timestamp": now,
    });
    let arweave_tx = arweave.write(&payload.to_string()).await?;
    arweave.mine().await?;

    // Network: Solana memo
    let memo = serde_json::json!({"h": content_hash, "a": arweave_tx, "v": 1});
    let solana_tx = solana.write_memo(keypair, &memo.to_string()).await?;

    // DB: save locally (short lock, no await)
    {
        let store = store.lock().unwrap();
        store.save_attestation(
            &attestation_id, content, &content_hash, tags,
            &solana_tx, &arweave_tx, &pubkey, &now, &embedding,
        )?;
    }

    Ok(serde_json::json!({
        "attestation_id": attestation_id,
        "content_hash": content_hash,
        "solana_tx": solana_tx,
        "arweave_tx": arweave_tx,
        "signer": pubkey,
        "did_sol": identity::did_sol(keypair),
        "timestamp": now,
    }))
}

/// Tool 3: verify (async — network only)
pub async fn verify(
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    solana_tx: Option<&str>,
    arweave_tx: Option<&str>,
) -> anyhow::Result<serde_json::Value> {
    if solana_tx.is_none() && arweave_tx.is_none() {
        return Ok(serde_json::json!({"status": "error", "message": "Provide solana_tx or arweave_tx"}));
    }

    let mut expected_hash: Option<String> = None;
    let mut ar_tx = arweave_tx.map(|s| s.to_string());

    if let Some(sol_tx) = solana_tx {
        match solana.read_memo(sol_tx).await? {
            Some(memo) => {
                expected_hash = memo["h"].as_str().map(|s| s.to_string());
                if ar_tx.is_none() {
                    ar_tx = memo["a"].as_str().map(|s| s.to_string());
                }
            }
            None => return Ok(serde_json::json!({"status": "anchor_not_found", "solana_tx": sol_tx})),
        }
    }

    let ar_tx_id = ar_tx.as_deref().unwrap_or("");
    let raw_bytes = match arweave.read(ar_tx_id).await {
        Ok(b) => b,
        Err(_) => return Ok(serde_json::json!({"status": "arweave_not_found", "arweave_tx": ar_tx_id})),
    };

    let payload: serde_json::Value = serde_json::from_slice(&raw_bytes).unwrap_or_default();
    let content = payload["content"].as_str().unwrap_or("");
    let actual_hash = hex::encode(Sha256::digest(content.as_bytes()));

    if let Some(expected) = &expected_hash {
        if &actual_hash == expected {
            return Ok(serde_json::json!({
                "status": "verified", "content_hash": actual_hash,
                "solana_tx": solana_tx.unwrap_or(""), "arweave_tx": ar_tx_id,
                "signer": payload["signer"].as_str().unwrap_or(""),
                "content_preview": &content[..content.len().min(200)],
            }));
        }
        return Ok(serde_json::json!({
            "status": "tampered", "expected_hash": expected, "actual_hash": actual_hash,
        }));
    }

    Ok(serde_json::json!({"status": "hash_computed", "content_hash": actual_hash}))
}

/// Tool 4: prove_identity (sync — pure crypto)
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

/// Tool 5: recall (sync — DB only)
pub fn recall(keypair: &Keypair, store: &AttestationStore, query: &str, limit: usize) -> serde_json::Value {
    let pubkey = identity::pubkey_base58(keypair);
    let query_emb = embed::embed_text(query);
    let results = store.search(&query_emb, &pubkey, limit).unwrap_or_default();
    let total = store.count(&pubkey).unwrap_or(0);
    serde_json::json!({"query": query, "results": results, "total_attestations": total})
}
