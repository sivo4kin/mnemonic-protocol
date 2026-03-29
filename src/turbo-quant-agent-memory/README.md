# turbo-quant-agent-memory

Minimal MVP design package for a **TurboQuant-inspired agent memory system**.

This is **not** a full TurboQuant implementation.
It is a pragmatic first version focused on:
- full-precision embeddings as source of truth
- compressed shadow index for cheap candidate generation
- exact rerank as the correction layer

## What’s in here

- `MVP_SPEC.md` — goals, non-goals, success criteria, milestones, metrics
- `ARCHITECTURE.md` — ingestion flow, storage layers, retrieval cascade, future extensions
- `SCHEMA.md` — suggested data model for memory records, embeddings, and quantized index
- `pseudocode.py` — implementation-oriented Python skeleton for ingest / quantize / retrieve / rerank

## MVP summary

### Core idea
Use a 2-stage retrieval pipeline:
1. search broad memory corpus using compressed vectors
2. rerank shortlisted candidates using exact vectors

### Why this shape
It is the smallest useful system that tests whether compressed memory retrieval is worth deeper investment.

### Explicit non-goals
- no random rotation
- no residual QJL
- no learned codebooks
- no production serving stack

## Recommended defaults

- embedding model: `text-embedding-3-small`
- embedding dimension: `1536`
- quantization: `8-bit` symmetric scalar quantization
- experimental mode: `4-bit`
- final results: `k=10`
- shortlist size: `n_candidates=50`

## What to build next

1. Hook `pseudocode.py` to a real embedding provider
2. Add persistence (SQLite / Postgres / local files)
3. Benchmark exact vs compressed+rerank retrieval
4. Test 8-bit as baseline, 4-bit as aggressive compression
5. Only after that, consider TurboQuant-style phase-2 upgrades
