mod common;

use chrono::Utc;
use mnemonic_verify::{
    embed, hash,
    receipt::{AnchorRecord, MemoryPayload, VerificationStatus},
    verify,
};

/// Helper: write a memory and return (arweave_tx_id, solana_tx_sig, content_hash).
async fn do_write(
    text: &str,
    arweave: &mnemonic_verify::arweave::ArweaveClient,
    solana: &mnemonic_verify::solana::SolanaClient,
) -> anyhow::Result<(String, String, String)> {
    let model = embed::init_model()?;
    let embedding = embed::embed_text(&model, text)?;
    let quantized = embed::quantize(&embedding);

    let now = Utc::now();
    let mut payload = MemoryPayload {
        text: text.to_string(),
        embedding: quantized,
        content_hash: String::new(),
        written_at: now,
    };
    let content_hash = hash::hash_payload(&payload);
    payload.content_hash = content_hash.clone();

    let payload_json = serde_json::to_string(&payload)?;
    let arweave_tx_id = arweave.write(&payload_json).await?;
    arweave.mine().await?;

    let anchor = AnchorRecord {
        arweave_tx_id: arweave_tx_id.clone(),
        content_hash: content_hash.clone(),
        timestamp_unix: now.timestamp(),
    };
    let solana_tx_sig = solana.write_anchor(&anchor).await?;

    Ok((arweave_tx_id, solana_tx_sig, content_hash))
}

#[tokio::test]
async fn test_tampered_content_detected() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    // 1. Write legitimate memory
    let text = "legitimate memory for tamper test";
    let (_, original_sig, original_hash) = do_write(text, &arweave, &solana)
        .await
        .expect("write failed");

    // 2. Write corrupted data to a NEW Arweave tx
    let corrupted_data = "THIS DATA HAS BEEN TAMPERED WITH";
    let corrupted_tx_id = arweave
        .write(corrupted_data)
        .await
        .expect("write corrupted failed");
    arweave.mine().await.expect("mine failed");

    // 3. Create a new Solana anchor pointing to corrupted tx but with ORIGINAL hash
    let tampered_anchor = AnchorRecord {
        arweave_tx_id: corrupted_tx_id,
        content_hash: original_hash.clone(), // original hash — will mismatch
        timestamp_unix: Utc::now().timestamp(),
    };
    let tampered_sig = solana
        .write_anchor(&tampered_anchor)
        .await
        .expect("write tampered anchor failed");

    // 4. Verify — should detect tamper
    let result = verify::recall_and_verify(&tampered_sig, &solana, &arweave)
        .await
        .expect("recall failed");

    assert_eq!(result.status, VerificationStatus::Tampered);
    assert_ne!(result.expected_hash, result.actual_hash);
    assert!(result.payload.is_none(), "tampered result should have no payload");

    // 5. Verify original is still intact
    let original_result = verify::recall_and_verify(&original_sig, &solana, &arweave)
        .await
        .expect("original recall failed");
    assert_eq!(original_result.status, VerificationStatus::Verified);
}

#[tokio::test]
async fn test_tampered_result_preserves_expected_hash() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let (_, _, original_hash) =
        do_write("hash preservation test", &arweave, &solana)
            .await
            .expect("write failed");

    // Create mismatched anchor
    let corrupted_tx_id = arweave
        .write("corrupted content xyz")
        .await
        .expect("write corrupted failed");
    arweave.mine().await.unwrap();

    let tampered_anchor = AnchorRecord {
        arweave_tx_id: corrupted_tx_id,
        content_hash: original_hash.clone(),
        timestamp_unix: Utc::now().timestamp(),
    };
    let tampered_sig = solana
        .write_anchor(&tampered_anchor)
        .await
        .expect("write anchor failed");

    let result = verify::recall_and_verify(&tampered_sig, &solana, &arweave)
        .await
        .expect("recall failed");

    // Expected hash must survive tamper — it comes from Solana, not Arweave
    assert_eq!(result.expected_hash, original_hash);
    assert_ne!(result.actual_hash, original_hash);
}

#[tokio::test]
async fn test_recall_nonexistent_tx_returns_anchor_not_found() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let result = verify::recall_and_verify("invalid_sig_xxxx", &solana, &arweave)
        .await
        .expect("recall should not error, but return AnchorNotFound");

    assert_eq!(result.status, VerificationStatus::AnchorNotFound);
}
