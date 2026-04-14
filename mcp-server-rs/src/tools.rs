//! Implementation of the 5 Mnemonic MCP tools.

use sha2::{Sha256, Digest};
use solana_sdk::signature::Keypair;

use crate::{
    arweave::ArweaveClient,
    compress::EmbeddingCompressor,
    db::AttestationStore,
    embed::Embedder,
    identity,
    solana::SolanaClient,
};

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

/// Tool 2: sign_memory (async — embed → compress → arweave → solana → DB)
pub async fn sign_memory(
    keypair: &Keypair,
    solana: &SolanaClient,
    arweave: &ArweaveClient,
    store: &std::sync::Mutex<AttestationStore>,
    embedder: &dyn Embedder,
    compressor: &EmbeddingCompressor,
    content: &str,
    tags: &[String],
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

    // 4. Write to Arweave (includes compressed embedding for future index reconstruction)
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
    let arweave_tx = arweave.write(&payload.to_string(), keypair).await?;
    arweave.mine().await?;

    // 5. Anchor on Solana
    let memo = serde_json::json!({"h": content_hash, "a": arweave_tx, "v": 1});
    let solana_tx = solana.write_memo(keypair, &memo.to_string()).await?;

    // 6. Save locally (full embedding for search, compressed for storage reference)
    {
        let store = store.lock().unwrap();
        store.save_attestation(
            &attestation_id, content, &content_hash, tags,
            &solana_tx, &arweave_tx, &pubkey, &now, &embedding,
        )?;
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
                "has_compressed_embedding": payload.get("embedding_compressed").is_some(),
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
    serde_json::json!({
        "query": query,
        "results": results,
        "total_attestations": total,
        "embed_provider": embedder.provider_name(),
    })
}
