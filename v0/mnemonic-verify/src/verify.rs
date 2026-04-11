use crate::arweave::ArweaveClient;
use crate::hash;
use crate::receipt::{MemoryPayload, VerificationResult, VerificationStatus};
use crate::solana::SolanaClient;

/// Full recall + verification pipeline:
///
/// 1. read_anchor(solana_tx_sig) → AnchorRecord
/// 2. arweave_client.read(anchor.arweave_tx_id) → raw_bytes
/// 3. hash_bytes(raw_bytes) → actual_hash
/// 4. Compare actual_hash vs anchor.content_hash
/// 5. If match: deserialize raw_bytes → MemoryPayload, return Verified
/// 6. If mismatch: return Tampered (with both hashes for diff)
pub async fn recall_and_verify(
    solana_tx_sig: &str,
    solana: &SolanaClient,
    arweave: &ArweaveClient,
) -> anyhow::Result<VerificationResult> {
    // Step 1: Read anchor from Solana
    let anchor = match solana.read_anchor(solana_tx_sig).await {
        Ok(a) => a,
        Err(_) => {
            return Ok(VerificationResult {
                status: VerificationStatus::AnchorNotFound,
                expected_hash: String::new(),
                actual_hash: String::new(),
                arweave_tx_id: String::new(),
                solana_tx_sig: solana_tx_sig.to_string(),
                payload: None,
            });
        }
    };

    // Step 2: Read content from Arweave
    let raw_bytes = match arweave.read(&anchor.arweave_tx_id).await {
        Ok(bytes) => bytes,
        Err(_) => {
            return Ok(VerificationResult {
                status: VerificationStatus::ArweaveNotFound,
                expected_hash: anchor.content_hash.clone(),
                actual_hash: String::new(),
                arweave_tx_id: anchor.arweave_tx_id.clone(),
                solana_tx_sig: solana_tx_sig.to_string(),
                payload: None,
            });
        }
    };

    // Step 3: Hash the raw bytes
    let actual_hash = hash::hash_bytes(&raw_bytes);

    // Step 4: Compare
    if actual_hash == anchor.content_hash {
        // Step 5: Verified — deserialize payload
        let payload: Option<MemoryPayload> =
            serde_json::from_slice(&raw_bytes).ok();

        Ok(VerificationResult {
            status: VerificationStatus::Verified,
            expected_hash: anchor.content_hash,
            actual_hash,
            arweave_tx_id: anchor.arweave_tx_id,
            solana_tx_sig: solana_tx_sig.to_string(),
            payload,
        })
    } else {
        // Step 6: Tampered
        Ok(VerificationResult {
            status: VerificationStatus::Tampered,
            expected_hash: anchor.content_hash,
            actual_hash,
            arweave_tx_id: anchor.arweave_tx_id,
            solana_tx_sig: solana_tx_sig.to_string(),
            payload: None,
        })
    }
}
