# turbo-quant-agent-memory

Minimal runnable MVP prototype for a **TurboQuant-inspired agent memory system**.

This is **not** full TurboQuant.
It is a compact prototype for testing a more production-shaped retrieval architecture:

- keep **full-precision embeddings** as source of truth
- build a **compressed shadow index**
- use **exact rerank** as the correction layer
- improve compressed retrieval with **corpus-calibrated per-dimension quantization**
- support both **offline mock embeddings** and **real OpenAI embeddings**
- support **real JSONL benchmark datasets** and **JSON result export**

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

## Real dataset input (JSONL)

You can benchmark your own memory/query data.

### Memory file format
Each line is JSON with at least:
- `memory_id`
- `content`

Optional:
- `memory_type`
- `importance_score`
- `tags`

Example `memories.jsonl`:

```jsonl
{"memory_id":"m1","content":"TurboQuant paper summary about vector quantization","memory_type":"research","tags":["quantization","paper"]}
{"memory_id":"m2","content":"Agent memory design note about compressed retrieval and reranking","memory_type":"design","importance_score":0.8}
{"memory_id":"m3","content":"Blockchain monitoring memory about wallet risk and suspicious transactions"}
```

### Query file format
Each line is JSON with at least:
- `query`

Optional:
- `relevant_ids` (list of labeled relevant memory ids)

Example `queries.jsonl`:

```jsonl
{"query":"compressed agent memory retrieval","relevant_ids":["m2"]}
{"query":"vector quantization research","relevant_ids":["m1"]}
{"query":"wallet transaction risk","relevant_ids":["m3"]}
```

### Benchmark behavior
- if `relevant_ids` are present, benchmark uses those labels
- if `relevant_ids` are absent, benchmark falls back to exact-search-as-baseline

## Benchmarking a real dataset

Example with OpenAI embeddings and JSON output:

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
python3 src/turbo-quant-agent-memory/pseudocode.py benchmark \
  --embedder openai \
  --bits 8 \
  --memory-file ./memories.jsonl \
  --query-file ./queries.jsonl \
  --k 10 \
  --candidates 50 \
  --out ./results.json
```

## JSON result export

If `--out` is provided, the benchmark writes a JSON file containing:
- benchmark config
- dataset mode
- judged/unjudged mode
- metrics

This makes it easier to compare runs later.

## Metrics reported

- candidate recall@k
- final recall@k
- candidate recall@n_candidates
- compression ratio
- quantization alpha summary
- saturation diagnostics

## What to look for

### Candidate recall@k
How many true top-k items already show up in the compressed shortlist.

### Final recall@k
How much exact rerank restores quality after compressed candidate generation.
This is the most important MVP metric.

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
