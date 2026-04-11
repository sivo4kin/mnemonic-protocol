use crate::arweave::ArweaveClient;
use crate::hash;
use crate::receipt::{MemoryPayload, VerificationResult, VerificationStatus};
use crate::solana::SolanaClient;

/// Full recall + verification pipeline:
///
/// 1. read_anchor(solana_tx_sig) → AnchorRecord
/// 2. arweave_client.read(anchor.arweave_tx_id) → raw_bytes
/// 3. Deserialize raw_bytes → MemoryPayload
/// 4. hash_payload(&payload) → actual_hash (canonical: excludes content_hash field)
/// 5. Compare actual_hash vs anchor.content_hash
/// 6. If match: return Verified with payload
/// 7. If mismatch: return Tampered (with both hashes for diff)
///
/// Note: The write path computes content_hash via hash_payload() which excludes
/// the content_hash field from the digest. Recall must use the same canonical
/// representation to produce matching hashes.
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

    // Step 3: Deserialize and compute canonical hash.
    //
    // The write path hashes via hash_payload() which excludes the content_hash
    // field. We must use the same canonical representation here so that an
    // untampered payload reproduces the anchored digest.
    let payload: Option<MemoryPayload> = serde_json::from_slice(&raw_bytes).ok();

    let actual_hash = match &payload {
        Some(p) => hash::hash_payload(p),
        None => {
            // Can't deserialize — fall back to raw byte hash for comparison.
            // This will always mismatch (write used hash_payload), so it
            // correctly reports Tampered for corrupted/unparseable content.
            hash::hash_bytes(&raw_bytes)
        }
    };

    // Step 4: Compare
    if actual_hash == anchor.content_hash {
        Ok(VerificationResult {
            status: VerificationStatus::Verified,
            expected_hash: anchor.content_hash,
            actual_hash,
            arweave_tx_id: anchor.arweave_tx_id,
            solana_tx_sig: solana_tx_sig.to_string(),
            payload,
        })
    } else {
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
