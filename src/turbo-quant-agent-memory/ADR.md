# Architecture Decision Record — Mnemonic

Last updated: 2026-03-31

---

## ADR-001: Solana Local Development Environment

**Date:** 2026-03-31
**Status:** Accepted

**Context:** On-chain commitment pipeline (`commit.mjs`) targeted devnet but had no local testing path. Relying on devnet for development is slow and rate-limited.

**Decision:** Install Solana CLI (v3.1.12 via Anza installer) and use `solana-test-validator` on `127.0.0.1:8899` for all local development and testing.

**Consequences:**
- Tests run offline, no network dependency
- Full test suite (7 original tests) passes against local validator
- Test keypair funded via local airdrop (no real SOL needed)
- `test-local.mjs` supports both `--start-validator` (auto-manage) and standalone mode

---

## ADR-002: Real Agent Integration Loop

**Date:** 2026-03-31
**Status:** Accepted
**Addresses gap:** #6 (no real agent integration)

**Context:** The memory system existed as standalone components (store, indexer, retriever) but nobody had wired them into an actual agent loop. Without this, it was unclear whether the API was practical for real use.

**Decision:** Created `agent_loop.py` — a reactive agent that processes multi-turn conversations using the memory system.

**Design:**
- Each turn: retrieve relevant memories -> form context -> store new memories
- Memory types: episodic, semantic, decision (with importance scoring)
- Index rebuild: on-demand before retrieval + periodic interval (every 3 ingestions)
- Uses `MockEmbeddingProvider` for offline operation
- 20-turn multi-topic scenario covering quantization, agent memory, and blockchain

**Integration points exercised:**
- `MemoryIndexer.ingest_memory()` — every turn
- `MemoryIndexer.rebuild_quantized_index()` — periodic + on-demand
- `MemoryRetriever.retrieve()` — compressed candidates with exact rerank
- `MemoryRetriever.exact_search()` — side-by-side comparison
- `estimate_index_bytes()` and `quant_diagnostics()` — summary stats

**Consequences:**
- Proves the 2-stage retrieval works in a real agent pattern
- Retrieval scores improve as context builds across turns
- API is practical — no ergonomic issues found
- CLI: `python3 agent_loop.py [--turns N] [--bits {4,8}] [--dim DIM]`

---

## ADR-003: Encryption Layer for On-Chain Memory

**Date:** 2026-03-31
**Status:** Accepted
**Addresses gap:** #7 (memory content goes to public storage unencrypted)

**Context:** Memory blobs uploaded to Arweave are permanent and public. Storing agent memory in cleartext on a public ledger is a deal-breaker for any real deployment. The on-chain hash (Solana memo) must match what's stored on Arweave, so encryption must happen before both hashing and uploading.

**Decision:** AES-256-GCM encryption using Node.js built-in `crypto` module. No external dependencies.

**Design:**
- `encrypt.mjs` module with `encryptBlob()` / `decryptBlob()` / `isEncryptedBlob()`
- Key derivation: HKDF (SHA-256) from raw key material (Solana keypair first 32 bytes)
- Packed format: `"MENC"` (4B) + version (1B) + IV (12B) + salt (16B) + tag (16B) + ciphertext
- Total overhead: 49 bytes per encrypted blob
- Hash computed on the **encrypted** blob so on-chain hash matches Arweave content
- Solana memo includes `encrypted: true` flag

**Commit flow with encryption:**
1. Read MNEM blob, validate header
2. Encrypt blob (derive key from keypair via HKDF)
3. Hash the encrypted blob (SHA3-256)
4. Upload encrypted blob to Arweave
5. Commit hash + metadata to Solana (memo includes `encrypted: true`)

**Decrypt flow:**
1. Load `.commitment.json`
2. Fetch encrypted blob (local file or Arweave)
3. Verify hash matches on-chain commitment
4. Decrypt with keypair, validate MNEM header

**Tests added (4):**
- Encrypt/decrypt round-trip (byte-identical)
- Decrypt from commitment matches original
- Wrong key fails with clear error
- Encrypted on-chain commitment pipeline

**Open question:** Multi-party access. Current design is single-owner (keypair holder only). Options discussed but not decided:
1. Shared secret — simple, no revocation
2. Per-recipient key wrapping (PGP/age model) — scalable, revocable
3. On-chain access control via Solana PDAs — composable with smart contracts
4. Threshold/MPC — strongest trust model, most complex

**Consequences:**
- Memory content is private on Arweave (only keypair holder can decrypt)
- On-chain commitment integrity preserved (hash of ciphertext)
- Zero external dependencies (Node.js `crypto` only)
- 49 bytes overhead per blob is negligible
- Multi-party access deferred — revisit when use case is clearer

---

## ADR-004: Latency Benchmarks and Numpy Acceleration

**Date:** 2026-03-31
**Status:** Accepted
**Addresses gap:** #8 (pure Python is slow, need benchmarks)

**Context:** The prototype uses pure Python for all vector math (dot products, quantization, scoring). No latency profiling existed. Need to understand where the bottleneck is and whether it's acceptable.

**Decision:** Created `bench_latency.py` with per-stage instrumentation and optional numpy acceleration path.

**Benchmark results (pure Python, 8-bit, MockEmbeddingProvider):**

| Corpus | Stage 1 p50 | Stage 2 p50 | Total p50 | QPS |
|--------|-------------|-------------|-----------|-----|
| 100    | 5.8ms       | 0.4ms       | 6.5ms     | 154 |
| 1000   | 58.6ms      | 0.5ms       | 59.3ms    | 17  |

**Key findings:**
- Bottleneck is Stage 1 (compressed candidate search): ~58us per memory
- Stage 2 (exact rerank on shortlist) is negligible (~0.5ms for 50 candidates)
- Scales linearly: at 10k memories, expect ~600ms/query in pure Python
- Query embedding time is <0.5ms (mock provider)

**Numpy acceleration path:**
- `numpy_batch_score()` — matrix multiply for scoring query against all vectors
- `numpy_quantize()` — vectorized quantization
- `numpy_score_compressed()` — reconstructed quantized scoring via matmul
- Pre-builds numpy matrices before timed loop
- Available via `--numpy` flag, graceful fallback when numpy unavailable

**Consequences:**
- Pure Python is acceptable for <1k memories (~17 QPS)
- Production path (10k+ memories) needs acceleration
- Numpy provides easy 10-50x speedup for scoring
- Long-term: Rust for production (see ADR-005)
- CLI: `python3 bench_latency.py [--sizes 100,1000,5000] [--bits 8] [--queries 20] [--numpy]`

---

## ADR-005: Production Language — Rust

**Date:** 2026-03-31
**Status:** Proposed (not yet implemented)

**Context:** Latency benchmarks (ADR-004) confirm pure Python bottlenecks at scale. The project needs a production-grade implementation for real deployment.

**Decision:** Production implementation will be in Rust.

**Rationale:**
- SIMD-friendly vector math (dot products, quantization)
- Solana native SDK is Rust
- Memory safety without GC pauses
- Can compile to WASM for client-side use
- `fastdot.c` already proved C-level dot product is viable; Rust gives the same performance with better tooling

**Scope (TBD):**
- Core quantization and scoring engine
- Solana program (on-chain logic, not just memo)
- Binary serialization (MNEM format)
- Encryption (AES-256-GCM via `aes-gcm` crate)

**Not yet decided:**
- Whether to expose Python bindings (PyO3) for gradual migration
- Whether the Rust implementation replaces or wraps the prototype
- Solana program architecture (PDA layout, instruction set)

---

## ADR-006: Concurrent Writers

**Date:** 2026-03-31
**Status:** Research needed
**Addresses gap:** #9

**Context:** What happens when two sessions write to the same agent's memory simultaneously? The current in-memory store has no concurrency controls.

**Open questions:**
- Is last-write-wins acceptable for MVP?
- Should the index rebuild be atomic?
- How does this interact with on-chain commitments? (each commit is a snapshot — no merge)
- CRDT-style merge vs lock-based exclusion?

**Decision:** Deferred. Needs separate research before architecture choice.

---

## ADR-007: Memory Pruning and Eviction

**Date:** 2026-03-31
**Status:** Research needed
**Addresses gap:** #10

**Context:** Memory can't grow forever. Need importance-based eviction to keep the index bounded.

**Open questions:**
- Eviction criteria: importance score? recency? access frequency? combination?
- Should eviction be per-agent or global?
- How does eviction interact with on-chain commitments? (old snapshots reference evicted memories)
- Should evicted memories be archived (Arweave) or truly deleted?
- Is this case-specific (per-deployment policy) or generic?

**Decision:** Deferred. This will be case-specific — different agents need different policies. Architecture should support pluggable eviction strategies.

---

## Summary of artifacts (as of 2026-03-31)

### Source (`src/turbo-quant-agent-memory/`)
| File | Purpose |
|------|---------|
| `pseudocode.py` | Core memory system (810 lines) |
| `agent_loop.py` | Real agent integration demo |
| `bench_latency.py` | Latency benchmarks with numpy path |
| `mvp_verify.py` | Serialization round-trip verification |
| `generate_real_corpus.py` | Realistic dataset generator |
| `fastdot.c` | C dot product (not integrated) |
| `ARCHITECTURE.md` | Design principles and failure modes |
| `MVP_SPEC.md` | Goals and success criteria |
| `PROJECT_STATE.md` | Current state and gaps |
| `SCHEMA.md` | Data model for persistence |
| `ADR.md` | This file |

### On-chain (`src/turbo-quant-agent-memory/onchain/`)
| File | Purpose |
|------|---------|
| `commit.mjs` | SHA3-256 + Arweave upload + Solana memo (with encrypt/decrypt) |
| `encrypt.mjs` | AES-256-GCM encryption module |
| `test-local.mjs` | 11 tests against local Solana validator |
| `package.json` | Dependencies (@solana/web3.js) |

### Research (`research/turbo-quant-agent-memory/`)
| File | Purpose |
|------|---------|
| `WHITEPAPER.md` | TurboQuant paper analysis |
| `MVP_VERIFICATION.md` | Verification methodology |

### Git commits (this session)
- `23c452c` — agent loop, encryption layer, latency benchmarks
- `797be9a` — research docs, corpus generator, verification suite, C dot product
