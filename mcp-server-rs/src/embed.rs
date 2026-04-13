//! Embedding service — pluggable: hash fallback (offline) or OpenAI API.

use sha2::{Sha256, Digest};

/// Embedding provider trait.
pub trait Embedder: Send + Sync {
    fn embed(&self, text: &str) -> Vec<f32>;
    fn dim(&self) -> usize;
    fn provider_name(&self) -> &str;
}

/// Deterministic hash-based embedder (384-dim). Works offline, no API key.
pub struct HashEmbedder {
    dim: usize,
}

impl HashEmbedder {
    pub fn new(dim: usize) -> Self {
        Self { dim }
    }
}

impl Default for HashEmbedder {
    fn default() -> Self {
        Self { dim: 384 }
    }
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
}

/// OpenAI embeddings API embedder.
pub struct OpenAIEmbedder {
    api_key: String,
    model: String,
    dim: usize,
}

impl OpenAIEmbedder {
    pub fn new(api_key: &str, model: &str) -> Self {
        // text-embedding-3-small = 1536 dim
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
        // Blocking HTTP call — called from sync context via tools
        let client = reqwest::blocking::Client::new();
        let body = serde_json::json!({
            "input": text,
            "model": self.model,
        });
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
                tracing::error!("OpenAI embedding failed, falling back to hash");
                HashEmbedder::new(self.dim).embed(text)
            }
            Err(e) => {
                tracing::error!("OpenAI request failed: {e}, falling back to hash");
                HashEmbedder::new(self.dim).embed(text)
            }
        }
    }

    fn dim(&self) -> usize { self.dim }
    fn provider_name(&self) -> &str { "openai" }
}

/// Build embedder from config.
pub fn build_embedder(provider: &str, api_key: &str, model: &str) -> Box<dyn Embedder> {
    match provider {
        "openai" if !api_key.is_empty() => {
            tracing::info!("Embedder: OpenAI {model}");
            Box::new(OpenAIEmbedder::new(api_key, model))
        }
        _ => {
            tracing::info!("Embedder: hash (384-dim, offline)");
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
    fn test_different_texts() {
        let e = HashEmbedder::default();
        assert_ne!(e.embed("hello"), e.embed("goodbye"));
    }

    #[test]
    fn test_cosine_self() {
        let e = HashEmbedder::default();
        let v = e.embed("test");
        assert!((cosine_similarity(&v, &v) - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_build_hash_fallback() {
        let e = build_embedder("hash", "", "");
        assert_eq!(e.provider_name(), "hash");
        assert_eq!(e.dim(), 384);
    }

    #[test]
    fn test_build_openai_without_key_falls_back() {
        let e = build_embedder("openai", "", "text-embedding-3-small");
        assert_eq!(e.provider_name(), "hash"); // no key → fallback
    }
}
