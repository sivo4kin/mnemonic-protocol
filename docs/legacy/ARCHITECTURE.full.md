# Architecture: Minimal Compressed Agent Memory MVP

> **Scope note:** This document describes the legacy / research prototype architecture for compressed retrieval and exact reranking. It does **not** describe the current Rust MCP implementation in `mcp/` on `main`.
>
> For the active implementation, see:
> - `mcp/README.md`
> - `docs/versions/v0.0.3/SPEC.md`
> - `docs/versions/v0.0.3/API.md`
> - `docs/IMPLEMENTATION_STATUS.md`

## 1. System Intent

This prototype MVP is a **compressed retrieval layer** for agent memory.

It is not a full memory platform and not a full TurboQuant implementation.
The design goal is simple:

- keep **full-precision embeddings** for correctness
- add a **compressed shadow index** for cheap broad retrieval
- use **exact reranking** as the correction layer

That gives us a low-risk path to test whether compressed memory search is worth pursuing.

---

## 2. Core Design Choice

### Why exact reranking is the MVP correction layer

TurboQuant uses a residual correction mechanism for inner-product fidelity.
For the MVP, that would be overkill.

The simplest and safest correction layer is:
- use compressed vectors for **candidate generation**
- use full-precision vectors for **final rerank**

Why this is the right MVP move:
- easy to implement
- easy to reason about
- preserves final ranking quality
- isolates compression risk to shortlist recall
- avoids premature complexity like residual sketches or special transforms

So the prototype architecture is intentionally a **2-stage retrieval cascade**.

---

## 3. High-Level Flow

## Ingestion flow

1. Receive a memory item
2. Generate full-precision embedding
3. Normalize embedding
4. Quantize normalized embedding into low-bit form
5. Store:
   - raw memory payload / metadata
   - full embedding
   - compressed embedding
   - norm / quantization parameters

## Retrieval flow

1. Embed query
2. Normalize query embedding
3. Quantize query embedding with same config
4. Score against compressed shadow index
5. Select top `n_candidates`
6. Fetch corresponding full-precision vectors
7. Rerank exactly using float embeddings
8. Return final top `k`

---

## 4. Main Components

## A. Memory Store
Stores the actual memory records.

Contains:
- memory id
- text/summary/payload
- metadata
- timestamps
- tags
- importance signals

This is the source of truth.

## B. Full-Precision Embedding Store
Stores `float32` embeddings.

Purpose:
- exact reranking
- quality baseline
- future migrations / reindexing

This is important because the prototype should never be trapped by quantization loss.

## C. Quantized Shadow Index
Stores low-bit compressed vectors.

Purpose:
- fast broad search
- smaller memory footprint
- lower transfer cost if kept in RAM

For the prototype, use simple scalar quantization:
- 8-bit symmetric quantization as default
- 4-bit as aggressive compression mode

## D. Retrieval Engine
Responsible for:
- compressed scoring
- candidate selection
- exact rerank
- assembling final results

## E. Evaluation Harness
Used to measure:
- recall@k
- memory usage
- latency
- shortlist quality

The prototype is incomplete without this.

---

## 5. Recommended Storage Layers

## Layer 0 — Memory records
What the memory actually is:
- content
- summary
- source session
- created time
- tags
- importance score

## Layer 1 — Exact vector layer
Stores:
- original embedding
- embedding model id
- norm

Used for:
- exact rerank
- truth baseline

## Layer 2 — Compressed vector layer
Stores:
- quantized vector bytes / packed nibbles
- quantization bit width
- clip scale / quant params
- optional version id

Used for:
- candidate generation only

This separation is critical.

---

## 6. Quantization Strategy for MVP

## Prototype implementation

The prototype uses **corpus-calibrated per-dimension symmetric scalar quantization**
on normalized vectors.

For each dimension `j`:
- compute the 98th-percentile absolute value across the corpus for dimension `j`
- set per-dimension clip range `alpha_j`
- clip coordinate to `[-alpha_j, alpha_j]`
- map to integer bins
- store packed integer values

### Default values
- bits: `8`
- metric: inner product over normalized vectors (equivalent to cosine)

### Important prototype constraint
The per-dimension `alphas` and `steps` arrays live on the quantizer object, not on each record.
That means:
- the quantizer must be kept alongside the index
- re-fitting on a different corpus invalidates existing packed codes
- persistence must serialize quantizer state, not just packed codes

### 4-bit mode
4-bit mode is supported as the stress-test compression option.
If 4-bit preserves shortlist recall well enough, that is a strong signal.

---

## 7. Query-Time Retrieval Cascade

## Stage 1 — Compressed candidate generation

Input:
- normalized query vector
- quantized query vector
- quantized memory index

Output:
- top `n_candidates` memory ids by approximate similarity

This stage should be broad and cheap.

## Stage 2 — Exact rerank

Input:
- candidate ids
- full-precision query embedding
- full-precision memory embeddings for candidates

Output:
- final top `k`

This stage restores ranking quality.

### Recommended defaults
- `k = 10`
- `n_candidates = 50`
- increase to `100` if 4-bit recall is weak

---

## 8. Why This Architecture Works as a Prototype

This system deliberately separates concerns:

### Compression handles scale
The shadow index lets us store and scan more vectors cheaply.

### Exact embeddings handle correctness
Final ranking quality is preserved by reranking with float vectors.

### The interface stays future-proof
Later we can swap in:
- structured random rotations
- non-uniform scalar codebooks
- residual correction sketches
- ANN backends over compressed vectors

without changing the high-level retrieval contract.

---

## 9. Failure Modes to Watch

## Failure mode 1 — shortlist recall collapses
If compressed candidate generation misses too many true neighbors, rerank cannot recover them.

Mitigation:
- increase `n_candidates`
- use 8-bit instead of 4-bit
- tune clipping range

## Failure mode 2 — quantization saturates coordinates
If clip range is too small, many values hit boundaries.

Mitigation:
- inspect coordinate histograms
- tune `alpha`
- log saturation rate

## Failure mode 3 — rerank cost dominates
If `n_candidates` becomes too large, exact rerank may erase system gains.

Mitigation:
- benchmark the crossover point
- keep `n_candidates` modest

## Failure mode 4 — memory usefulness not aligned with embedding similarity
Good vector recall does not guarantee useful memory retrieval.

Mitigation:
- later add metadata-aware reranking
- evaluate with agent tasks, not just vector metrics

---

## 10. Recommended Prototype Defaults

- normalized embeddings: **yes**
- compressed shadow index: **yes**
- quantization: **per-dimension calibrated symmetric scalar**
- quantization bits: **8 default**, `4` experimental
- transform/rotation: **none**
- correction layer: **exact rerank only**
- top-k return: `10`
- shortlist size: `50`
- storage model: **SQLite working index + snapshot/restore**

---

## 11. Relationship to the current MCP implementation

The current `mcp/` implementation differs in important ways:

- active runtime is a Rust MCP server, not this prototype stack
- current local recall path uses **full embeddings in SQLite**
- current signed artifact format is **canonical CBOR + COSE**
- current artifact hashing uses **blake3**
- current runtime has explicit `local` and `full` storage modes
- current MCP path does not currently implement this compressed retrieval architecture as the active recall path

So this document should be read as:

> research architecture and prototype lineage

not:

> exact current code path

---

## 12. Bottom Line

The minimal prototype architecture is:

> full-precision memory store + compressed shadow index + 2-stage retrieval with exact rerank.

That is the smallest useful system that tests whether TurboQuant-inspired ideas are worth deeper implementation work for agent memory.
