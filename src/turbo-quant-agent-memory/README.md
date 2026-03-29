# turbo-quant-agent-memory

Minimal runnable MVP prototype for a **TurboQuant-inspired agent memory system**.

This is **not** full TurboQuant.
It is the simplest useful architecture for testing compressed memory retrieval:

- keep **full-precision embeddings** as source of truth
- build a **compressed shadow index**
- use **exact rerank** as the correction layer

## Files

- `MVP_SPEC.md` — goals, non-goals, success criteria, milestones, metrics
- `ARCHITECTURE.md` — ingestion flow, storage layers, retrieval cascade, future extensions
- `SCHEMA.md` — suggested data model for memory records, embeddings, and quantized index
- `pseudocode.py` — runnable offline prototype with demo and benchmark modes

## Key MVP decisions

### Correction layer
The MVP uses **exact reranking**, not residual sketches.

Why:
- much simpler to implement
- preserves final ranking quality
- keeps compression risk limited to shortlist recall
- gives a clean baseline before adding more advanced correction methods

### Quantization
- default: **8-bit** symmetric scalar quantization
- optional: **4-bit** mode for more aggressive compression
- no random rotation
- no QJL
- no learned codebooks

## Requirements

- Python 3.10+ recommended
- no external dependencies required

## Run the demo

From the workspace root or this folder:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py demo
```

Or with 4-bit mode:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py demo --bits 4
```

The demo will:
- build a small in-memory corpus
- index it
- run sample queries
- print:
  - compressed-stage candidates
  - final reranked results
  - exact baseline results

## Run the benchmark

Default benchmark:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark
```

Custom example:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark --bits 8 --memories 2000 --queries 100 --k 10 --candidates 50
```

4-bit example:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark --bits 4 --memories 2000 --queries 100 --k 10 --candidates 75
```

The benchmark reports:
- average candidate recall@k
- average final recall@k
- rough float vs compressed index size
- compression ratio

## Recommended defaults

- embedding dimension: `256` in the offline mock prototype
- quantization bits: `8`
- clip range: `0.25`
- final results: `k=10`
- shortlist size: `50`

## What this prototype is for

This prototype is for validating the product/architecture question:

> Can a compressed shadow index reduce storage cost while preserving retrieval quality well enough through exact reranking?

If yes, the next steps are:
- plug in a real embedding model
- add persistence
- benchmark on real memory/query data
- then consider TurboQuant-style upgrades
