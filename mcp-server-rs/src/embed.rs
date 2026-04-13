//! Deterministic hash-based embedder (384-dim).
//! Same algorithm as the Python hash fallback — produces identical vectors.

use sha2::{Sha256, Digest};

pub const DIM: usize = 384;

/// Embed text into a 384-dim f32 vector using deterministic SHA-256 hashing.
pub fn embed_text(text: &str) -> Vec<f32> {
    let mut vec = vec![0.0f32; DIM];

    for chunk in 0..=(DIM / 8) {
        let input = format!("{text}:{chunk}");
        let hash = Sha256::digest(input.as_bytes());
        for (j, pair_offset) in (0..32).step_by(4).enumerate() {
            let idx = chunk * 8 + j;
            if idx >= DIM {
                break;
            }
            let raw = u32::from_le_bytes([
                hash[pair_offset],
                hash[pair_offset + 1],
                hash[pair_offset + 2],
                hash[pair_offset + 3],
            ]);
            vec[idx] = (raw as f64 / u32::MAX as f64 * 2.0 - 1.0) as f32;
        }
    }

    // L2-normalize
    let norm: f32 = vec.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm > 0.0 {
        for v in vec.iter_mut() {
            *v /= norm;
        }
    }
    vec
}

/// Cosine similarity between two vectors.
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if na == 0.0 || nb == 0.0 {
        return 0.0;
    }
    dot / (na * nb)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deterministic() {
        let v1 = embed_text("hello world");
        let v2 = embed_text("hello world");
        assert_eq!(v1, v2);
    }

    #[test]
    fn test_dimension() {
        assert_eq!(embed_text("test").len(), DIM);
    }

    #[test]
    fn test_normalized() {
        let v = embed_text("test normalization");
        let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 1e-5, "norm={norm}");
    }

    #[test]
    fn test_different_texts_differ() {
        let v1 = embed_text("hello");
        let v2 = embed_text("goodbye");
        assert_ne!(v1, v2);
    }

    #[test]
    fn test_cosine_self() {
        let v = embed_text("test");
        assert!((cosine_similarity(&v, &v) - 1.0).abs() < 1e-5);
    }
}
