# Mnemonic MVP: Minimal Verification of the Core Thesis

## The one question this MVP answers

> Does compressed semantic memory survive an on-chain round-trip with
> sufficient retrieval quality to be useful?

If yes → the full Mnemonic architecture is viable.
If no → identify which link in the chain breaks and at what scale.

---

## What "works" means (pass/fail criteria)

| Test | Pass | Fail |
|------|------|------|
| 8-bit recall@20 on 10K memories | ≥ 0.95 | < 0.90 |
| 4-bit recall@20 on 10K memories | ≥ 0.90 | < 0.80 |
| Post-rerank recall@10 | ≥ 0.98 | < 0.95 |
| Rehydrated index matches original | Byte-identical | Any diff |
| Retrieval results after round-trip | Identical to pre-commit | Any diff |
| Total blob size (10K memories, 4-bit, 768-dim) | < 10 MB | > 50 MB |
| End-to-end cost (Arweave + Solana) | < $0.10 | > $1.00 |

---

## Scope: what the MVP IS and IS NOT

### IS
- A single Python script (~500 lines) that runs end-to-end
- Uses a real open embedding model (nomic-embed-text or MiniLM)
- Quantizes, serializes, uploads, downloads, deserializes, retrieves
- Measures retrieval quality before and after the round-trip
- Logs all metrics to JSON for analysis

### IS NOT
- A production system
- A Solana program (MVP uses a mock commitment or devnet)
- Multi-agent or multi-session
- Real-time or streaming
- A full Arweave integration (MVP can use local files simulating the round-trip,
  with optional Arweave testnet upload)

---

## Architecture (minimal)

```
┌─────────────────────────────────────────────────────┐
│                   MVP Pipeline                      │
│                                                     │
│  1. INGEST         Load 10K text memories           │
│       │            Embed with open model             │
│       ▼                                             │
│  2. COMPRESS       Normalize → Quantize (4/8-bit)   │
│       │            Store full + compressed           │
│       ▼                                             │
│  3. BASELINE       Run retrieval on N queries        │
│       │            Record recall@k, rankings         │
│       ▼                                             │
│  4. SERIALIZE      Pack: memories + embeddings +     │
│       │              compressed index + quantizer    │
│       │              state → single blob             │
│       ▼                                             │
│  5. HASH           SHA3-256(blob)                   │
│       │                                             │
│       ▼                                             │
│  6. COMMIT         Write hash to mock chain /        │
│       │              Solana devnet                   │
│       │            Upload blob to local file /       │
│       │              Arweave testnet                 │
│       ▼                                             │
│  7. REHYDRATE      Download blob (or read from       │
│       │              local path)                     │
│       │            Verify SHA3 matches commitment    │
│       │            Deserialize all layers            │
│       ▼                                             │
│  8. RETRIEVE       Run same N queries on             │
│       │              rehydrated index                │
│       │            Record recall@k, rankings         │
│       ▼                                             │
│  9. COMPARE        Diff baseline vs rehydrated       │
│       │            Report: identical? degraded?      │
│       ▼                                             │
│  10. REPORT        JSON output with all metrics      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Data requirements

### Memory corpus
- **Source**: Use a public dataset with natural text diversity:
  - Option A: `SQuAD` passages (~10K paragraphs)
  - Option B: `MS MARCO` passages (sample 10K)
  - Option C: Synthetic agent memory dataset (conversations, facts, tasks)
- **Format**: JSONL with `id`, `text`, `metadata`

### Query set
- 100-500 queries with known relevant memory IDs (ground truth)
- Can be derived from the corpus (e.g., questions from SQuAD)

---

## Implementation plan

### File: `mvp_verify.py`

```python
# Pseudocode structure — not final implementation

def main():
    config = parse_args()  # bits, corpus_path, query_path, output_path

    # 1. Load corpus
    memories = load_jsonl(config.corpus_path)

    # 2. Embed with open model
    embedder = load_open_embedder("nomic-embed-text-v1.5")  # or MiniLM
    embeddings = embedder.encode([m.text for m in memories])

    # 3. Build compressed index
    quantizer = CalibratedScalarQuantizer(bits=config.bits)
    normalized = normalize(embeddings)
    rotated = apply_rotation(normalized, seed=config.rotation_seed)
    quantizer.fit(rotated)
    compressed = [quantizer.quantize(v) for v in rotated]

    # 4. Baseline retrieval
    queries = load_jsonl(config.query_path)
    query_embeddings = embedder.encode([q.text for q in queries])
    baseline_results = retrieve_cascade(
        query_embeddings, compressed, embeddings, quantizer,
        n_candidates=50, k=10
    )
    baseline_recall = compute_recall(baseline_results, queries)

    # 5. Serialize to blob
    blob = serialize_snapshot(memories, embeddings, compressed, quantizer)

    # 6. Hash and "commit"
    content_hash = sha3_256(blob)
    commitment = mock_commit(content_hash, config)  # or solana devnet

    # 7. Rehydrate from blob
    restored = deserialize_snapshot(blob)
    assert sha3_256(serialize_snapshot(*restored)) == content_hash

    # 8. Retrieval on rehydrated index
    rehydrated_results = retrieve_cascade(
        query_embeddings, restored.compressed, restored.embeddings,
        restored.quantizer, n_candidates=50, k=10
    )
    rehydrated_recall = compute_recall(rehydrated_results, queries)

    # 9. Compare
    results_identical = (baseline_results == rehydrated_results)
    recall_preserved = (baseline_recall == rehydrated_recall)

    # 10. Report
    report = {
        "corpus_size": len(memories),
        "embedding_dim": embeddings.shape[1],
        "bits": config.bits,
        "blob_size_bytes": len(blob),
        "content_hash": content_hash.hex(),
        "baseline_recall_at_20": baseline_recall,
        "rehydrated_recall_at_20": rehydrated_recall,
        "results_identical": results_identical,
        "compression_ratio": len(blob) / (embeddings.nbytes + sum(len(m.text.encode()) for m in memories)),
        "estimated_arweave_cost_usd": len(blob) / 1e9 * 5.0,
    }
    save_json(report, config.output_path)
    print_summary(report)
```

---

## Key implementation details

### Serialization format (blob)

```
┌──────────────────────────────────────┐
│ Header (64 bytes)                    │
│   magic: "MNEM"                      │
│   version: u16                       │
│   embedding_model: utf8 (32 bytes)   │
│   embedding_dim: u16                 │
│   quant_bits: u8                     │
│   rotation_seed: u64                 │
│   n_memories: u32                    │
│   n_queries: u32 (unused, 0)         │
├──────────────────────────────────────┤
│ Quantizer state                      │
│   alphas: float32[dim]               │
│   steps: float32[dim]                │
├──────────────────────────────────────┤
│ Per-memory records (repeated)        │
│   memory_id: utf8 (len-prefixed)     │
│   text: utf8 (len-prefixed)          │
│   metadata_json: utf8 (len-pref.)    │
│   norm: float32                      │
│   full_embedding: float32[dim]       │
│   compressed_code: uint8[dim] or     │
│                    uint4[dim/2]       │
├──────────────────────────────────────┤
│ Footer                               │
│   record_count: u32 (integrity)      │
│   checksum: SHA3-256 of above        │
└──────────────────────────────────────┘
```

### Determinism guarantees in MVP

| Component | Deterministic? | How |
|---|---|---|
| Embedding | ✓ (same model, same input) | Use local model, not API |
| Normalization | ✓ | float64 intermediate |
| Rotation | ✓ | Seeded numpy PRNG |
| Quantization | ✓ | Integer arithmetic after calibration |
| Compressed scoring | ✓ | Integer dot product |
| Exact reranking | ✗ (float platform-dependent) | Acceptable — candidate set is deterministic |
| Serialization | ✓ | Fixed byte order (little-endian) |
| Hashing | ✓ | SHA3-256 standard |

---

## Dependencies (minimal)

```
numpy           # vector ops
sentence-transformers  # open embedding model
hashlib         # SHA3
struct          # binary packing
json            # reporting
```

Optional (for real on-chain test):
```
solders / solana-py   # Solana devnet commitment
arweave-python-client # Arweave upload
```

---

## What we learn from each outcome

### All tests pass
→ The core thesis holds. Compressed semantic memory survives on-chain
round-trip. Proceed to Phase 2 (real Solana program, multi-session demo).

### Recall degrades but results are still identical post-round-trip
→ Compression fidelity is the bottleneck, not the on-chain mechanism.
Fix: tune quantization (more bits, better calibration, add rotation).

### Results differ after round-trip
→ Serialization or deserialization is non-deterministic.
Fix: audit the packing format, check float endianness, verify quantizer
state reconstruction.

### Blob too large for economic viability
→ Need more aggressive compression or tiered storage (compress only the
index, store payloads separately with a content hash pointer).

### Embedding model is the bottleneck (too slow, too large)
→ Evaluate smaller models (MiniLM-L6 at 384-dim) or Matryoshka dimension
reduction.

---

## Timeline

| Day | Milestone |
|-----|-----------|
| 1 | Corpus preparation + embedding pipeline with open model |
| 2 | Quantization + serialization format + round-trip test |
| 3 | Retrieval cascade + baseline/rehydrated comparison |
| 4 | Solana devnet commitment (optional) + metrics report |
| 5 | Analysis, write-up, decision on Phase 2 |

---

## Success = one number

The MVP succeeds if this is true:

> **After compressing 10,000 memories to 4-bit, serializing to a blob,
> hashing, "committing" the hash, rehydrating from the blob, and running
> retrieval — the top-10 results for every test query are identical to
> the baseline.**

That single fact proves: compression is sufficient, serialization is lossless,
and the on-chain round-trip preserves retrieval determinism.

Everything else in the whitepaper is engineering on top of a proven foundation.
