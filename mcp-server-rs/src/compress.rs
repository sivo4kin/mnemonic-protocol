//! TurboQuant compression layer — compresses f32 embeddings for efficient
//! storage on Arweave and compact representation in SQLite.
//!
//! Pipeline: f32 vec → TurboQuant compress → serialized bytes
//!           serialized bytes → TurboQuant decompress → f32 vec (approximate)

use ndarray::Array1;
use turboquant::TurboQuant;

/// Compressed embedding — serializable to bytes for storage.
#[derive(Debug, Clone)]
pub struct CompressedEmbedding {
    pub dim: usize,
    pub bit_width: usize,
    pub mse_indices: Vec<u8>,     // packed indices
    pub qjl_signs: Vec<i8>,       // sign bits
    pub vector_norm: f64,
    pub residual_norm: f64,
}

impl CompressedEmbedding {
    /// Serialize to bytes for SQLite/Arweave storage.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        // Header: dim (4), bit_width (1), vector_norm (8), residual_norm (8)
        buf.extend_from_slice(&(self.dim as u32).to_le_bytes());
        buf.push(self.bit_width as u8);
        buf.extend_from_slice(&self.vector_norm.to_le_bytes());
        buf.extend_from_slice(&self.residual_norm.to_le_bytes());
        // Indices length + data
        buf.extend_from_slice(&(self.mse_indices.len() as u32).to_le_bytes());
        buf.extend_from_slice(&self.mse_indices);
        // Signs length + data
        buf.extend_from_slice(&(self.qjl_signs.len() as u32).to_le_bytes());
        for &s in &self.qjl_signs {
            buf.push(s as u8);
        }
        buf
    }

    /// Deserialize from bytes.
    pub fn from_bytes(data: &[u8]) -> Option<Self> {
        if data.len() < 25 { return None; }
        let mut off = 0;

        let dim = u32::from_le_bytes(data[off..off+4].try_into().ok()?) as usize;
        off += 4;
        let bit_width = data[off] as usize;
        off += 1;
        let vector_norm = f64::from_le_bytes(data[off..off+8].try_into().ok()?);
        off += 8;
        let residual_norm = f64::from_le_bytes(data[off..off+8].try_into().ok()?);
        off += 8;

        let idx_len = u32::from_le_bytes(data[off..off+4].try_into().ok()?) as usize;
        off += 4;
        let mse_indices = data[off..off+idx_len].to_vec();
        off += idx_len;

        let signs_len = u32::from_le_bytes(data[off..off+4].try_into().ok()?) as usize;
        off += 4;
        let qjl_signs: Vec<i8> = data[off..off+signs_len].iter().map(|&b| b as i8).collect();

        Some(Self { dim, bit_width, mse_indices, qjl_signs, vector_norm, residual_norm })
    }
}

/// Compressor wrapping TurboQuant.
pub struct EmbeddingCompressor {
    tq: TurboQuant,
    dim: usize,
    bit_width: usize,
}

impl EmbeddingCompressor {
    pub fn new(dim: usize, bit_width: usize, seed: u64) -> Self {
        let tq = TurboQuant::new(dim, bit_width, seed, true);
        Self { tq, dim, bit_width }
    }

    /// Compress an f32 embedding vector.
    pub fn compress(&self, embedding: &[f32]) -> CompressedEmbedding {
        let x = Array1::from_iter(embedding.iter().map(|&v| v as f64));
        let compressed = self.tq.quantize(&x);

        // Extract single-vector data from batch format
        let mse_indices: Vec<u8> = compressed.mse_indices.row(0)
            .iter().map(|&i| i as u8).collect();
        let qjl_signs: Vec<i8> = compressed.qjl_signs.row(0)
            .iter().copied().collect();
        let vector_norm = compressed.vector_norms[0];
        let residual_norm = compressed.residual_norms[0];

        CompressedEmbedding {
            dim: self.dim,
            bit_width: self.bit_width,
            mse_indices,
            qjl_signs,
            vector_norm,
            residual_norm,
        }
    }

    /// Decompress back to approximate f32 vector.
    pub fn decompress(&self, compressed: &CompressedEmbedding) -> Vec<f32> {
        use ndarray::{Array2, Array1 as A1};

        let mse_indices = Array2::from_shape_vec(
            (1, compressed.dim),
            compressed.mse_indices.iter().map(|&i| i as usize).collect(),
        ).unwrap();

        let qjl_signs = Array2::from_shape_vec(
            (1, compressed.dim),
            compressed.qjl_signs.clone(),
        ).unwrap();

        let cv = turboquant::CompressedVectors {
            mse_indices,
            vector_norms: A1::from_vec(vec![compressed.vector_norm]),
            qjl_signs,
            residual_norms: A1::from_vec(vec![compressed.residual_norm]),
            bit_width: compressed.bit_width,
        };

        let reconstructed = self.tq.dequantize(&cv);
        reconstructed.row(0).iter().map(|&v| v as f32).collect()
    }

    /// Compression ratio vs f32.
    pub fn compression_ratio(&self) -> f64 {
        self.tq.compression_ratio(32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_vector(dim: usize) -> Vec<f32> {
        (0..dim).map(|i| ((i as f32) * 0.01).sin()).collect()
    }

    #[test]
    fn test_compress_decompress_roundtrip() {
        let c = EmbeddingCompressor::new(128, 4, 42);
        let original = sample_vector(128);
        let compressed = c.compress(&original);
        let restored = c.decompress(&compressed);

        assert_eq!(restored.len(), 128);
        // Check approximate reconstruction (TurboQuant is lossy)
        let mse: f32 = original.iter().zip(restored.iter())
            .map(|(a, b)| (a - b).powi(2)).sum::<f32>() / original.len() as f32;
        assert!(mse < 0.1, "MSE too high: {mse}");
    }

    #[test]
    fn test_serialize_deserialize() {
        let c = EmbeddingCompressor::new(128, 4, 42);
        let original = sample_vector(128);
        let compressed = c.compress(&original);

        let bytes = compressed.to_bytes();
        let restored = CompressedEmbedding::from_bytes(&bytes).unwrap();

        assert_eq!(restored.dim, 128);
        assert_eq!(restored.bit_width, 4);
        assert_eq!(restored.mse_indices.len(), compressed.mse_indices.len());
        assert_eq!(restored.qjl_signs.len(), compressed.qjl_signs.len());
        assert!((restored.vector_norm - compressed.vector_norm).abs() < 1e-10);
    }

    #[test]
    fn test_compression_ratio() {
        let c = EmbeddingCompressor::new(384, 4, 42);
        let ratio = c.compression_ratio();
        assert!(ratio > 3.0, "Expected >3x compression, got {ratio}");
    }

    #[test]
    fn test_compressed_size_smaller() {
        let c = EmbeddingCompressor::new(384, 4, 42);
        let v = sample_vector(384);
        let compressed = c.compress(&v);
        let bytes = compressed.to_bytes();

        let original_bytes = 384 * 4; // f32 = 4 bytes each
        assert!(bytes.len() < original_bytes,
            "compressed {} >= original {}", bytes.len(), original_bytes);
    }
}
