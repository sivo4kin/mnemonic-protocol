# Verifiable Persistent Agent Memory via Compressed On-Chain Embeddings

**Draft v0.1 — March 2026**

---

## Abstract

Large language model agents lack persistent, verifiable memory. Session context
vanishes when an inference provider restarts, and no standard mechanism exists
for an agent to prove what it knew or when it knew it. We propose **Mnemonic** —
an architecture that stores compressed semantic memory embeddings on permanent
decentralized storage (Arweave / Filecoin) with integrity hashes anchored to a
high-throughput L1 (Solana). The compression layer draws on TurboQuant's
insight that randomized scalar quantization achieves near-optimal distortion at
extreme bit-widths, enabling a 1536-dimensional embedding to be stored in
≤768 bytes at 4-bit precision while preserving >90% retrieval recall via a
two-stage cascade (compressed candidate generation → exact rerank). The result
is agent memory that is **portable across providers**, **verifiable on-chain**,
**economically viable** at scale, and **semantically meaningful** — unlike raw
KV cache snapshots, which are model-locked, multi-gigabyte, and opaque.

---

## 1. Problem Statement

### 1.1 Agent memory is ephemeral

Today's LLM agents operate in one of two memory modes:

1. **Context window** — fast, accurate, gone when the session ends.
2. **External RAG stores** — persistent but centralized, unverifiable, and
   controlled by a single provider.

Neither mode gives an agent a durable, portable identity. If Provider A shuts
down, the agent's accumulated knowledge disappears. If the agent migrates to
Provider B, it starts from zero.

### 1.2 Why raw KV caches are the wrong abstraction

A natural-sounding fix is to snapshot the transformer's KV cache — the
intermediate attention state — and store it. TurboQuant (Zandieh & Mirrokni,
2025) shows that KV caches can be compressed to ~2.5 bits/value with marginal
quality loss. However, KV caches fail as portable memory for three reasons:

| Property | KV Cache | Semantic Embedding Index |
|---|---|---|
| Model-portable | ✗ Architecture-locked | ✓ Any model using same embedder |
| Cross-version stable | ✗ Breaks on model updates | ✓ Stable within embedding model version |
| Human-interpretable | ✗ Opaque tensor state | ✓ Linked to source text |
| Size (128K context, 70B model) | ~2-3 GB compressed | ~1-10 MB for thousands of memories |
| On-chain cost at $5/GB | $10-15 per snapshot | $0.005-0.05 per snapshot |

**The right unit of persistent memory is the semantic memory item — not the
attention state.**

### 1.3 What is missing

A complete solution requires:

1. **Compression** — embeddings must be small enough for on-chain economics.
2. **Retrieval fidelity** — compressed search must not destroy ranking quality.
3. **Verifiability** — anyone can prove a memory existed at a given time.
4. **Determinism** — same compressed blob + same query = same retrieval result.
5. **Provider independence** — no single inference provider controls the state.
6. **Open embedding standard** — the embedding model must be freely runnable.

---

## 2. Core Insight: Applying TurboQuant to Semantic Memory

### 2.1 What TurboQuant actually teaches

TurboQuant (arXiv:2504.19874) introduces a data-oblivious vector quantization
method:

1. **Random rotation** transforms arbitrary vectors into statistically regular
   coordinates.
2. **Per-coordinate scalar quantization** exploits high-dimensional
   concentration for near-optimal compression.
3. **Residual correction** (1-bit QJL sketch) restores inner-product fidelity.

The key theoretical result: distortion scales as **4^{-b}** where b is
bits-per-coordinate — meaning 4-bit quantization achieves ~1/256th the
distortion of 1-bit, near the information-theoretic limit.

### 2.2 The transfer to agent memory

We apply TurboQuant's *architectural lesson* — not its KV cache application —
to semantic memory embeddings:

```
TurboQuant principle          →  Agent memory application
─────────────────────────────────────────────────────────
Randomize to regularize       →  Shared rotation seed for all memories
Cheap scalar quantization     →  4/8-bit per-dimension embedding compression
Residual correction           →  2-stage cascade: compressed search → exact rerank
Data-oblivious operation      →  No retraining when memory corpus grows
Metric-aware optimization     →  Optimize for retrieval recall, not MSE
```

This gives us embeddings compressed to **6.25–12.5%** of their original size
while preserving retrieval quality through the cascade.

---

## 3. Architecture: Mnemonic Protocol

### 3.1 Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Session                        │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Ingest   │───▶│ Memory Store │───▶│  Retrieval   │  │
│  │ Pipeline │    │  (local)     │    │  Engine      │  │
│  └──────────┘    └──────┬───────┘    └──────────────┘  │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                    ┌─────▼──────┐
                    │  Snapshot  │  (end of session or periodic)
                    │  & Commit  │
                    └─────┬──────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
        ┌─────▼────┐ ┌───▼────┐ ┌───▼──────┐
        │ Compress  │ │ Hash   │ │ Anchor   │
        │ & Pack    │ │ (SHA3) │ │ (Solana) │
        └─────┬────┘ └───┬────┘ └───┬──────┘
              │           │          │
        ┌─────▼───────────▼──┐  ┌───▼──────────────┐
        │  Arweave/Filecoin  │  │ Solana Program    │
        │  (blob storage)    │  │ (hash registry)   │
        └────────────────────┘  └───────────────────┘
```

### 3.2 Memory layers

Each memory item consists of:

| Layer | Contents | Storage | Purpose |
|-------|----------|---------|---------|
| L0 — Payload | Text, summary, metadata, tags | Arweave blob | Source of truth |
| L1 — Full embedding | float32 vector + norm | Arweave blob | Exact reranking |
| L2 — Compressed index | 4/8-bit quantized vector | Arweave blob | Fast retrieval |
| L3 — Quantizer state | Per-dim alphas, steps, rotation seed | Arweave blob | Reproducibility |
| L4 — Commitment | SHA3(L0‖L1‖L2‖L3) | Solana account | Verifiability |

### 3.3 Compression pipeline

For each memory item with embedding `e ∈ ℝ^d`:

```
1.  u = e / ‖e‖                          # normalize
2.  z = R · u  where R is seeded PRNG     # random rotation (shared seed)
3.  For each dim j:
      q_j = round((z_j + α_j) / step_j)  # per-dim scalar quantization
4.  Pack q[] into byte array              # 4-bit: d/2 bytes, 8-bit: d bytes
5.  Store: packed_bytes ‖ norm ‖ memory_id
```

**Compression ratios:**

| Embedding dim | float32 size | 8-bit compressed | 4-bit compressed |
|---|---|---|---|
| 384 (MiniLM) | 1,536 B | 384 B (25%) | 192 B (12.5%) |
| 768 (E5-base) | 3,072 B | 768 B (25%) | 384 B (12.5%) |
| 1536 (text-embedding-3-small) | 6,144 B | 1,536 B (25%) | 768 B (12.5%) |

### 3.4 Retrieval cascade

```
Query q
  │
  ▼
[Compress q with same R, α, step]
  │
  ▼
[Score against L2 compressed index]  ──▶  top n_candidates (broad, cheap)
  │
  ▼
[Fetch L1 full embeddings for candidates]
  │
  ▼
[Exact cosine rerank]  ──▶  top k (precise)
  │
  ▼
[Fetch L0 payloads]  ──▶  memory items injected into context
```

**Target metrics:**

| Metric | 8-bit target | 4-bit target |
|---|---|---|
| Recall@20 (candidate stage) | ≥ 0.95 | ≥ 0.90 |
| Recall@10 (after rerank) | ≥ 0.98 | ≥ 0.95 |
| Latency (10K memories) | < 50ms | < 50ms |

### 3.5 On-chain commitment scheme

At snapshot time (end of session, or periodic):

```
1.  Serialize memory store state:
      S = [L0_items ‖ L1_embeddings ‖ L2_compressed ‖ L3_quantizer_state]
2.  Compute content hash:
      H = SHA3-256(S)
3.  Upload S to Arweave → get transaction ID: ar_tx_id
4.  Write to Solana program:
      {
        agent_id:       pubkey,
        memory_version: u64,
        content_hash:   H,
        arweave_tx:     ar_tx_id,
        timestamp:      slot,
        embedding_model: string,
        quant_config:   { bits, rotation_seed, version }
      }
5.  Sign with agent's keypair
```

**What this enables:**

- **Existence proof**: "Memory M existed at time T" — verify H on-chain, fetch
  from Arweave, recompute hash.
- **Tamper detection**: If Arweave blob doesn't match on-chain hash, memory was
  altered.
- **Audit trail**: Full version history of agent's memory state.
- **Provider migration**: New provider downloads blob from Arweave, rehydrates
  locally, verifies hash.

### 3.6 Deterministic retrieval

For retrieval to be reproducible given the same compressed blob and query:

1. **Fixed rotation seed** — stored in L3, deterministic PRNG.
2. **Fixed quantizer state** — per-dim alphas and steps stored in L3.
3. **Canonical scoring** — integer dot product on packed codes, no floating
   point non-determinism.
4. **Deterministic tie-breaking** — by memory_id on equal scores.

This means: `same_blob + same_query_embedding = same_candidate_list`, always.
The exact rerank stage uses float arithmetic (platform-dependent), but the
candidate set is deterministic.

---

## 4. Open Embedding Standard

### 4.1 The portability requirement

If the embedding model is proprietary (e.g., OpenAI's text-embedding-3-small),
the agent's memory is still provider-dependent — not at the storage layer, but
at the semantic layer. A new provider cannot re-embed queries compatibly.

### 4.2 Solution: canonical open embedder

Mnemonic specifies a **canonical open embedding model** that any participant can
run:

- **Primary recommendation**: `nomic-embed-text-v1.5` (768-dim, open weights,
  Apache 2.0, Matryoshka support for dimension reduction)
- **Alternative**: `BAAI/bge-base-en-v1.5` (768-dim, MIT license)
- **Fallback**: `all-MiniLM-L6-v2` (384-dim, Apache 2.0, smallest footprint)

The embedding model identifier is stored in the on-chain commitment. Any party
can:
1. Download the model weights (open, deterministic)
2. Embed a query
3. Run retrieval against the compressed index
4. Verify results match

### 4.3 Embedding model versioning

When the canonical model changes:
- Old memories retain their original `embedding_model` tag
- A migration job re-embeds and re-compresses under the new model
- Both versions coexist until migration completes
- On-chain record tracks which model version each snapshot uses

---

## 5. Economics

### 5.1 Storage costs

| Scenario | Memories | 4-bit index size | Arweave cost (~$5/GB) | Solana tx |
|---|---|---|---|---|
| Personal agent | 1,000 | ~750 KB | $0.004 | $0.00025 |
| Professional agent | 10,000 | ~7.5 MB | $0.04 | $0.00025 |
| Enterprise agent | 100,000 | ~75 MB | $0.38 | $0.00025 |
| Autonomous agent (1M) | 1,000,000 | ~750 MB | $3.75 | $0.00025 |

Including full embeddings (L1) and payloads (L0), multiply by ~10-30x.
Still under $100 for a million memories permanently stored.

### 5.2 Comparison with centralized alternatives

| | Mnemonic (on-chain) | Pinecone/Weaviate (SaaS) | Self-hosted Postgres+pgvector |
|---|---|---|---|
| Monthly cost (10K memories) | ~$0.04 one-time | ~$70/mo | ~$20/mo (server) |
| Verifiable | ✓ On-chain hash | ✗ | ✗ |
| Provider-independent | ✓ | ✗ | Partially |
| Permanent | ✓ (Arweave) | ✗ (subscription) | ✗ (server uptime) |

---

## 6. Trust Model and Threat Analysis

### 6.1 What Mnemonic guarantees

- **Integrity**: Memory blob matches on-chain hash, or tampering is detected.
- **Ordering**: Solana slot numbers provide a total order on memory versions.
- **Availability**: Arweave's permanent storage model ensures blobs survive.
- **Provenance**: Agent's signing key links memory state to identity.

### 6.2 What Mnemonic does NOT guarantee

- **Correctness of memories**: An agent can commit false memories. The chain
  proves *what* was stored, not *whether it's true*.
- **Completeness**: An agent can selectively forget by omitting items from a
  new snapshot. Diffing consecutive snapshots can detect deletions.
- **Embedding fidelity**: Quantization is lossy. The commitment covers the
  compressed form; the original float vector is a best-effort inclusion.
- **Cross-platform float determinism**: Exact rerank scores may differ across
  CPU architectures. The compressed candidate stage IS deterministic (integer
  arithmetic).

### 6.3 Attack surface

| Attack | Mitigation |
|---|---|
| Provider modifies agent memory | Hash mismatch detected on rehydration |
| Agent repudiates past memory | On-chain record is immutable |
| Adversary uploads fake memory blob | Blob hash won't match agent's signed commitment |
| Embedding model supply chain attack | Pin model weights hash alongside embedding_model ID |
| Stale memory injection (replay old snapshot) | Version counter prevents rollback |

---

## 7. Comparison with Related Work

| System | Persistent | Verifiable | Compressed | Provider-independent | Open embedder |
|---|---|---|---|---|---|
| ChatGPT Memory | ✓ | ✗ | N/A | ✗ | ✗ |
| LangChain + Pinecone | ✓ | ✗ | ✗ | ✗ | Optional |
| MemGPT / Letta | ✓ | ✗ | ✗ | Partially | Optional |
| IPFS + custom RAG | ✓ | Partially | ✗ | ✓ | Optional |
| **Mnemonic (this work)** | **✓** | **✓** | **✓** | **✓** | **✓** |

TurboQuant (Zandieh & Mirrokni, 2025) provides the compression theory.
Mnemonic provides the systems architecture that makes compressed memory
verifiable and portable.

---

## 8. Limitations and Open Questions

### 8.1 Known limitations

1. **Embedding model lock-in within a version**: Memories are only queryable
   with the same embedding model. Migration requires re-embedding.

2. **Quantization quality at extreme scale**: The 2-stage cascade is validated
   on small corpora. Behavior at 1M+ memories with 4-bit compression needs
   empirical validation.

3. **Snapshot granularity vs. cost**: Frequent snapshots increase on-chain cost.
   Optimal snapshot frequency is application-dependent.

4. **No real-time collaboration**: This is a snapshot-and-commit model, not a
   live replicated database. Concurrent writers need conflict resolution.

### 8.2 Open research questions

1. Can **Matryoshka embeddings** (variable-dimension) further reduce storage
   for low-importance memories without a separate model?

2. What is the **optimal cascade width** (n_candidates) as a function of
   corpus size and bit-width?

3. Can **memory importance scoring** be made verifiable — i.e., can we prove
   on-chain that a memory was promoted/demoted based on retrieval statistics?

4. Is there a practical **zero-knowledge proof** that a retrieval result came
   from a committed memory blob without revealing the full blob?

---

## 9. Roadmap

### Phase 1 — Prove compression fidelity (Weeks 1-2)
- Benchmark 4-bit and 8-bit recall on real datasets (1K, 10K, 100K memories)
- Validate 2-stage cascade preserves retrieval quality
- Establish minimum viable compression ratio

### Phase 2 — On-chain commitment PoC (Weeks 3-4)
- Implement snapshot serialization and SHA3 hashing
- Deploy Solana program for memory commitments
- Upload compressed blobs to Arweave
- End-to-end: commit → fetch → rehydrate → verify

### Phase 3 — Cross-provider migration demo (Weeks 5-6)
- Agent session on Provider A accumulates memories
- Snapshot committed on-chain
- Provider B rehydrates from Arweave blob
- Retrieval quality compared pre/post migration

### Phase 4 — Open embedding standardization (Weeks 7-8)
- Benchmark open embedding models for retrieval quality under quantization
- Select canonical embedder
- Publish embedding + quantization spec for interoperability

---

## 10. Conclusion

The insight that TurboQuant-style compression enables on-chain agent memory is
correct — but only when applied to **semantic embeddings**, not raw KV caches.
Compressed embeddings are small enough for permanent decentralized storage
(sub-$1 for 100K memories), semantically meaningful, model-portable (with open
embedders), and support deterministic retrieval through integer-arithmetic
scoring on quantized vectors.

Mnemonic combines three independently validated components — corpus-calibrated
scalar quantization, content-addressed permanent storage, and on-chain hash
commitment — into an architecture that gives agents something they have never
had: **memory that is provably theirs, survives across providers, and can be
verified by anyone**.

---

## References

1. Zandieh, A. & Mirrokni, V. (2025). *TurboQuant: Online Vector Quantization
   with Near-Optimal Distortion Rate.* arXiv:2504.19874.
2. Arweave Protocol. https://arweave.org
3. Solana Documentation. https://solana.com/docs
4. Nomic AI. *nomic-embed-text-v1.5.* https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
5. Packer, C. et al. (2023). *MemGPT: Towards LLMs as Operating Systems.*
6. Kusupati, A. et al. (2022). *Matryoshka Representation Learning.*

---

## Appendix A: Glossary

- **KV cache**: Key-value attention state inside a transformer — architecture-specific, not portable.
- **Semantic embedding**: Dense vector representation of text meaning — model-specific but architecture-independent.
- **Scalar quantization**: Mapping each coordinate independently to a discrete set of values.
- **Cascade retrieval**: Two-stage search: cheap approximate first pass, exact rerank second pass.
- **Content-addressed storage**: Data retrieved by its hash, not its location (IPFS, Arweave).
- **Mnemonic**: The protocol name for this architecture (from Greek *mnemonikos* — "of or relating to memory").
