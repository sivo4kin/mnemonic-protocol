mod common;

use chrono::Utc;
use mnemonic_verify::{
    embed, hash,
    receipt::{AnchorRecord, MemoryPayload, VerificationStatus},
    verify,
};

/// Full write → recall → verify pipeline test.
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
async fn test_write_produces_valid_receipt() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let (arweave_tx_id, solana_tx_sig, content_hash) =
        do_write("test memory: hello world", &arweave, &solana)
            .await
            .expect("write failed");

    assert!(!arweave_tx_id.is_empty(), "arweave_tx_id must be non-empty");
    assert!(!solana_tx_sig.is_empty(), "solana_tx_sig must be non-empty");
    assert!(!content_hash.is_empty(), "content_hash must be non-empty");
}

#[tokio::test]
async fn test_recall_returns_verified_for_intact_memory() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let text = "recall test: verify intact memory 2026";
    let (_arweave_tx_id, solana_tx_sig, _content_hash) =
        do_write(text, &arweave, &solana)
            .await
            .expect("write failed");

    let result = verify::recall_and_verify(&solana_tx_sig, &solana, &arweave)
        .await
        .expect("recall failed");

    assert_eq!(result.status, VerificationStatus::Verified);
    assert_eq!(result.expected_hash, result.actual_hash);
    let payload = result.payload.expect("payload must be Some for verified result");
    assert_eq!(payload.text, text);
}

#[tokio::test]
async fn test_recalled_text_matches_original() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let text = "specific test string 9f3a";
    let (_, solana_tx_sig, _) = do_write(text, &arweave, &solana)
        .await
        .expect("write failed");

    let result = verify::recall_and_verify(&solana_tx_sig, &solana, &arweave)
        .await
        .expect("recall failed");

    assert_eq!(result.status, VerificationStatus::Verified);
    assert_eq!(result.payload.unwrap().text, text);
}

#[tokio::test]
async fn test_content_hash_in_receipt_matches_solana_anchor() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let (_, solana_tx_sig, content_hash) =
        do_write("hash consistency test", &arweave, &solana)
            .await
            .expect("write failed");

    let anchor = solana
        .read_anchor(&solana_tx_sig)
        .await
        .expect("read anchor failed");

    assert_eq!(content_hash, anchor.content_hash);
}

#[tokio::test]
async fn test_multiple_writes_produce_distinct_receipts() {
    let Some((arweave, solana)) = common::require_local_nodes().await else {
        return;
    };

    let (ar_a, sol_a, hash_a) = do_write("text A for distinct test", &arweave, &solana)
        .await
        .expect("write A failed");

    let (ar_b, sol_b, hash_b) = do_write("text B for distinct test", &arweave, &solana)
        .await
        .expect("write B failed");

    assert_ne!(ar_a, ar_b, "arweave_tx_ids must differ");
    assert_ne!(sol_a, sol_b, "solana_tx_sigs must differ");
    assert_ne!(hash_a, hash_b, "content_hashes must differ");
}
