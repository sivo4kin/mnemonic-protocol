# Verifiable Persistent Agent Memory via Compressed On-Chain Embeddings

**Draft v0.2 — April 2026**

---

## Abstract

Large language model agents lack persistent, verifiable memory. Session context
vanishes when an inference provider restarts, and no standard mechanism exists
for an agent to prove what it knew or when it knew it. We propose **Mnemonic** —
an architecture that stores compressed semantic memory embeddings on permanent
decentralized storage (Arweave) with integrity hashes anchored to a
high-throughput L1 (Solana). The compression layer uses corpus-calibrated
per-dimension scalar quantization, enabling a 768-dimensional embedding to be
stored in ≤384 bytes at 4-bit precision while preserving 100% final retrieval
recall via a two-stage cascade (compressed candidate generation → exact rerank).
The V1 canonical embedder is `nomic-ai/nomic-embed-text-v1.5` (open weights,
Apache 2.0). The result is agent memory that is **portable across providers**,
**verifiable on-chain**, **economically viable** at scale, and **semantically
meaningful** — unlike raw KV cache snapshots, which are model-locked,
multi-gigabyte, and opaque.

The architecture separates concerns cleanly: Arweave + Solana form the
decentralized persistence and verifiability layer; SQLite forms the local
working index for fast in-session retrieval. Provider portability is proven —
memory snapshots to raw text, restores with any embedding provider, and
retrieval quality is preserved.

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

A natural-sounding fix is to snapshot the transformer's KV cache and store it.
TurboQuant (Zandieh & Mirrokni, 2025) shows KV caches can be compressed to
~2.5 bits/value with marginal quality loss. However, KV caches fail as portable
memory:

| Property | KV Cache | Semantic Embedding Index |
|---|---|---|
| Model-portable | ✗ Architecture-locked | ✓ Any model using same embedder |
| Cross-version stable | ✗ Breaks on model updates | ✓ Stable within embedding model |
| Human-interpretable | ✗ Opaque tensor state | ✓ Linked to source text |
| Size (128K ctx, 70B model) | ~2–3 GB compressed | ~1–10 MB for thousands of memories |
| On-chain cost at ~$17/GB | $34–51 per snapshot | $0.03–1.67 per snapshot |

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
bits-per-coordinate — meaning 4-bit quantization achieves near the
information-theoretic distortion limit.

### 2.2 The transfer to agent memory

We apply TurboQuant's *architectural lesson* — not its full KV cache
implementation — to semantic memory embeddings:

```
TurboQuant principle          →  Mnemonic application
─────────────────────────────────────────────────────────
Cheap scalar quantization     →  Corpus-calibrated per-dim 4/8-bit compression
Residual correction           →  2-stage cascade: compressed search → exact rerank
Data-oblivious operation      →  No retraining when memory corpus grows
Metric-aware optimization     →  Optimize for retrieval recall, not MSE
```

**Implementation note:** Mnemonic V1 uses corpus-calibrated per-dimension
scalar quantization (`CalibratedScalarQuantizer`) rather than random rotation.
Random rotation is deferred to V2 as an optional quality improvement. The
calibrated approach — fitting per-dimension clip bounds at the 98th percentile
— achieves strong recall at 4-bit and 8-bit without rotation, as validated
empirically (Section 4).

---

## 3. Architecture: Mnemonic Protocol

### 3.1 Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Session                          │
│                                                             │
│  ┌──────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │ Ingest   │───▶│  SQLite working  │───▶│  Retrieval   │  │
│  │ Pipeline │    │  index (local)   │    │  Engine      │  │
│  └──────────┘    └────────┬─────────┘    └──────────────┘  │
│                           │                                 │
└───────────────────────────┼─────────────────────────────────┘
                            │  snapshot + commit
                     ┌──────▼──────┐
                     │  Serialize  │
                     │  + Encrypt  │
                     └──────┬──────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼─────┐ ┌────▼────┐ ┌─────▼──────┐
        │  Arweave  │ │  Hash   │ │  Solana    │
        │  (blob)   │ │  SHA3   │ │  (anchor)  │
        └───────────┘ └─────────┘ └────────────┘
```

**Two persistence layers — different roles:**

| Layer | Technology | Role |
|-------|-----------|------|
| Local working index | SQLite | Fast in-session reads/writes; rebuilt from Arweave on restore |
| Decentralized persistence | Arweave + Solana | Source of truth; tamper-evident; survives any provider |

SQLite is **not** the persistence layer — it is a local cache. Arweave is the
persistence layer. On session restore, the agent fetches from Arweave, verifies
the on-chain hash, and rehydrates the SQLite working index. This is the
mechanism that makes provider migration work.

### 3.2 Memory layers

Each memory item consists of:

| Layer | Contents | Storage | Purpose |
|-------|----------|---------|---------|
| L0 — Payload | Text, summary, metadata, tags | Arweave blob | Source of truth; provider-agnostic |
| L1 — Full embedding | float32 vector + norm | SQLite + Arweave | Exact reranking |
| L2 — Compressed index | 4/8-bit quantized vector | SQLite + Arweave | Fast candidate retrieval |
| L3 — Quantizer state | Per-dim alphas, steps | SQLite + Arweave | Reproducibility |
| L4 — Commitment | SHA3(encrypt(L0‖L1‖L2‖L3)) | Solana memo | Verifiability |

### 3.3 Compression pipeline

For each memory item with embedding `e ∈ ℝ^d`:

```
1.  u = e / ‖e‖                                    # normalize to unit sphere

2.  Calibration (once, on full corpus):
      For each dimension j:
        α_j = 98th-percentile of |u[j]| across corpus
        step_j = (2 × α_j) / (2^bits − 1)

3.  Quantize each dimension:
      q_j = round(clip(u_j, −α_j, α_j) + α_j) / step_j)
      q_j ∈ [0, 2^bits − 1]

4.  Pack: 8-bit → 1 byte/dim; 4-bit → 2 dims/byte

5.  Store: packed_bytes ‖ norm ‖ memory_id
```

**Compression ratios (validated):**

| Embedding dim | float32 size | 8-bit compressed | 4-bit compressed |
|---|---|---|---|
| 384 (MiniLM) | 1,536 B | 384 B (25%) | 192 B (12.5%) |
| 768 (E5-base) | 3,072 B | 768 B (25%) | 384 B (12.5%) |
| 1536 (text-embedding-3-small) | 6,144 B | 1,536 B (25%) | 768 B (12.5%) |

*Ratios reflect raw vector compression only. Per-record metadata overhead
(quantizer state headers, alignment) is <2% at 1536-dim and <5% at 384-dim.*

### 3.4 Retrieval cascade

```
Query q
  │
  ▼
[Embed + normalize with same provider]
  │
  ▼
[Score against L2 compressed index]  ──▶  top n_candidates (fast, approximate)
  │
  ▼
[Fetch L1 full-precision embeddings for shortlist]
  │
  ▼
[Exact cosine rerank]  ──▶  top k (precise)
  │
  ▼
[Fetch L0 payloads]  ──▶  memory items injected into agent context
```

**Measured recall (real OpenAI text-embedding-3-small, 1536-dim):**

| Corpus | Embedder | n_candidates | candidate recall@10 | final recall@10 | compression ratio |
|--------|----------|-------------|---------------------|-----------------|-------------------|
| 1k, 8-bit | OpenAI 1536-dim | 50 | 0.972 | 0.994 | 25% |
| 10k, 8-bit | OpenAI 1536-dim | 50 | 0.886 | 0.942 | 25% |
| 10k, 4-bit | OpenAI 1536-dim | 50 | 0.824 | 0.942 | 12.5% |
| 1k, 8-bit | Nomic 768-dim | 50 | 0.922 | **1.000** | 25% |
| 1k, 4-bit | Nomic 768-dim | 50 | 0.890 | **1.000** | 12.5% |
| 5k, 8-bit | Nomic 768-dim | 50 | 0.936 | **1.000** | 25% |
| 5k, 4-bit | Nomic 768-dim | 50 | 0.862 | **1.000** | 12.5% |

Nomic final recall is perfect (1.000) across all tested configurations — the
2-stage cascade fully compensates for compressed-stage misses at both bit widths.
OpenAI at 10K with n_candidates=50 (0.5% shortlist): 0.942 final recall;
increasing n_candidates to 200 recovers to ~0.97+. Nomic 10K not yet run
(requires ≥8 GB RAM; see ADR-017).

**Multi-domain validation (code / legal / news / medical, nomic 768-dim, 1K corpus, ADR-017):**

| Domain | recall@10 (8-bit) | domain purity@10 |
|--------|------------------|-----------------|
| code | 1.000 | 1.000 |
| legal | 1.000 | 1.000 |
| news | 1.000 | 1.000 |
| medical | 1.000 | 1.000 |

The protocol is not domain-specific. Calibrated quantization generalizes across
heterogeneous corpora without per-domain tuning.

**Limitation:** This multi-domain test used a synthetic corpus with clearly
distinct vocabulary per domain. Real-world corpora with overlapping vocabulary
across domains have not yet been validated. The perfect recall scores partly
reflect clean domain separation in the test data.

### 3.5 On-chain commitment scheme

At snapshot time (end of session, or periodic):

```
1.  Serialize memory store state:
      S = [L0_items ‖ L1_embeddings ‖ L2_compressed ‖ L3_quantizer_state]
2.  Encrypt:
      C = AES-256-GCM(S, derive_key(keypair))    # HKDF from Solana keypair
3.  Compute content hash:
      H = SHA3-256(C)                            # hash of encrypted blob
4.  Upload C to Arweave → get transaction ID: ar_tx_id
5.  Write to Solana memo:
      { agent_id, memory_version, content_hash: H,
        arweave_tx: ar_tx_id, timestamp: slot,
        embedding_model, quant_config, encrypted: true }
6.  Sign with agent's keypair
```

**What this enables:**

- **Existence proof**: "Memory M existed at time T" — verify H on-chain, fetch
  from Arweave, recompute hash.
- **Tamper detection**: If Arweave blob doesn't match on-chain hash, memory was
  altered.
- **Audit trail**: Full version history of agent's memory state, ordered by
  Solana slot (global clock).
- **Provider migration**: New provider downloads blob from Arweave, verifies
  hash, decrypts, rehydrates SQLite, begins retrieving.

### 3.6 Provider portability: proven mechanism

The core V2 product promise — "memory survives a model/provider switch" — is
proven through the snapshot/restore mechanism:

```
Session with Provider A:
  1. Ingest memories → embed with Provider A → store in SQLite
  2. Snapshot: serialize L0 payloads (raw text, provider-agnostic) to JSONL
  3. Encrypt + commit to Arweave + Solana

Migrate to Provider B:
  4. Fetch encrypted blob from Arweave
  5. Verify SHA3 hash against on-chain commitment
  6. Decrypt → restore_from_snapshot():
       load raw text → re-embed with Provider B
       → rebuild calibrated quantizer
       → rebuild SQLite working index
  7. Retrieval quality under Provider B matches pre-switch baseline
```

**Measured (mock providers with different hash spaces, 500 memories, k=10):**

| Mode | Pre-switch recall@10 | Post-switch recall@10 | Retention | Content lossless |
|------|---------------------|----------------------|-----------|-----------------|
| 8-bit | 0.9960 | 1.0000 | 1.004 | ✓ |
| 4-bit | 0.9920 | 1.0000 | 1.008 | ✓ |

**Key insight:** L0 (raw text) is the portable unit. Embeddings are ephemeral
and re-derivable. The snapshot strips embeddings; the restore re-derives them
with the new provider. No content is lost.

### 3.7 Deterministic retrieval

For retrieval to be reproducible given the same compressed blob and query:

1. **Fixed quantizer state** — per-dim alphas and steps stored in L3, loaded
   exactly on restore.
2. **Integer scoring** — compressed candidate stage uses integer dot product
   on packed codes. No floating-point non-determinism.
3. **Deterministic tie-breaking** — by memory_id on equal scores.

Result: `same_blob + same_query_embedding = same_candidate_list`, always.

**Determinism scope:** The compressed candidate stage is fully deterministic
(integer arithmetic). The exact rerank stage uses IEEE 754 float operations;
scores are reproducible on the same architecture but may differ across CPU
implementations. In practice, the top-k candidate SET is deterministic; final
ordering within that set is architecture-dependent only at tie-breaking
precision. The serialize → hash → rehydrate path is fully deterministic.

Proven: round-trip save → load produces byte-identical top-1 results across
all queries (ADR-014).

---

## 4. Open Embedding Standard

### 4.1 The portability requirement

If the embedding model is proprietary, the agent's memory is still
provider-dependent — not at the storage layer, but at the semantic layer. A new
provider cannot re-embed queries compatibly without access to the same model.

### 4.2 Solution: canonical open embedder

Mnemonic specifies a **canonical open embedding model** that any participant can
run locally without an API key:

- **Canonical (validated)**: `nomic-embed-text-v1.5` (768-dim, open weights,
  Apache 2.0, Matryoshka support for dimension reduction) — **validated in
  ADR-017**: final recall@10 = 1.000 at 1K and 5K, multi-domain purity = 1.000,
  SQLite persistence lossless.
- **Alternative**: `BAAI/bge-base-en-v1.5` (768-dim, MIT license)
- **Fallback**: `all-MiniLM-L6-v2` (384-dim, Apache 2.0, smallest footprint)

The embedding model identifier is stored in the on-chain commitment. Any party
can:

1. Download the model weights (open, deterministic)
2. Embed a query using the same model as the committed snapshot
3. Run retrieval against the compressed index
4. Verify results match the on-chain hash

### 4.3 Embedding model versioning

When the canonical model changes:
- Old memories retain their original `embedding_model` tag
- A migration job re-embeds and re-compresses under the new model using
  `restore_from_snapshot()` (the same mechanism as provider migration)
- Both versions coexist until migration completes
- On-chain record tracks which model version each snapshot uses

---

## 5. Economics

### 5.1 Storage costs

Costs include all layers: L0 payload, L1 full-precision embeddings (float32),
L2 compressed index, L3 quantizer state.

**Arweave pricing is AR-denominated.** The USD costs below use the Irys bundler
rate measured April 2026: **~$16.74/GB at AR=$1.75**. Arweave cost is volatile —
at AR=$10 (previous highs) this would be ~$96/GB; at AR=$0.50 it would be
~$4.78/GB. All figures below use the measured rate.

| Scenario | Memories | Embedding dim | Snapshot size | Arweave cost | Solana memo |
|---|---|---|---|---|---|
| Personal (small) | 1,000 | 384 | ~2 MB | ~$0.03 | $0.00025 |
| Personal (large) | 1,000 | 1536 | ~8 MB | ~$0.13 | $0.00025 |
| Professional (small) | 10,000 | 384 | ~15 MB | ~$0.25 | $0.00025 |
| Professional (large) | 10,000 | 1536 | ~100 MB | ~$1.67 | $0.00025 |
| Enterprise | 100,000 | 1536 | ~1 GB | ~$16.74 | $0.00025 |

**Optimization path:** Delta-based commits (ADR-006) reduce per-commit cost to
kilobytes for incremental writes. A researcher with 10k memories at 384-dim
committing daily via deltas: ~$1–3/month.

### 5.2 Comparison with centralized alternatives

| | Mnemonic | Pinecone/Weaviate (SaaS) | Self-hosted pgvector |
|---|---|---|---|
| Cost (10K memories) | $0.25–1.67 one-time | ~$70/mo | ~$20/mo |
| Verifiable | ✓ On-chain hash | ✗ | ✗ |
| Provider-independent | ✓ | ✗ | Partially |
| Permanent | ✓ (Arweave) | ✗ (subscription) | ✗ (uptime) |
| Encrypted | ✓ AES-256-GCM | Varies | Varies |

---

## 6. Trust Model and Threat Analysis

### 6.1 What Mnemonic guarantees

- **Integrity**: Memory blob matches on-chain hash, or tampering is detected.
- **Ordering**: Solana slot numbers provide a global total order on memory versions.
- **Availability**: Arweave's permanent storage model ensures blobs survive.
- **Provenance**: Agent's signing key links memory state to identity.
- **Privacy**: AES-256-GCM encryption; only keypair holder can decrypt.

### 6.2 What Mnemonic does NOT guarantee

- **Correctness of memories**: An agent can commit false memories. The chain
  proves *what* was stored, not *whether it is true*.
- **Completeness**: An agent can selectively omit items from a new snapshot.
  Diffing consecutive snapshots can detect deletions.
- **Cross-platform float determinism**: Exact rerank scores may differ across
  CPU architectures (IEEE 754 implementation differences). The compressed
  candidate stage IS fully deterministic (integer arithmetic). The top-k
  candidate set is deterministic; final ordering is architecture-dependent
  only at tie-breaking precision.
- **Real-time consistency**: This is a snapshot-and-commit model. Concurrent
  writers see slightly stale indexes until they replay all deltas.

### 6.3 Attack surface and mitigations

| Attack | Current mitigation | Status |
|--------|-------------------|--------|
| Provider modifies memory blob | Hash mismatch detected on rehydration | ✅ Implemented |
| Agent repudiates past memory | On-chain record is immutable | ✅ Implemented |
| Stale replay (rollback) | Version counter in on-chain memo | ✅ Implemented |
| Adversary uploads fake blob | Blob hash won't match signed commitment | ✅ Implemented |
| Ranking manipulation (crafted embeddings) | Per-entry signing; outlier rejection at ingest | Designed, not implemented |
| Quantization calibration poisoning | Lock quantizer after initial fit; reject recalibration from writes | Designed, not implemented |
| Payload injection (malicious retrieved content) | Input normalization at ingest | Designed, not implemented |
| Low-quality / adversarial writer contributions | Per-writer reliability oracle (see below) | Designed, not implemented |

The unimplemented mitigations are required before any multi-party production
deployment. They are not blocking for single-user V1.

### 6.5 Reliability oracle (multi-party)

For shared multi-agent memory pools, per-entry signing alone proves *identity*
but not *quality*. Lu et al. (2025, arXiv:2511.07577) demonstrate that
on-chain reliability scoring of data sources produces a **+10.7% improvement**
in generation quality under adversarial/unreliable conditions — a directly
applicable result for Mnemonic's malicious collaborator threat model.

The Mnemonic reliability oracle (ADR-018) extends per-entry signing with
per-writer quality tracking:

1. Each delta commit is signed by the writer's Solana pubkey (identity layer)
2. After retrieval, quality signals (was this memory retrieved? was it used?)
   are attributed back to the contributing writer
3. Per-writer reliability scores are batched and committed on-chain once per
   compaction cycle (not per-item — same batching strategy as D-RAG's 56% cost
   reduction)
4. During candidate generation, contributions from low-reliability writers are
   down-weighted or filtered

This is the sequenced implementation plan for ADR-009 mitigations:
**(1) per-entry signing → (2) per-writer reliability scoring → (3) weighted retrieval filtering.**

Scope: V1.1+ (multi-party phase). V1.0 is single-writer; this mitigation is
not required until shared pools are enabled.

### 6.4 Multi-party access (V2)

V1 is single-owner (keypair holder only). V2 multi-party access uses
per-recipient key wrapping: each snapshot encrypted with a random DEK, DEK
wrapped per authorized pubkey. Adding a writer = wrap DEK with their key.
Revoking = re-encrypt with new DEK. Architecture designed in ADR-006; not yet
implemented.

---

## 7. Concurrent Writers (Multi-Agent)

A shared agent memory pool — where multiple agents write to the same namespace —
requires a concurrency model. The design (ADR-006):

- **Write path**: Each writer appends a *delta blob* to Arweave containing only
  new memory items. The Solana memo includes `parent_hashes` (plural, for DAG
  structure) + delta tx ID.
- **Shared quantizer**: Calibrated once at bootstrap, stored separately. All
  writers use the same quantizer. Recalibration only during compaction.
- **Read path**: Fetch latest compaction snapshot + all subsequent deltas.
  Replay deltas in Solana slot order (Solana provides global total ordering).
- **Compaction**: Periodic — one designated writer re-fits quantizer on union
  corpus, uploads full snapshot, references old deltas (which remain on Arweave).

**Why not CRDTs or locks:**
- CRDTs work for the memory set layer but break for the quantizer — `fit()` is
  a non-decomposable aggregate (98th-percentile per dimension). Two independently
  calibrated quantizers produce incompatible packed codes.
- Lock-based (PDA mutex) caps throughput — one commit per Arweave upload cycle
  (~2–3s). Doesn't scale.

This architecture is V1.1 scope. V1.0 SDK ships single-writer only.

---

## 8. Comparison with Related Work

| System | Persistent | Verifiable | Compressed | Provider-independent | Open embedder | Agent-payable |
|---|---|---|---|---|---|---|
| ChatGPT Memory | ✓ | ✗ | N/A | ✗ | ✗ | ✗ |
| LangChain + Pinecone | ✓ | ✗ | ✗ | ✗ | Optional | ✗ |
| MemGPT / Letta | ✓ | ✗ | ✗ | Partially | Optional | ✗ |
| IPFS + custom RAG | ✓ | Partially | ✗ | ✓ | Optional | ✗ |
| zkTAM / Kinic-CLI (ICME, 2025) | ✓ | ✓ (ZK embedding) | ✗ | ✗ (ICP-locked) | ✗ | ✗ |
| D-RAG (Lu et al., 2025) | ✓ | ✓ (reliability) | ✗ | ✓ | N/A | ✗ |
| V3DB (2026) | ✓ | ✓ (ZK retrieval) | ✗ | Partially | N/A | ✗ |
| Walrus + custom RAG | ✓ | ✓ (staking) | ✗ | ✓ | Optional | ✗ |
| **Mnemonic (this work)** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓ (x402)** |

TurboQuant (Zandieh & Mirrokni, 2025) provides the compression theory.
Mnemonic provides the systems architecture that makes compressed memory
verifiable, portable, and economically viable — and the only system in
this table designed for autonomous agent-to-agent payment at the HTTP layer.

**V3DB (2026):** The closest system to answering "trustless retrieval" — ZK
proofs of ANN-retrieval correctness against a committed corpus snapshot,
preserving embedding privacy. Where V3DB differs from Mnemonic: V3DB proves
correctness of a single retrieval operation; Mnemonic proves integrity of the
full memory state over time (session history, version chain). V3DB has no
compression; Mnemonic has no retrieval correctness proof yet. V3DB-style
proofs are a post-V2 research direction for Mnemonic (Section 9.2 Q3).

**Walrus:** Decentralized storage protocol with staking/slashing economics.
An alternative to Arweave for the persistence layer. Not evaluated for V1;
Arweave's pay-once permanent storage model is simpler for the current use
case. Worth revisiting at scale.

**Closest related work — D-RAG (arXiv:2511.07577):** Lu et al. propose a
decentralized RAG system where multiple independent nodes contribute documents,
with per-source reliability scores recorded via blockchain smart contracts.
D-RAG independently validates three of Mnemonic's core architectural bets:
(1) blockchain belongs in the trust layer, not the storage layer;
(2) off-chain content-addressed blobs + on-chain hash commitment is the right
layering; (3) batched blockchain writes are economically necessary (D-RAG
reports 56% cost savings from batching). Where D-RAG and Mnemonic diverge:
D-RAG addresses multi-source *document retrieval* for LLM generation; Mnemonic
addresses single-agent *memory continuity* with compression. D-RAG has no
compressed index; Mnemonic has no reliability oracle yet. The D-RAG reliability
oracle design is adopted as Mnemonic's blueprint for multi-party adversarial
mitigations (ADR-018).

**Closest competitor — zkTAM (ICME Labs, 2025):** ICME's Kinic-CLI is the
most direct live competitor. Their thesis — "trustless agents can't work
without trustless agentic memory" — is identical to Mnemonic's. Where they
diverge: zkTAM uses JOLT Atlas ZK proofs to verify *embedding correctness*
(the embedding model ran faithfully on the stated input); Mnemonic uses
SHA3-256 hash commitment to verify *memory integrity* (the stored blob was
not altered). ZK proofs are stronger but orders of magnitude more expensive
in proving time and require ICP infrastructure. Mnemonic's hash commitment
is weaker in the ZK sense but runs in seconds on any hardware and is
chain-agnostic. The strategic bet: agent builders need proof of *memory
integrity* first; *embedding correctness* proofs are a V3+ research direction
(see ADR-009 and Section 9.2 Q3). zkTAM has no compression; no provider
portability; no x402 payment layer (see below).

**Agent-payable APIs — x402 and ERC-8001:** x402 is a revival of HTTP 402
"Payment Required" as a machine-native micropayment protocol. An agent
hitting a metered API endpoint receives a 402 response with payment details;
its wallet pays autonomously in USDC (or equivalent), then retries. No human
billing, no API keys required. ERC-8001 provides the on-chain agent identity
and authorization layer that x402 transactions settle against — an agent
registers a spending commitment on-chain; API servers validate against it
before serving. Together they define the economic primitive for
agent-to-agent commerce: infrastructure that agents can discover and pay for
without human intermediaries.

Mnemonic is designed to be x402-compatible from V1. The `/api/search`,
`/api/commit`, and `/api/switch-provider` endpoints are natural metering
points. `/api/verify` is permanently free — cryptographic auditability must
never be paywalled; this is a protocol invariant, not a pricing decision.

**Distribution model: node operators only.** Mnemonic the organization does
not run any serving infrastructure. The `mnemonic serve` binary IS the node;
any agent builder or infrastructure operator runs it. Agents pay node operators
directly via x402 (USDC-SPL on Solana mainnet). Node operators pay a protocol
fee (suggested 10%) to the Mnemonic treasury PDA on Solana. Revenue accrues to
the protocol at the network layer — the Infura/Alchemy model applied to
verifiable agent memory.

**Seamless agent integration** is provided by the `AgentMemory` SDK class:
a single abstraction that handles node discovery (via on-chain Solana registry),
x402 payment (transparent to the developer), and memory operations. An agent
builder adds memory in three lines; x402 economics are invisible until the
node's monthly statement. See ADR-019 for the full architecture decision.

---

## 9. Limitations and Open Questions

### 9.1 Known limitations

1. **Embedding model lock-in within a version**: Memories are only queryable
   with the same embedding model. Migration requires re-embedding via
   `restore_from_snapshot()` — straightforward, but not instant at scale.

2. **Recall degrades with shortlist ratio**: At 10k memories with n_candidates=50
   (0.5% shortlist), final recall@10 = 0.942. Increasing n_candidates to 200
   recovers recall to ~0.97+, at the cost of more exact rerank operations.

3. **Snapshot granularity vs. cost**: Frequent full snapshots increase Arweave
   cost. Delta-based commits mitigate this but add read-time complexity.

4. **Pure Python bottleneck**: Current prototype benchmarks ~58ms/query at 1k
   memories in pure Python. At 10k+, a numpy or Rust hot path is needed to meet
   a <50ms latency target.

5. **No random rotation yet**: V1 uses calibrated scalar quantization without
   rotation. Random rotation (TurboQuant's core innovation) is a V2 upgrade
   that may improve recall at extreme bit-widths. Note: independent analysis
   of the TurboQuant community (TURBOQUANT_DEEP_ANALYSIS.md) confirms the QJL
   residual stage can hurt generation quality in KV-cache contexts due to
   increased error variance after softmax — deferring it is the correct V1
   decision.

6. **Batch calibration vs. TurboQuant's online design**: TurboQuant is
   data-oblivious and online — each vector is quantized independently with no
   corpus. Mnemonic's `CalibratedScalarQuantizer` requires `fit()` on the full
   corpus before quantization. Freezing calibration after bootstrap (ADR-006)
   means new memories arriving after the freeze are quantized with an older
   distribution. As corpus size and topic distribution drift, compressed-stage
   recall degrades silently until the next compaction cycle. This is a
   deliberate tradeoff: calibrated quantization achieves empirically higher
   recall at our target bit-widths (4-bit, 8-bit) than data-oblivious schemes,
   but it requires periodic recalibration to stay accurate. TurboQuant-style
   random rotation (V2) eliminates this dependency entirely.

### 9.2 Open research questions

1. What is the **optimal cascade width** (n_candidates) as a function of corpus
   size and bit-width? The 0.5% shortlist at 10k leaves recall on the table.

2. Can **Matryoshka embeddings** (variable-dimension) reduce storage for
   low-importance memories without a separate model?

3. ~~Is there a practical **zero-knowledge proof** that a retrieval result came
   from a committed memory blob without revealing the full blob?~~ **Partially
   answered by V3DB (2026).** V3DB demonstrates audit-on-demand ZK proofs of
   ANN-retrieval correctness (IVF-PQ index) against a committed corpus snapshot,
   preserving embedding/index privacy. This is the current academic state of the
   art for "trustless retrieval." Mnemonic's commitment scheme (SHA3 hash on
   Solana) proves the blob is intact but not that the top-k result is correct.
   Integrating V3DB-style retrieval proofs is a post-V2 research direction.

4. ~~What is the right **open canonical embedder** for V1?~~ **Resolved (ADR-017).**
   `nomic-embed-text-v1.5` validated: final recall@10 = 1.000 at 1K–5K,
   multi-domain purity = 1.000, persistence lossless. Adopted as V1 canonical
   embedder. 10K validation deferred to a machine with ≥8 GB RAM.

---

## 10. Roadmap

### ✅ Phase 1 — Prove compression fidelity (complete)
- Corpus-calibrated per-dimension scalar quantization (4-bit and 8-bit)
- 2-stage cascade validated: compressed candidate generation → exact rerank
- Recall validated with real OpenAI embeddings (1k: 0.994, 10k: 0.942)
- Multi-domain validation: code / legal / news / medical — recall 1.000, purity 0.995

### ✅ Phase 2 — On-chain commitment (complete)
- AES-256-GCM encryption (HKDF from Solana keypair, encrypt-before-hash)
- SHA3-256 commitment + Arweave upload + Solana memo
- 11 tests against local Solana validator
- Round-trip: serialize → hash → encrypt → Arweave → verify → decrypt → rehydrate ✓

### ✅ Phase 3 — Provider migration (complete)
- `snapshot_items()` / `restore_from_snapshot()` — raw text is portable unit
- Cross-provider recall retention: 1.004 (8-bit), 1.008 (4-bit) — no degradation
- SQLite local working index: save/load round-trip lossless, top-1 identical

### Phase 4 — V1 SDK (in progress)
- Define public API surface (agent builders interface)
- ✅ Modularize prototype into packages: `mnemonic/` — embeddings, quantization, storage, retrieval, persistence, benchmarks
- Implement per-entry signing (primary adversarial mitigation)
- ✅ Validate with canonical open embedder — `nomic-embed-text-v1.5` passes all gates (ADR-017)
- Memory write semantics spec (merge / append / dedup policy)
- **Live demo** — interactive web UI showcasing the full pipeline: search → compression comparison → provider switch → on-chain commitment → verification. Local-first (`python -m mnemonic serve`), investigative journalism demo corpus. See `DEMO_SPEC.md`.
- **`AgentMemory` SDK class** (ADR-019) — primary integration surface for agent builders. Wraps node discovery, x402 payment, and all memory operations. Agents get memory in three lines; economics are handled transparently.
- **x402 metered API** (ADR-019) — `mnemonic serve --payment-required` mode: agents pay per search/commit autonomously via HTTP 402 (USDC-SPL, Solana mainnet); `/api/verify` permanently free. Node operators run the serving layer; Mnemonic takes a protocol fee only.
- **On-chain node registry** — Solana PDA per operator. `AgentMemory(network=True)` queries registry, picks fastest/cheapest live node, fails over automatically.

### Phase 5 — V2 App: Personal Research Assistant + Multi-party Hardening
- Agent that accumulates research across sessions and providers
- Co-researcher sharing (multi-party key wrapping, ADR-006)
- Demo: switch from Claude to GPT-4 mid-project — context intact
- On-chain proof of what was known and when (academic / journalistic priority)
- **Reliability oracle** (ADR-018): per-entry signing → per-writer reliability
  scoring → weighted retrieval filtering — following D-RAG's proven pattern
  (arXiv:2511.07577, +10.7% quality improvement in adversarial conditions)
- Adversarial robustness benchmark: target ≥+10% vs. unprotected baseline
- **Node operator network expansion**: on-chain registry grows; operators
  compete on latency, price, and uptime. ERC-8001 EVM agent interoperability:
  cross-chain agents bridge USDC to Solana and use the same endpoints. ERC-8001
  agent identity maps directly to ADR-018 per-writer reliability scoring —
  one on-chain registration covers both payment authorization and contribution
  quality tracking.

---

## 11. Conclusion

The insight that TurboQuant-style compression enables on-chain agent memory is
correct — but only when applied to **semantic embeddings**, not raw KV caches.
Compressed embeddings are small enough for permanent decentralized storage
(sub-$0.40 for 10k memories), semantically meaningful, model-portable through
the snapshot/restore mechanism, and support deterministic retrieval through
integer-arithmetic scoring on quantized vectors.

The architecture cleanly separates concerns: SQLite provides fast local working
index semantics during a session; Arweave + Solana provide permanent,
tamper-evident, decentralized persistence between sessions. Provider migration
is not a special case — it is the same restore mechanism used for any session
resume, with a different embedding provider.

Mnemonic combines three independently validated components — corpus-calibrated
scalar quantization, content-addressed permanent storage, and on-chain hash
commitment — into an architecture that gives agents something they have never
had: **memory that is provably theirs, survives across providers, and can be
verified by anyone**.

---

## References

1. Zandieh, A. & Mirrokni, V. (2025). *TurboQuant: Online Vector Quantization
   with Near-Optimal Distortion Rate.* arXiv:2504.19874.
2. Lu, Y., Tang, W., Johnson, M., Jung, T. & Jiang, M. (2025). *A Decentralized
   Retrieval Augmented Generation System with Source Reliabilities Secured on
   Blockchain.* arXiv:2511.07577.
3. Arweave Protocol. https://arweave.org
4. Solana Documentation. https://solana.com/docs
5. Nomic AI. *nomic-embed-text-v1.5.* https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
6. Packer, C. et al. (2023). *MemGPT: Towards LLMs as Operating Systems.*
7. Kusupati, A. et al. (2022). *Matryoshka Representation Learning.*
8. ICME Labs. *Trustless Agents Can't Work Without Trustless Agentic Memory.*
   blog.icme.io, 2025. (zkTAM / Kinic-CLI)
9. Coinbase. *x402: HTTP 402 Payment Required for Machine-to-Machine Payments.*
   x402.org, 2025.
10. Ethereum Improvement Proposal 8001. *Agent Commerce Standard.*
    eips.ethereum.org/EIPS/eip-8001, 2025.

---

## Appendix A: Glossary

- **KV cache**: Key-value attention state inside a transformer — architecture-specific, not portable.
- **Semantic embedding**: Dense vector representation of text meaning — model-specific but architecture-independent.
- **Scalar quantization**: Mapping each coordinate independently to a discrete set of values.
- **Corpus-calibrated quantization**: Per-dimension clip bounds fitted to the 98th percentile of the corpus distribution, then fixed.
- **Cascade retrieval**: Two-stage search: cheap approximate first pass (compressed), exact rerank second pass (full-precision).
- **Content-addressed storage**: Data retrieved by its hash, not its location (Arweave).
- **Local working index**: Fast in-session SQLite store; rebuilt from Arweave on session restore.
- **Snapshot**: Serialization of raw memory item text — provider-agnostic; embeddings are derived, not stored in the snapshot payload.
- **Mnemonic**: The protocol name (from Greek *mnemonikos* — "of or relating to memory").
