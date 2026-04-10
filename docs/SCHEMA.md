# Schema: Minimal Compressed Agent Memory MVP

## 1. Design Principles

The schema should preserve three things separately:

1. **Memory payload** — the actual content and metadata
2. **Exact vector representation** — used for reranking and ground truth
3. **Compressed vector representation** — used for cheap candidate generation

This separation keeps the MVP safe and upgradeable.

---

## 2. Logical Entities

The MVP can be modeled with three primary entities:

- `memory_items`
- `memory_embeddings`
- `quantized_index`

You can implement this in SQLite, Postgres, DuckDB, or even local files + NumPy for the first pass.

---

## 3. Table: memory_items

This is the source-of-truth memory record.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `memory_id` | string / UUID | yes | Primary key |
| `content` | text | yes | Raw memory text or summary |
| `memory_type` | string | yes | e.g. episodic, semantic, project, note |
| `source_session_id` | string | no | Origin session/thread/task |
| `project_id` | string | no | Optional project scope |
| `user_id` | string | no | Optional owner/user scope |
| `importance_score` | float | no | Default 0.0-1.0 |
| `tags_json` | json/text | no | Tags or structured labels |
| `created_at` | timestamp | yes | Creation time |
| `updated_at` | timestamp | yes | Last update time |
| `last_access_at` | timestamp | no | Retrieval/use timestamp |
| `retrieval_count` | integer | no | Usefulness proxy |
| `sensitivity_label` | string | no | public/internal/private/etc |
| `is_archived` | boolean | yes | Default false |

### Notes
- `importance_score` is optional in MVP but useful later for tiered precision.
- `retrieval_count` and `last_access_at` help future promotion/demotion logic.

---

## 4. Table: memory_embeddings

Stores full-precision embeddings and embedding metadata.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `memory_id` | string / UUID | yes | FK to `memory_items` |
| `embedding_model` | string | yes | e.g. `nomic-ai/nomic-embed-text-v1.5` (V1 canonical), `text-embedding-3-small` (alternative) |
| `embedding_dim` | integer | yes | e.g. 768 (nomic), 1536 (OpenAI) |
| `embedding_dtype` | string | yes | `float32` |
| `embedding_f32` | blob / array | yes | Full-precision vector |
| `embedding_norm` | float | yes | L2 norm before normalization |
| `normalized_f32` | blob / array | yes | Optional cached normalized vector |
| `embedding_version` | integer | yes | Version for migrations |
| `created_at` | timestamp | yes | Created time |

### Notes
- You may choose to store only `embedding_f32` and compute normalization on the fly.
- For MVP, storing `normalized_f32` is acceptable if it simplifies rerank.
- This table is the exact rerank source.

---

## 5. Table: quantized_index

Stores the compressed shadow representation.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `memory_id` | string / UUID | yes | FK to `memory_items` |
| `quant_version` | integer | yes | Version of quantization logic |
| `quant_bits` | integer | yes | `4` or `8` |
| `quant_scheme` | string | yes | e.g. `symmetric_uniform_per_dim_calibrated` |
| `embedding_dim` | integer | yes | Must match original dim |
| `packed_codes` | blob | yes | Packed quantized values |
| `saturation_rate` | float | no | Fraction clipped at boundaries |
| `created_at` | timestamp | yes | Created time |
| `updated_at` | timestamp | yes | Last re-quantized time |

### Quantizer state (stored separately, not per record)

The current implementation uses per-dimension calibration. The quantizer state
must be stored alongside the index, not per record:

| Field | Type | Notes |
|---|---|---|
| `alphas` | float array | Per-dimension clip ranges, length = embedding_dim |
| `steps` | float array | Per-dimension bin widths, length = embedding_dim |
| `bits` | integer | 4 or 8 |
| `default_alpha` | float | Fallback floor for alpha calibration |

### Notes
- `packed_codes` is the main compressed representation.
- For 4-bit mode, pack two values per byte.
- Dequantization requires the quantizer's `alphas` and `steps` arrays: `value_j = -alpha_j + code_j * step_j`.
- A single `clip_alpha` float is **not sufficient** — the current implementation uses per-dimension `alpha_j` values.
- The quantizer must be serialized/persisted alongside the index for the packed codes to be usable.

---

## 6. Optional Table: retrieval_events

Useful if you want to learn from usage even in MVP.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `event_id` | string / UUID | yes | Primary key |
| `query_id` | string | yes | Retrieval operation id |
| `memory_id` | string / UUID | yes | Retrieved memory |
| `stage` | string | yes | `candidate` or `final` |
| `approx_score` | float | no | Compressed-stage similarity |
| `exact_score` | float | no | Final rerank similarity |
| `rank_position` | integer | yes | Rank within stage |
| `created_at` | timestamp | yes | Event time |

This is optional but good for analysis.

---

## 7. Minimal Object Model

If you implement MVP in Python first, the core objects can be:

### `MemoryItem`
```python
{
  "memory_id": str,
  "content": str,
  "memory_type": str,
  "importance_score": float,
  "tags": list[str],
  "created_at": datetime,
}
```

### `EmbeddingRecord`
```python
{
  "memory_id": str,
  "embedding_model": str,
  "embedding_dim": int,
  "embedding_f32": np.ndarray,
  "embedding_norm": float,
  "normalized_f32": np.ndarray,
}
```

### `QuantizedRecord`
```python
{
  "memory_id": str,
  "quant_bits": int,
  "quant_scheme": "symmetric_uniform_per_dim_calibrated",
  "packed_codes": bytes,
  "embedding_dim": int,
  "saturation_rate": float,
}
```

### `CalibratedScalarQuantizer` (quantizer state — stored once per index, not per record)
```python
{
  "bits": int,
  "default_alpha": float,
  "alphas": list[float],   # per-dimension clip ranges
  "steps": list[float],    # per-dimension bin widths
}
```

---

## 8. Recommended Defaults

For MVP:

- `embedding_model`: `nomic-ai/nomic-embed-text-v1.5` (V1 canonical open embedder)
- `embedding_dim`: `768`
- `quant_bits`: `8`
- `quant_scheme`: `symmetric_uniform_per_dim_calibrated`
- per-dimension `alphas`: calibrated from corpus at 98th percentile
- `quant_version`: `1`
- `embedding_version`: `1`

Use 4-bit mode as an experimental branch, not the default.

---

## 9. Indexing / Access Patterns

### Common ingestion path
1. insert into `memory_items`
2. insert into `memory_embeddings`
3. insert into `quantized_index`

### Common retrieval path
1. score query against `quantized_index`
2. get top candidate `memory_id`s
3. fetch exact embeddings from `memory_embeddings`
4. fetch payload from `memory_items`
5. rerank and return

This is the central contract of the MVP.

---

## 10. Future-Proofing Fields

Fields worth keeping even if lightly used now:
- `quant_version`
- `embedding_version`
- `saturation_rate`
- `importance_score`
- `retrieval_count`
- `last_access_at`

These make future migrations and tiered precision much easier.

---

## 11. Bottom Line

The minimal schema should preserve:
- exact memory data
- exact embeddings
- compressed lookup vectors

That is enough to support a 2-stage compressed retrieval MVP without locking the system into a premature compression design.
