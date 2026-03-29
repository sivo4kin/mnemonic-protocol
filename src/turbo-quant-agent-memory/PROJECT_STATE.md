# PROJECT_STATE.md

## Project

`turbo-quant-agent-memory`

## One-line summary

A practical, TurboQuant-inspired compressed agent memory MVP that uses a compressed shadow index for candidate generation and exact full-precision reranking for final retrieval quality.

## Current phase

Late research / early prototype.

This is no longer just an idea dump. The project already has:
- paper analysis
- distilled architectural principles
- schema and MVP specs
- a runnable Python prototype
- demo and benchmark entrypoints

## Source of truth

The current project context was reconstructed from files created in a prior web chat session.
Within this environment, the source of truth is:
- `src/turbo-quant-agent-memory/*`
- `research/turbo-quant-agent-memory/*`

## Project thesis

The core question being tested is:

> Can a compressed shadow index reduce storage cost while preserving retrieval quality well enough through exact reranking?

The project intentionally does **not** begin with full TurboQuant complexity.
Instead, it extracts the architectural lesson:
- compress broadly
- recover precision narrowly
- keep full-precision vectors as the correctness layer

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

## Implemented today

From `pseudocode.py`, the current prototype already includes:
- in-memory memory store
- full-precision embedding storage
- quantized shadow index
- normalized vector retrieval
- calibrated scalar quantization
- 4-bit and 8-bit modes
- compressed candidate retrieval
- exact reranking
- mock embedding provider
- OpenAI embedding provider
- local embedding cache
- synthetic dataset generation
- JSONL dataset ingestion
- benchmark mode
- JSON result export

## Important implementation note

The written docs often describe a simple global symmetric quantizer as the MVP default.

However, the current runnable prototype has already moved to:
- **corpus-calibrated per-dimension scalar quantization**

That means the code is slightly ahead of the docs, and documentation alignment is needed.

## Main artifacts

### In `src/turbo-quant-agent-memory/`
- `README.md`
- `ARCHITECTURE.md`
- `MVP_SPEC.md`
- `SCHEMA.md`
- `pseudocode.py`
- `PROJECT_STATE.md`

### In `research/turbo-quant-agent-memory/`
- `paper.pdf`
- `report.md`
- `condensed-principles.md`
- `apply-to-agent-memory-architecture.md`

## Key strengths of current design

- clean 2-stage retrieval architecture
- low implementation risk
- keeps exact vectors as safety/correction layer
- compatible with future TurboQuant-like upgrades
- practical benchmarkability
- online-friendly ingestion story

## Main gaps / open questions

1. No persistent storage layer yet
2. Single-file prototype needs modularization if project grows
3. No benchmark results on real datasets yet
4. No latency profiling under realistic corpus size
5. No transform/rotation experiments yet
6. No residual correction stage yet
7. Docs and implementation are slightly out of sync

## Recommended next steps

### Priority 1
- Align documentation with actual prototype behavior
- Run real benchmark passes using JSONL memories/queries
- Save benchmark outputs for comparison

### Priority 2
- Split `pseudocode.py` into modules:
  - embeddings
  - quantization
  - storage
  - retrieval
  - benchmarking

### Priority 3
- Choose persistence approach for MVP:
  - SQLite is likely the best first step

### Priority 4
- Only after real benchmarks, decide whether to explore:
  - random/structured transforms
  - residual correction
  - tiered precision classes

## Working recommendation

Do not overcommit to full TurboQuant implementation yet.
First prove that:
- shortlist recall is strong enough
- exact reranking recovers quality reliably
- storage savings are meaningful
- operational complexity stays low

If those are true, then phase 2 can justify additional sophistication.
