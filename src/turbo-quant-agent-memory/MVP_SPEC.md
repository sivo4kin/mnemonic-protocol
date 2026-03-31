# MVP Spec: Compressed Agent Memory Retrieval

## Overview

A minimal system that stores agent memory items with full-precision embeddings
and a compressed shadow index, then retrieves memories via 2-stage lookup:
fast candidate generation on the compressed index, followed by exact reranking
on full-precision vectors.

This is **not** full TurboQuant. No random rotation, no residual QJL. Uses
corpus-calibrated per-dimension scalar quantization (4-bit or 8-bit) as the
compression layer.

---

## Goals

1. **Fast approximate recall** -- compressed index reduces memory scan cost.
2. **High final accuracy** -- exact rerank on shortlist preserves retrieval quality.
3. **Simple implementation** -- a solo engineer can build and validate in 1-2 weeks.
4. **Clear upgrade path** -- design slots where TurboQuant extensions (rotation,
   residual coding) can plug in later without rewriting core logic.

## Non-Goals

- Production-grade serving infrastructure (no gRPC, no horizontal scaling).
- Random rotation or QJL residual quantization (phase-2).
- Learned quantization or codebook methods.
- Multi-tenant isolation or auth.
- Streaming ingestion or real-time index updates at scale.

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Recall@20 from compressed candidates vs. exact brute-force | >= 0.95 for 8-bit, >= 0.90 for 4-bit |
| Rerank restores top-10 precision to exact search | >= 0.98 |
| Index memory footprint (8-bit) vs. float32 baseline | <= 30% |
| Index memory footprint (4-bit) vs. float32 baseline | <= 15% |
| End-to-end retrieval latency (10k memories, single query) | < 50ms |
| Time to implement core loop | <= 5 engineering days |

---

## Milestones

### M1 -- Storage & Ingestion (days 1-2)
- Memory item schema (SQLite or in-memory dict).
- Embedding generation (call any embedding model, e.g. `text-embedding-3-small`).
- Full-precision vector store.
- Scalar quantization routine (4-bit and 8-bit).
- Shadow index build/rebuild.

### M2 -- Retrieval Pipeline (days 3-4)
- Compressed candidate generation (inner-product on quantized vectors).
- Exact rerank on shortlist using full-precision vectors.
- Configurable `k` (final results) and `n_candidates` (shortlist size).

### M3 -- Evaluation & Tuning (day 5)
- Synthetic memory corpus (1k-10k items).
- Recall@k benchmark: compressed-only vs. 2-stage vs. exact brute-force.
- Latency benchmark.
- Document findings, recommended defaults.

---

## Evaluation Metrics

1. **Recall@k** -- fraction of true top-k neighbors found by each stage.
2. **Precision@k after rerank** -- how close reranked results are to exact search.
3. **Memory ratio** -- bytes(compressed index) / bytes(float32 index).
4. **Latency** -- wall-clock time for candidate generation, rerank, and total.
5. **Reconstruction error** -- L2 distance between dequantized and original vectors
   (sanity check on quantization quality).

---

## Recommended Defaults

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Embedding dimension | 384 (mock) / 1536 (OpenAI) | Mock uses 384; OpenAI `text-embedding-3-small` uses 1536 |
| Quantization bits | 8 | Good accuracy/compression trade-off |
| Quantization scheme | Per-dimension calibrated symmetric scalar | 98th-percentile clip per dimension |
| n_candidates | 5 * k | Empirical sweet spot; tune in M3 |
| k (final results) | 10 | Typical agent retrieval need |
| Distance metric | Inner product (cosine on normalized vectors) | Standard for text embeddings |

---

## Experiment Plan

### Experiment 1: Quantization Quality
- Generate 5,000 random embeddings (dim=1536, unit-normalized).
- Quantize at 4-bit and 8-bit.
- Measure per-vector reconstruction error (L2, cosine).
- Plot error distribution. Confirm 8-bit error is negligible.

### Experiment 2: Retrieval Accuracy
- Build a corpus of 10,000 synthetic memory items.
- For 200 random queries, compute exact top-50 (brute-force float32).
- Run compressed candidate generation (n_candidates = 50, 100, 200).
- Measure Recall@10, Recall@20 of compressed stage.
- Apply exact rerank on each candidate set. Measure final Recall@10.
- Compare 4-bit vs. 8-bit.

### Experiment 3: Latency
- Measure candidate generation time for 1k, 5k, 10k corpus sizes.
- Measure rerank time as a function of n_candidates.
- Identify the crossover point where 2-stage is faster than brute-force.
