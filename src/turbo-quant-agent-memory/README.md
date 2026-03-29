# turbo-quant-agent-memory

Minimal runnable MVP prototype for a **TurboQuant-inspired agent memory system**.

This is **not** full TurboQuant.
It is a compact prototype for testing a more production-shaped retrieval architecture:

- keep **full-precision embeddings** as source of truth
- build a **compressed shadow index**
- use **exact rerank** as the correction layer
- improve compressed retrieval with **corpus-calibrated per-dimension quantization**
- support both **offline mock embeddings** and **real OpenAI embeddings**

## Files

- `MVP_SPEC.md` — goals, non-goals, success criteria, milestones, metrics
- `ARCHITECTURE.md` — ingestion flow, storage layers, retrieval cascade, future extensions
- `SCHEMA.md` — suggested data model for memory records, embeddings, and quantized index
- `pseudocode.py` — runnable prototype with demo and benchmark modes

## Embedding modes

### 1. Mock mode
- fully offline
- deterministic
- good for quick architecture testing

### 2. OpenAI mode
- real embeddings via the OpenAI embeddings API
- cached locally on disk to avoid repeated API calls

## Environment variables for OpenAI mode

Required:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Optional:

```bash
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
```

Default model if not set:
- `text-embedding-3-small`

## Local embedding cache

Embeddings are cached under:

```text
src/turbo-quant-agent-memory/.cache/embeddings/
```

Cache key depends on:
- provider
- model
- text

So repeated runs with the same input should avoid extra API calls.

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

## Run with mock embeddings

Demo:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py demo --embedder mock
```

Benchmark:

```bash
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark --embedder mock --bits 8 --memories 1000 --queries 50 --k 10 --candidates 50
```

## Run with OpenAI embeddings

Demo:

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
python3 src/turbo-quant-agent-memory/pseudocode.py demo --embedder openai --bits 8
```

Benchmark:

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark --embedder openai --bits 8 --memories 200 --queries 20 --k 10 --candidates 50
```

### Important note
Using OpenAI mode will make network requests and can incur API cost.
Start with small corpus/query counts first.

## What improved vs the earlier version

### 1. Better quantization
- per-dimension calibrated clip ranges
- lower saturation
- better approximate scoring

### 2. Better benchmark diagnostics
Reports:
- candidate recall@k
- final recall@k
- candidate recall@n_candidates
- compression ratio
- quantization alpha summary
- saturation diagnostics

### 3. Real embedding path
The system can now test the same retrieval architecture with actual OpenAI embeddings.

## What to look for in benchmark results

### Candidate recall@k
How many true top-k items are already present in the compressed shortlist.
If this is weak, rerank cannot fully recover.

### Final recall@k
How much exact rerank restores quality after compressed candidate generation.
This is the most important MVP metric.

### Candidate recall@n_candidates
A broader diagnostic showing whether the shortlist is capturing the right neighborhood.

### Compression ratio
How much smaller the compressed index is than float32 normalized vectors.

### Saturation stats
If saturation is high, clip ranges are too tight or poorly calibrated.

## Recommended defaults

- embedder: `mock` for offline development, `openai` for real testing
- quantization bits: `8`
- final results: `k=10`
- shortlist size: `50`

## What this prototype is for

This prototype validates the architecture question:

> Can a compressed shadow index reduce storage cost while preserving retrieval quality well enough through exact reranking?

If yes, the next steps are:
- benchmark on real memory/query data
- add persistence for indexed corpora
- separate ingestion from retrieval
- only then consider TurboQuant-style transforms or residual correction
