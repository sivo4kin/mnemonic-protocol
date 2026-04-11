use sha2::{Digest, Sha256};

use crate::receipt::MemoryPayload;

/// Canonical hashing of MemoryPayload.
///
/// 1. Serialize payload to JSON (serde_json uses BTreeMap by default → sorted keys)
/// 2. Remove the `content_hash` field from the serialized JSON object
/// 3. SHA-256 the canonical UTF-8 bytes
/// 4. Return lowercase hex string
pub fn hash_payload(payload: &MemoryPayload) -> String {
    let mut value = serde_json::to_value(payload).expect("MemoryPayload must serialize");
    if let serde_json::Value::Object(ref mut map) = value {
        map.remove("content_hash");
    }
    let canonical = serde_json::to_string(&value).expect("canonical JSON serialization");
    hash_bytes(canonical.as_bytes())
}

/// SHA-256 hash of raw bytes, returned as lowercase hex.
pub fn hash_bytes(data: &[u8]) -> String {
    let digest = Sha256::digest(data);
    hex::encode(digest)
}

/// Verify: recompute hash of raw bytes and compare to expected hex string.
pub fn verify_hash(data: &[u8], expected_hex: &str) -> bool {
    hash_bytes(data) == expected_hex
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::receipt::{MemoryPayload, QuantizedEmbedding};

    fn make_payload(content_hash: &str) -> MemoryPayload {
        MemoryPayload {
            text: "test memory".into(),
            embedding: QuantizedEmbedding {
                bytes: vec![1, 2, 3],
                scale: 0.01,
                dims: 3,
            },
            content_hash: content_hash.into(),
            written_at: chrono::DateTime::parse_from_rfc3339("2026-04-11T10:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
        }
    }

    #[test]
    fn test_hash_determinism() {
        let payload = make_payload("");
        let h1 = hash_payload(&payload);
        let h2 = hash_payload(&payload);
        assert_eq!(h1, h2, "same payload must produce identical hash");
    }

    #[test]
    fn test_hash_sensitivity() {
        let p1 = make_payload("");
        let mut p2 = make_payload("");
        p2.text = "test memory!".into(); // one character different
        assert_ne!(
            hash_payload(&p1),
            hash_payload(&p2),
            "different payload must produce different hash"
        );
    }

    #[test]
    fn test_hash_excludes_content_hash_field() {
        let p1 = make_payload("");
        let p2 = make_payload("some_different_hash_value");
        assert_eq!(
            hash_payload(&p1),
            hash_payload(&p2),
            "content_hash field must be excluded from hash computation"
        );
    }

    #[test]
    fn test_verify_hash_ok() {
        let data = b"hello world";
        let h = hash_bytes(data);
        assert!(verify_hash(data, &h));
    }

    #[test]
    fn test_verify_hash_fail_on_mutation() {
        let data = b"hello world";
        let h = hash_bytes(data);
        assert!(!verify_hash(b"hello world!", &h));
    }
}
