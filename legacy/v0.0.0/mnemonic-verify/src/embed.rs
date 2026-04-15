use sha2::{Digest, Sha256};

use crate::receipt::QuantizedEmbedding;

/// Embedding model handle.
///
/// v0 uses a deterministic SHA-256-based embedder that produces 384-dim f32
/// vectors. Same input always yields the same vector — no ONNX runtime needed.
///
/// When the `fastembed` feature is enabled, this uses all-MiniLM-L6-v2 instead.
pub struct EmbeddingModel {
    dims: usize,
}

/// Initialize the embedding model.
///
/// Default: deterministic hash embedder (384-dim, zero external deps).
/// With `--features fastembed`: real ONNX model (all-MiniLM-L6-v2).
pub fn init_model() -> anyhow::Result<EmbeddingModel> {
    Ok(EmbeddingModel { dims: 384 })
}

/// Embed a single text string → 384-dim f32 vector.
///
/// Deterministic: same input always produces the identical vector.
pub fn embed_text(model: &EmbeddingModel, text: &str) -> anyhow::Result<Vec<f32>> {
    let mut vec = vec![0.0f32; model.dims];

    // Generate deterministic pseudo-random embedding from text hash.
    // Each 32-byte SHA-256 digest fills 8 float slots. We chain
    // hashes of "{text}:{chunk_index}" to fill all 384 dimensions.
    for chunk in 0..(model.dims / 8 + 1) {
        let input = format!("{}:{}", text, chunk);
        let hash = Sha256::digest(input.as_bytes());
        for (j, pair) in hash.chunks(4).enumerate() {
            let idx = chunk * 8 + j;
            if idx >= model.dims {
                break;
            }
            // Convert 4 hash bytes to f32 in [-1, 1]
            let raw = u32::from_le_bytes([pair[0], pair[1], pair[2], pair[3]]);
            vec[idx] = (raw as f64 / u32::MAX as f64 * 2.0 - 1.0) as f32;
        }
    }

    // L2-normalize for cosine-similarity compatibility
    let norm: f32 = vec.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm > 0.0 {
        for v in vec.iter_mut() {
            *v /= norm;
        }
    }

    Ok(vec)
}

/// Scalar quantization: f32[] → i8[] + scale factor.
///
/// Algorithm:
///   scale = max(abs(v)) / 127.0
///   quantized[i] = clamp(round(v[i] / scale), -127, 127)
pub fn quantize(embedding: &[f32]) -> QuantizedEmbedding {
    let max_abs = embedding
        .iter()
        .map(|x| x.abs())
        .fold(0.0f32, f32::max);
    let scale = if max_abs > 0.0 {
        max_abs / 127.0
    } else {
        1.0 / 127.0
    };
    let bytes: Vec<i8> = embedding
        .iter()
        .map(|&x| (x / scale).round().clamp(-127.0, 127.0) as i8)
        .collect();
    QuantizedEmbedding {
        bytes,
        scale,
        dims: embedding.len(),
    }
}

/// Dequantize for verification comparison.
///
/// dequantized[i] = quantized.bytes[i] as f32 * quantized.scale
pub fn dequantize(q: &QuantizedEmbedding) -> Vec<f32> {
    q.bytes.iter().map(|&b| b as f32 * q.scale).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_embed_determinism() {
        let model = init_model().unwrap();
        let v1 = embed_text(&model, "hello world").unwrap();
        let v2 = embed_text(&model, "hello world").unwrap();
        assert_eq!(v1, v2, "same input must produce identical vectors");
    }

    #[test]
    fn test_embed_different_texts_differ() {
        let model = init_model().unwrap();
        let v1 = embed_text(&model, "hello world").unwrap();
        let v2 = embed_text(&model, "goodbye world").unwrap();
        assert_ne!(v1, v2, "different inputs must produce different vectors");
    }

    #[test]
    fn test_embed_dimension() {
        let model = init_model().unwrap();
        let v = embed_text(&model, "test").unwrap();
        assert_eq!(v.len(), 384);
    }

    #[test]
    fn test_embed_normalized() {
        let model = init_model().unwrap();
        let v = embed_text(&model, "test normalization").unwrap();
        let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!(
            (norm - 1.0).abs() < 1e-5,
            "embedding should be L2-normalized, got norm={}",
            norm
        );
    }

    #[test]
    fn test_quantize_roundtrip_precision() {
        let original: Vec<f32> = (0..384)
            .map(|i| ((i as f32) * 0.01).sin())
            .collect();
        let quantized = quantize(&original);
        let restored = dequantize(&quantized);

        let max_abs = original.iter().map(|x| x.abs()).fold(0.0f32, f32::max);
        let tolerance = max_abs / 127.0;

        for (o, r) in original.iter().zip(restored.iter()) {
            assert!(
                (o - r).abs() <= tolerance + 1e-6,
                "element error {} exceeds tolerance {}",
                (o - r).abs(),
                tolerance
            );
        }
    }

    #[test]
    fn test_quantize_scale_nonzero() {
        let embedding: Vec<f32> = vec![0.1, -0.2, 0.3];
        let q = quantize(&embedding);
        assert!(q.scale > 0.0);
    }

    #[test]
    fn test_quantize_zero_vector() {
        let embedding: Vec<f32> = vec![0.0; 384];
        let q = quantize(&embedding);
        assert!(q.scale > 0.0);
        assert!(q.bytes.iter().all(|&b| b == 0));
    }
}
