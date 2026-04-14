//! Implementation of the 5 Mnemonic MCP tools.

use sha2::{Sha256, Digest};
use solana_sdk::signature::Keypair;

use crate::{
    arweave::ArweaveClient,
    compress::EmbeddingCompressor,
    db::AttestationStore,
    embed::Embedder,
    identity,
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
/// In "full" mode: embed → compress → Arweave → Solana SPL Memo → SQLite
/// In "local" mode: embed → compress → SQLite only (no blockchain, free, instant)
pub async fn sign_memory(
    keypair: &Keypair,
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    embedder: &dyn Embedder,
    compressor: &EmbeddingCompressor,
    content: &str,
    tags: &[String],
    cost_hint: &CostHint,
    storage_mode: &str,
) -> anyhow::Result<serde_json::Value> {
    let pubkey = identity::pubkey_base58(keypair);
    let attestation_id = uuid::Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();

    // 1. Embed content
    let embedding = embedder.embed(content);

    // 2. Compress with TurboQuant
    let compressed = compressor.compress(&embedding);
    let compressed_bytes = compressed.to_bytes();

    // 3. SHA-256 of content
    let content_hash = hex::encode(Sha256::digest(content.as_bytes()));

    let (solana_tx, arweave_tx) = if storage_mode == "local" {
        // Local mode: skip blockchain, use synthetic IDs
        let local_ar = format!("local:{}", &attestation_id[..8]);
        let local_sol = format!("local:{}", &content_hash[..16]);
        (local_sol, local_ar)
    } else {
        // Full mode: Arweave + Solana
        let payload = serde_json::json!({
            "content": content,
            "content_hash": content_hash,
            "tags": tags,
            "signer": pubkey,
            "timestamp": now,
            "embedding_compressed": base64::Engine::encode(
                &base64::engine::general_purpose::STANDARD,
                &compressed_bytes,
            ),
            "embed_provider": embedder.provider_name(),
            "embed_dim": embedder.dim(),
            "turbo_bits": compressed.bit_width,
        });
        let ar_tx = arweave.write(&payload.to_string(), keypair).await?;
        arweave.mine().await?;

        let memo = serde_json::json!({"h": content_hash, "a": ar_tx, "v": 1});
        let sol_tx = solana.write_memo(keypair, &memo.to_string()).await?;
        (sol_tx, ar_tx)
    };

    // Save locally (both modes)
    {
        let store = store.lock().unwrap();
        store.save_attestation(
            &attestation_id, content, &content_hash, tags,
            &solana_tx, &arweave_tx, &pubkey, &now, &embedding,
        )?;
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
    Ok(serde_json::json!({
        "attestation_id": attestation_id,
        "content_hash": content_hash,
        "solana_tx": solana_tx,
        "arweave_tx": arweave_tx,
        "signer": pubkey,
        "did_sol": identity::did_sol(keypair),
        "timestamp": now,
        "storage_mode": storage_mode,
        "embed_provider": embedder.provider_name(),
        "embed_dim": embedder.dim(),
        "compression": {
            "algorithm": "TurboQuant",
            "bits": compressed.bit_width,
            "ratio": format!("{ratio:.1}x"),
            "original_bytes": embedding.len() * 4,
            "compressed_bytes": compressed_bytes.len(),
        },
    }))
}

/// Tool 3: verify
///
/// In "full" mode: fetch from Solana + Arweave → recompute hash
/// In "local" mode: verify from SQLite attestation store
pub async fn verify(
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    solana_tx: Option<&str>,
    arweave_tx: Option<&str>,
    storage_mode: &str,
) -> anyhow::Result<serde_json::Value> {
    // Local mode: look up by solana_tx (which is "local:..." synthetic ID) in SQLite
    if storage_mode == "local" {
        return verify_local(store, solana_tx, arweave_tx);
    }

    // Full mode: on-chain verification
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
                "has_compressed_embedding": payload.get("embedding_compressed").is_some(),
            }));
        }
        return Ok(serde_json::json!({
            "status": "tampered", "expected_hash": expected, "actual_hash": actual_hash,
        }));
    }

    Ok(serde_json::json!({"status": "hash_computed", "content_hash": actual_hash}))
}

/// Local-mode verification: look up attestation in SQLite and recompute hash.
fn verify_local(
    store: &std::sync::Mutex<AttestationStore>,
    solana_tx: Option<&str>,
    _arweave_tx: Option<&str>,
) -> anyhow::Result<serde_json::Value> {
    let lookup_id = solana_tx.or(_arweave_tx)
        .ok_or_else(|| anyhow::anyhow!("provide solana_tx or arweave_tx"))?;

    let store = store.lock().unwrap();
    let att = store.find_by_tx(lookup_id)?;

    match att {
        Some(a) => {
            let actual_hash = hex::encode(Sha256::digest(a.content.as_bytes()));
            if actual_hash == a.content_hash {
                Ok(serde_json::json!({
                    "status": "verified",
                    "storage_mode": "local",
                    "content_hash": actual_hash,
                    "solana_tx": a.solana_tx,
                    "arweave_tx": a.arweave_tx,
                    "signer": a.signer_pubkey,
                    "content_preview": &a.content[..a.content.len().min(200)],
                }))
            } else {
                Ok(serde_json::json!({
                    "status": "tampered",
                    "storage_mode": "local",
                    "expected_hash": a.content_hash,
                    "actual_hash": actual_hash,
                }))
            }
        }
        None => Ok(serde_json::json!({
            "status": "not_found",
            "storage_mode": "local",
            "lookup_id": lookup_id,
        })),
    }
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

/// Tool 5: recall (sync — DB search using full embeddings)
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
    let mut response = serde_json::json!({
        "query": query,
        "results": results,
        "total_attestations": total,
        "embed_provider": embedder.provider_name(),
    });
    if embedder.is_fallback() {
        response["embed_warning"] = serde_json::json!(
            "Hash embedder active \u{2014} recall results are NOT semantic. \
             Set OPENAI_API_KEY or ensure internet for fastembed model download."
        );
    }
    response
}
