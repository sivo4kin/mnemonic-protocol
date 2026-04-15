use thiserror::Error;

#[derive(Error, Debug)]
pub enum MnemonicError {
    #[error("Arweave write failed: {0}")]
    ArweaveWrite(String),

    #[error("Arweave read failed — tx_id not found: {0}")]
    ArweaveNotFound(String),

    #[error("Solana anchor write failed: {0}")]
    SolanaWrite(String),

    #[error("Solana anchor not found for sig: {0}")]
    AnchorNotFound(String),

    #[error("Hash mismatch — expected {expected}, got {actual}")]
    HashMismatch { expected: String, actual: String },

    #[error("Payload deserialization failed: {0}")]
    DeserializeError(String),

    #[error("Embedding model error: {0}")]
    EmbedError(String),

    #[error("Node unreachable: {url} — {reason}")]
    NodeUnreachable { url: String, reason: String },
}
