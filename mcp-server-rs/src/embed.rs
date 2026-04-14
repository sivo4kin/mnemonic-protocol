//! Embedding service — pluggable: fastembed (local ONNX), OpenAI API, or hash fallback.

use sha2::{Sha256, Digest};

/// Embedding provider trait.
pub trait Embedder: Send + Sync {
    fn embed(&self, text: &str) -> Vec<f32>;
    fn dim(&self) -> usize;
    fn provider_name(&self) -> &str;
    /// Returns true if this is the hash fallback (not semantic).
    fn is_fallback(&self) -> bool { false }
}

// ── FastEmbed (local ONNX) ──────────────────────────────────────────────────

/// Local ONNX embedder via fastembed (all-MiniLM-L6-v2, 384-dim).
/// Downloads model on first run (~22MB), cached at ~/.cache/fastembed.
/// Enable with: cargo build --features local-embed
#[cfg(feature = "local-embed")]
pub struct FastEmbedder {
    model: fastembed::TextEmbedding,
    dim: usize,
}

#[cfg(feature = "local-embed")]
impl FastEmbedder {
    pub fn try_new() -> Result<Self, String> {
        use fastembed::{TextEmbedding, InitOptions, EmbeddingModel};
        let model = TextEmbedding::try_new(InitOptions {
            model_name: EmbeddingModel::AllMiniLML6V2,
            ..Default::default()
        }).map_err(|e| format!("fastembed init failed: {e}"))?;

        // Probe dimension
        let sample = model.embed(vec!["test"], None)
            .map_err(|e| format!("fastembed probe failed: {e}"))?;
        let dim = sample.first().map(|v| v.len()).unwrap_or(384);

        Ok(Self { model, dim })
    }
}

#[cfg(feature = "local-embed")]
impl Embedder for FastEmbedder {
    fn embed(&self, text: &str) -> Vec<f32> {
        match self.model.embed(vec![text.to_string()], None) {
            Ok(embeddings) => {
                embeddings.into_iter().next().unwrap_or_else(|| vec![0.0; self.dim])
            }
            Err(e) => {
                tracing::error!("fastembed inference failed: {e}");
                vec![0.0; self.dim]
            }
        }
    }

    fn dim(&self) -> usize { self.dim }
    fn provider_name(&self) -> &str { "fastembed" }
}

// ── Hash embedder (fallback) ────────────────────────────────────────────────

/// Deterministic hash-based embedder (384-dim). Works offline, no API key.
/// NOT semantic — produces consistent but meaningless vectors.
pub struct HashEmbedder {
    dim: usize,
}

impl HashEmbedder {
    pub fn new(dim: usize) -> Self { Self { dim } }
}

impl Default for HashEmbedder {
    fn default() -> Self { Self { dim: 384 } }
}

impl Embedder for HashEmbedder {
    fn embed(&self, text: &str) -> Vec<f32> {
        let mut vec = vec![0.0f32; self.dim];
        for chunk in 0..=(self.dim / 8) {
            let input = format!("{text}:{chunk}");
            let hash = Sha256::digest(input.as_bytes());
            for (j, pair_offset) in (0..32).step_by(4).enumerate() {
                let idx = chunk * 8 + j;
                if idx >= self.dim { break; }
                let raw = u32::from_le_bytes([
                    hash[pair_offset], hash[pair_offset + 1],
                    hash[pair_offset + 2], hash[pair_offset + 3],
                ]);
                vec[idx] = (raw as f64 / u32::MAX as f64 * 2.0 - 1.0) as f32;
            }
        }
        l2_normalize(&mut vec);
        vec
    }

    fn dim(&self) -> usize { self.dim }
    fn provider_name(&self) -> &str { "hash" }
    fn is_fallback(&self) -> bool { true }
}

// ── OpenAI embedder ─────────────────────────────────────────────────────────

/// OpenAI embeddings API embedder.
pub struct OpenAIEmbedder {
    api_key: String,
    model: String,
    dim: usize,
}

impl OpenAIEmbedder {
    pub fn new(api_key: &str, model: &str) -> Self {
        let dim = if model.contains("small") { 1536 } else { 3072 };
        Self {
            api_key: api_key.to_string(),
            model: model.to_string(),
            dim,
        }
    }
}

impl Embedder for OpenAIEmbedder {
    fn embed(&self, text: &str) -> Vec<f32> {
        let client = reqwest::blocking::Client::new();
        let body = serde_json::json!({ "input": text, "model": self.model });
        let resp = client.post("https://api.openai.com/v1/embeddings")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&body)
            .send();

        match resp {
            Ok(r) => {
                if let Ok(json) = r.json::<serde_json::Value>() {
                    if let Some(embedding) = json["data"][0]["embedding"].as_array() {
                        return embedding.iter()
                            .filter_map(|v| v.as_f64().map(|f| f as f32))
                            .collect();
                    }
                }
                tracing::error!("OpenAI embedding failed, returning zeros");
                vec![0.0; self.dim]
            }
            Err(e) => {
                tracing::error!("OpenAI request failed: {e}");
                vec![0.0; self.dim]
            }
        }
    }

    fn dim(&self) -> usize { self.dim }
    fn provider_name(&self) -> &str { "openai" }
}

// ── Builder ─────────────────────────────────────────────────────────────────

/// Build embedder from config. Priority: fastembed > openai > hash (with warning).
pub fn build_embedder(provider: &str, api_key: &str, model: &str) -> Box<dyn Embedder> {
    match provider {
        "fastembed" => {
            #[cfg(feature = "local-embed")]
            {
                match FastEmbedder::try_new() {
                    Ok(e) => {
                        tracing::info!("Embedder: fastembed (all-MiniLM-L6-v2, {}-dim, local ONNX)", e.dim());
                        return Box::new(e);
                    }
                    Err(msg) => {
                        tracing::warn!("fastembed unavailable: {msg}");
                    }
                }
            }
            #[cfg(not(feature = "local-embed"))]
            {
                tracing::warn!("fastembed not compiled in. Build with: cargo build --features local-embed");
            }
            // Fallback chain: OpenAI if key available, else hash with warning
            if !api_key.is_empty() {
                tracing::info!("Falling back to OpenAI embeddings ({model})");
                Box::new(OpenAIEmbedder::new(api_key, model))
            } else {
                tracing::warn!(
                    "Using hash embedder — recall will NOT return semantic results. \
                     Set OPENAI_API_KEY for meaningful recall, or build with --features local-embed."
                );
                Box::new(HashEmbedder::default())
            }
        }
        "openai" if !api_key.is_empty() => {
            tracing::info!("Embedder: OpenAI {model}");
            Box::new(OpenAIEmbedder::new(api_key, model))
        }
        "openai" => {
            tracing::warn!("EMBED_PROVIDER=openai but OPENAI_API_KEY not set. Falling back to hash.");
            Box::new(HashEmbedder::default())
        }
        _ => {
            tracing::info!("Embedder: hash (384-dim, offline, non-semantic)");
            Box::new(HashEmbedder::default())
        }
    }
}

/// Cosine similarity between two vectors.
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if na == 0.0 || nb == 0.0 { return 0.0; }
    dot / (na * nb)
}

fn l2_normalize(vec: &mut [f32]) {
    let norm: f32 = vec.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm > 0.0 {
        for v in vec.iter_mut() { *v /= norm; }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_deterministic() {
        let e = HashEmbedder::default();
        assert_eq!(e.embed("hello"), e.embed("hello"));
    }

    #[test]
    fn test_hash_dimension() {
        let e = HashEmbedder::default();
        assert_eq!(e.embed("test").len(), 384);
    }

    #[test]
    fn test_hash_normalized() {
        let e = HashEmbedder::default();
        let v = e.embed("test");
        let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_hash_is_fallback() {
        let e = HashEmbedder::default();
        assert!(e.is_fallback());
    }

    #[test]
    fn test_cosine_self() {
        let e = HashEmbedder::default();
        let v = e.embed("test");
        assert!((cosine_similarity(&v, &v) - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_build_hash_explicit() {
        let e = build_embedder("hash", "", "");
        assert_eq!(e.provider_name(), "hash");
        assert!(e.is_fallback());
    }
}
