use serde::{Deserialize, Serialize};

/// Quantized embedding: scalar quantization f32 → i8
/// Scale factor stored for lossless reconstruction of approximate vector
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuantizedEmbedding {
    pub bytes: Vec<i8>,
    pub scale: f32,
    pub dims: usize,
}

/// The full memory chunk written to Arweave
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryPayload {
    pub text: String,
    pub embedding: QuantizedEmbedding,
    pub content_hash: String,
    pub written_at: chrono::DateTime<chrono::Utc>,
}

/// Anchor record stored as SPL Memo on Solana
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnchorRecord {
    pub arweave_tx_id: String,
    pub content_hash: String,
    pub timestamp_unix: i64,
}

/// Full receipt returned to caller after a successful write
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryReceipt {
    pub arweave_tx_id: String,
    pub solana_tx_sig: String,
    pub content_hash: String,
    pub written_at: chrono::DateTime<chrono::Utc>,
}

/// Result of a recall + verification attempt
#[derive(Debug, Serialize, Deserialize)]
pub struct VerificationResult {
    pub status: VerificationStatus,
    pub expected_hash: String,
    pub actual_hash: String,
    pub arweave_tx_id: String,
    pub solana_tx_sig: String,
    pub payload: Option<MemoryPayload>,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub enum VerificationStatus {
    Verified,
    Tampered,
    AnchorNotFound,
    ArweaveNotFound,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_receipt_serde_roundtrip() {
        let receipt = MemoryReceipt {
            arweave_tx_id: "tx_abc123".into(),
            solana_tx_sig: "sig_def456".into(),
            content_hash: "deadbeef".repeat(8),
            written_at: chrono::Utc::now(),
        };
        let json = serde_json::to_string(&receipt).unwrap();
        let decoded: MemoryReceipt = serde_json::from_str(&json).unwrap();
        assert_eq!(receipt.arweave_tx_id, decoded.arweave_tx_id);
        assert_eq!(receipt.solana_tx_sig, decoded.solana_tx_sig);
        assert_eq!(receipt.content_hash, decoded.content_hash);
    }

    #[test]
    fn test_anchor_record_json_size_under_566_bytes() {
        let record = AnchorRecord {
            arweave_tx_id: "A".repeat(43), // standard Arweave TX ID length
            content_hash: "f".repeat(64),  // SHA-256 hex
            timestamp_unix: 1_700_000_000,
        };
        let json = serde_json::to_string(&record).unwrap();
        assert!(
            json.len() < 566,
            "AnchorRecord JSON is {} bytes, must be < 566 for SPL Memo",
            json.len()
        );
    }
}
