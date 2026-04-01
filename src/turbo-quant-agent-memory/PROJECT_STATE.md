# PROJECT_STATE.md

## Project

`turbo-quant-agent-memory`

## One-line summary

Verifiable and non-censored shared agent memory system — V1 is infrastructure, V2 is infrastructure + a consumer app.

## Product definition

### What it is
A verifiable and non-censored shared agent memory system. Infrastructure that any agent or agent network can use to store and retrieve context across sessions.

### Who it's for
Two simultaneous audiences:
- **Agent builders** — SDK/API consumers who wire memory into their agent pipelines
- **Non-technical users** — who interact with a V2 app that happens to use agents with shared memory under the hood

### What the user buys
Verifiable and non-censored agent memory layout. Not just storage — proof that memory wasn't tampered with, and no platform can censor or revoke it.

### The wedge
Any agent (or agent network) that needs shared context. The first paying use case will be built as a concrete agent application where shared memory produces clear user value.

### V1 vs V2
- **V1** — infrastructure only: memory store, quantized retrieval, on-chain commitment, SDK
- **V2** — infrastructure + a Personal Research Assistant app (see ADR-011)

### V2 app: Personal Research Assistant (chosen)
An agent that accumulates research across sessions. Memory survives model switches and provider changes. Co-researchers can be invited into a shared memory pool. On-chain proof of what was known and when.

**Target users:** Independent researchers, investigative journalists, PhD students, analysts.
**Demo moment:** Switch from Claude to GPT-4 mid-project — your research context is intact. Add a co-author — they see everything you discovered.
**Other candidates evaluated:** Developer institutional memory agent (Option B), Sovereign personal AI (Option C) — see ADR-011 for full analysis. Option B is the natural second vertical.

### First paying customer model
A researcher using the V2 app who gets clear value from: (a) context surviving session resets and model switches, and (b) being able to share a research pool with a collaborator.

---

## Current phase

**V1 development. All retrieval gates passed. Live demo is the next V1 deliverable.**

All architecture, design, and validation work is done. SQLite persistence, multi-domain recall, provider portability, encryption, security model, agent loop, and concurrent writers design are all closed. Real OpenAI embeddings at 10k scale passed (ADR-016). Canonical open embedder (`nomic-embed-text-v1.5`) validated (ADR-017) — final recall@10 = 1.000 at 1K–5K, adopted as V1 reference embedder. Prototype modularized into `mnemonic/` package.

**Next:** V1 live demo — interactive web UI demonstrating the full pipeline (search → compression comparison → provider switch → on-chain commitment → verification). See `DEMO_SPEC.md`.

## Source of truth

The current project context was reconstructed from files created in a prior web chat session.
Within this environment, the source of truth is:
- `src/turbo-quant-agent-memory/*`
- `research/turbo-quant-agent-memory/*`

## Project thesis

Two interlocking questions:

> 1. Can a compressed shadow index reduce storage cost while preserving retrieval quality well enough through exact reranking?
> 2. Can on-chain commitment make agent memory verifiable and tamper-evident without killing usability?

The project intentionally does **not** begin with full TurboQuant complexity.
Instead, it extracts the architectural lesson:
- compress broadly
- recover precision narrowly
- keep full-precision vectors as the correctness layer
- commit state on-chain so any reader can verify it wasn't altered

## Architecture summary

### Ingestion
1. ingest memory item
2. generate embedding
3. normalize embedding
4. quantize normalized embedding
5. store:
   - memory payload + metadata
   - full-precision embedding
   - compressed representation
   - quantization diagnostics

### Retrieval
1. embed query
2. normalize query
3. score against compressed shadow index
4. shortlist top `n_candidates`
5. fetch full-precision embeddings for shortlisted candidates
6. exact rerank
7. return final top `k`

## What's been built

### Retrieval layer (`mnemonic/` package)
- in-memory memory store (`store.py`)
- full-precision embedding storage
- quantized shadow index (`quantizer.py`)
- normalized vector retrieval (`retriever.py`)
- corpus-calibrated per-dimension scalar quantization (4-bit and 8-bit)
- compressed candidate retrieval + exact reranking
- mock embedding provider (salted hash space — two instances simulate two different providers)
- OpenAI embedding provider (batched, retry with exponential backoff — ADR-015)
- Nomic embedding provider (`nomic-embed-text-v1.5`, 768-dim, open weights — ADR-017)
- local embedding cache (`cache.py`)
- synthetic dataset generation + JSONL dataset ingestion (`persistence.py`)
- benchmark mode + JSON result export (`benchmark.py`)
- snapshot (raw items → provider-agnostic JSONL, no embeddings)
- restore from snapshot (re-embed with any provider, rebuild quantized index)
- provider-switch test (ingest with A → snapshot → restore with B → compare recall)
- CLI entry point (`__main__.py`): demo, benchmark, persist-test, multidomain, provider-switch

### Agent integration (`agent_loop.py`)
- reactive agent loop: retrieve → form context → store per turn
- episodic / semantic / decision memory types with importance scoring
- periodic index rebuild (every 3 ingestions + on-demand before retrieval)
- 20-turn multi-topic demo scenario

### On-chain commitment (`onchain/commit.mjs`)
- AES-256-GCM encryption (HKDF from keypair, encrypt-before-hash)
- SHA3-256 hash of encrypted blob
- Arweave upload (encrypted content-addressed storage)
- Solana memo commitment (hash + metadata, fully public)
- Decrypt + verify round-trip
- 11 tests against local Solana validator (`test-local.mjs`)

### Performance (`bench_latency.py`)
- per-stage latency instrumentation (Stage 1: compressed scan, Stage 2: exact rerank)
- numpy acceleration path (matrix multiply scoring, vectorized quantization)
- benchmarked: pure Python ~58ms/query at 1k memories; numpy path available for 10k+

### Designed but deferred
- Concurrent writers: event-sourced delta log + shared quantizer + Solana ordering (ADR-006, V1.1 scope — V1.0 is single-writer)
- Memory eviction: pluggable policy, case-specific (ADR-007)
- Multi-party key access: per-recipient key wrapping (ADR-006)

## Implementation note

The prototype uses **corpus-calibrated per-dimension scalar quantization**
(`CalibratedScalarQuantizer` with per-dimension `alphas[]` and `steps[]`).

As of 2026-03-29, the docs (ARCHITECTURE.md, SCHEMA.md, MVP_SPEC.md) have been
updated to reflect this. The previous references to "global symmetric" quantization
with a single `clip_alpha` have been corrected.

## Main artifacts

### In `src/turbo-quant-agent-memory/`
- `mnemonic/` — modular Python package (see below)
- `pseudocode.py` — original monolith (superseded by `mnemonic/` package)
- `agent_loop.py` — real agent integration loop
- `bench_latency.py` — per-stage latency benchmarks, numpy acceleration path
- `mvp_verify.py` — serialization round-trip verification
- `generate_real_corpus.py` — realistic multi-topic dataset generator
- `ARCHITECTURE.md` — design principles and failure modes
- `MVP_SPEC.md` — goals, success criteria, security model
- `PROJECT_STATE.md` — this file
- `SCHEMA.md` — data model for persistence
- `ADR.md` — all architecture decisions (ADR-001 through ADR-017)
- `BLOCKERS.md` — full blocker analysis (product + technical)
- `DEMO_SPEC.md` — V1 live demo specification (5-act narrative, web UI, implementation plan)

### In `src/turbo-quant-agent-memory/mnemonic/`
- `__init__.py` — public API exports
- `__main__.py` — CLI entry point (demo, benchmark, persist-test, multidomain, provider-switch)
- `models.py` — MemoryItem, EmbeddingRecord, QuantizedRecord, SearchResult
- `math_utils.py` — dot, l2_norm, normalize, clip
- `cache.py` — EmbeddingCache (content-hash keyed)
- `embedders.py` — BaseEmbeddingProvider, MockEmbeddingProvider, OpenAIEmbeddingProvider, NomicEmbeddingProvider
- `quantizer.py` — CalibratedScalarQuantizer
- `store.py` — MemoryStore
- `indexer.py` — MemoryIndexer
- `retriever.py` — MemoryRetriever
- `persistence.py` — load_jsonl, ingest_memory_jsonl, save_to_sqlite, load_from_sqlite, snapshot_items, restore_from_snapshot
- `benchmark.py` — run_demo, run_benchmark, run_persist_test, run_multidomain_benchmark, run_provider_switch_test

### In `src/turbo-quant-agent-memory/onchain/`
- `commit.mjs` — encrypt + hash + Arweave upload + Solana memo commit
- `encrypt.mjs` — AES-256-GCM encryption module (HKDF, packed format)
- `test-local.mjs` — 11 tests against local Solana validator

### In `research/turbo-quant-agent-memory/`
- `WHITEPAPER.md` — TurboQuant paper analysis
- `MVP_VERIFICATION.md` — verification methodology
- `CONCURRENT_WRITERS.md` — concurrent writers research (ADR-006 basis)

## Key strengths of current design

- clean 2-stage retrieval architecture
- low implementation risk
- keeps exact vectors as safety/correction layer
- compatible with future TurboQuant-like upgrades
- practical benchmarkability
- online-friendly ingestion story

## V1 remaining gates

| # | Gate | Status |
|---|------|--------|
| 1 | **Real embeddings at scale** | ✅ **PASSED** (ADR-016) — 10k memories, OpenAI `text-embedding-3-small` (1536-dim): candidate recall@10=0.886 (8-bit), final recall@10=0.942. Round-trip lossless, hash match. Arweave cost ~$0.39/snapshot. |
| 2 | **Multi-domain corpus recall** | ✅ **PASSED** (ADR-013) — recall@10=1.00, purity@10=0.995 across code/legal/news/medical. |
| 3 | **SQLite persistence** | ✅ **PASSED** (ADR-014) — save/load round-trip lossless, recall retention=1.000, top-1 identical. |

**All three retrieval gates closed.**

### V1 remaining deliverables

| # | Deliverable | Status |
|---|-------------|--------|
| 4 | **Live demo** | 🔲 **TODO** — interactive web UI: search, compression comparison, provider switch, on-chain commit, verify. See `DEMO_SPEC.md`. |
| 5 | **SDK API surface** | 🔲 **TODO** — public interface spec for agent builders. |
| 6 | **Demo corpus** | 🔲 **TODO** — 1000 investigative journalism research memories for demo. |

## What's been built (updated)

### Retrieval layer (`mnemonic/` package — modularized from `pseudocode.py`)
- in-memory memory store
- full-precision embedding storage
- corpus-calibrated per-dimension scalar quantization (4-bit and 8-bit)
- compressed candidate retrieval + exact reranking
- mock embedding provider (salted hash space)
- OpenAI embedding provider (batched, retry with exponential backoff — ADR-015)
- Nomic embedding provider (`nomic-embed-text-v1.5`, 768-dim, open weights — ADR-017)
- local embedding cache
- synthetic dataset generation + JSONL dataset ingestion (batch-aware for OpenAI/Nomic)
- benchmark mode + JSON result export
- snapshot (raw items → provider-agnostic JSONL) + restore from snapshot
- provider-switch test — PASSED (ADR-012)
- multi-domain benchmark (code/legal/news/medical) — PASSED (ADR-013, ADR-017)
- SQLite persistence: `save_to_sqlite` / `load_from_sqlite` — PASSED (ADR-014)
- session persist-test round-trip — PASSED (ADR-014)
- canonical open embedder validation — PASSED (ADR-017): nomic final recall@10 = 1.000 at 1K–5K

## Resolved gaps (reference)

| # | Gap | Resolution |
|---|-----|-----------|
| 3 | Adversarial input research | Security model defined (ADR-009): 4 attack vectors identified, mitigations designed. Implementation deferred to pre-production (not a V1 SDK gate). |
| 5 | Latency profiling | `bench_latency.py` done (ADR-004): pure Python ~58ms/query at 1k. Numpy path identified. Pure Python acceptable through 1k; numpy or Rust needed at 10k+. |
| 6 | Transforms / rotation | Deferred to phase 2 (post-V1). Not needed to prove core thesis. |
| 7 | Multi-party access | Single-owner keypair for V1 by design (ADR-003, ADR-009). Key wrapping path designed for V2. |
| 8 | Concurrent writers | Architecture designed (ADR-006): event-sourced delta log, deferred to V1 SDK phase. |
| 9 | Memory eviction | Pluggable policy design decided (ADR-007). Case-specific. Deferred. |
| 10 | Modularization | Deferred — acceptable for prototype; do alongside SQLite persistence (gate 3). |
| 11 | Docs/implementation sync | Resolved 2026-03-29. |
| 12 | Platform change survivability | Resolved 2026-04-01 (ADR-012): snapshot/restore across different embedding spaces; recall retention 1.004 (8-bit), 1.008 (4-bit); content lossless. |
| 13 | Canonical open embedder | Resolved 2026-04-01 (ADR-017): `nomic-embed-text-v1.5` (768-dim, Apache 2.0) validated — final recall@10 = 1.000 at 1K–5K, multi-domain purity = 1.000, persistence lossless. Adopted as V1 canonical embedder. |
| 14 | Modularization | Resolved 2026-04-01: prototype refactored into `mnemonic/` package with clean module separation (models, embedders, quantizer, store, indexer, retriever, persistence, benchmark). |
