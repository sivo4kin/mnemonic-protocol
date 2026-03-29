# turbo-quant-agent-memory

Minimal runnable MVP prototype for a **TurboQuant-inspired agent memory system**.

This is **not** full TurboQuant.
It is a compact offline prototype for testing a more production-shaped retrieval architecture:

- keep **full-precision embeddings** as source of truth
- build a **compressed shadow index**
- use **exact rerank** as the correction layer
- improve compressed retrieval with **corpus-calibrated per-dimension quantization**

## Files

- `MVP_SPEC.md` — goals, non-goals, success criteria, milestones, metrics
- `ARCHITECTURE.md` — ingestion flow, storage layers, retrieval cascade, future extensions
- `SCHEMA.md` — suggested data model for memory records, embeddings, and quantized index
- `pseudocode.py` — runnable offline prototype with demo and benchmark modes

## What improved vs the first runnable version

### 1. Better quantization
The prototype now uses **per-dimension calibrated quantization** instead of one global clip range.

That means:
- each dimension gets its own clip range from corpus statistics
- saturation is reduced
- approximate scoring is more faithful
- compressed candidate quality is more production-like

### 2. Better offline embeddings
The mock embedder is still local and deterministic, but now includes:
- token features
- bigram features
- domain keyword boosts
- lightweight lexical statistics

So the retrieval benchmark is less toy-like.

### 3. Better benchmark output
The benchmark now reports:
- candidate recall@k
- final recall@k
- candidate recall@n_candidates
- compression ratio
- quantization alpha summary
- saturation diagnostics

## Key MVP decisions

### Correction layer
The MVP uses **exact reranking**, not residual sketches.

Why:
- much simpler to implement
- preserves final ranking quality
- keeps compression risk limited to shortlist recall
- gives a clean baseline before adding more advanced correction methods

### Quantization
- default: **8-bit** calibrated scalar quantization
- optional: **4-bit** mode for more aggressive compression
- no random rotation
- no QJL
- no learned codebooks

## Requirements

- Python 3.10+ recommended
- no external dependencies required

## Run the demo

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py demo
```

4-bit demo:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py demo --bits 4
```

The demo will:
- build a small in-memory corpus
- calibrate the quantizer
- index memories
- run sample queries
- print:
  - compressed-stage candidates
  - final reranked results
  - exact baseline results

## Run the benchmark

Default:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark
```

Example:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark --bits 8 --memories 1000 --queries 50 --k 10 --candidates 50
```

4-bit example:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark --bits 4 --memories 1000 --queries 50 --k 10 --candidates 75
```

## What to look for in benchmark results

### Candidate recall@k
How many true top-k items are already present in the compressed shortlist.
If this is weak, rerank cannot fully recover.

### Final recall@k
How much exact rerank restores quality after compressed candidate generation.
This is the most important MVP metric.

### Candidate recall@n_candidates
A broader diagnostic that shows whether the shortlist is capturing the right neighborhood at all.

### Compression ratio
How much smaller the compressed index is than float32 normalized vectors.

### Saturation stats
If saturation is high, clip ranges are too tight or the representation is poorly calibrated.

## Recommended defaults

- embedding dimension: `384` in the offline mock prototype
- quantization bits: `8`
- final results: `k=10`
- shortlist size: `50`

## What this prototype is for

This prototype is for validating the architecture question:

> Can a compressed shadow index reduce storage cost while preserving retrieval quality well enough through exact reranking?

If yes, the next steps are:
- plug in a real embedding model
- add persistence
- benchmark on real memory/query data
- only then consider TurboQuant-style transforms or residual correction
