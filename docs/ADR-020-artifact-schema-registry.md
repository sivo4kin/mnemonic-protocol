# ADR-020: Artifact Schema Registry — Typed, Versioned, Immutable Schemas

**Date:** 2026-04-14  
**Status:** Proposed  
**Depends on:** ADR (CBOR/COSE canonical encoding, implemented on feat/CBOR)  
**Blocks:** Artifact lineage DAG, verifier SDK, reliability oracle (ADR-018)

---

## Context

Mnemonic artifacts have a `type` field (e.g. `rag.context`, `rag.result`, `memory`) and a
`schema_version` number. The current implementation (`codec/schema.rs`) defines five schemas
with canonical CBOR field ordering, required/optional field lists, and validation.

However, the schemas are structurally flat — all schemas share the same generic fields
(`artifact_id`, `type`, `schema_version`, `content`, `producer`, `created_at`, `tags`,
`metadata`, `parents`). There is no domain-specific structure:

- `rag.context` doesn't enforce `query`, `chunks`, or `retrieval_model`
- `rag.result` doesn't enforce `answer`, `context_artifacts`, or `citations`
- `agent.state` doesn't enforce `sequence`, `state_hash`, or `parent_state`
- `receipt` doesn't enforce `task_id`, `input_artifacts`, `output_artifacts`, or `status`

This means two producers emitting `rag.result` can produce completely different shapes,
leading to different CBOR canonical encodings, different content hashes, and broken
cross-agent verification.

---

## Decision

Evolve the schema registry to enforce domain-specific field structure per artifact type.

### Design principles

1. **Schemas are immutable once published** — `v1` is frozen after first artifact is written.
   Adding a field requires creating `v2`.

2. **Version bumps are additive only** — `v2` may add fields but must not rename or
   remove fields from `v1`. Existing verifiers remain valid.

3. **CBOR field order is schema-driven** — the codec reads field order from the registry,
   not from the input JSON. This is already implemented.

4. **Unknown fields are stripped before CBOR encoding** — prevents schema pollution and
   ensures deterministic hashing.

5. **Validation at write time** — reject malformed artifacts with `400 SCHEMA_VIOLATION`
   before CBOR encoding. Don't store invalid artifacts.

6. **Machine-readable schema publication** — schemas should be publishable as JSON Schema
   (Draft 7) and CBOR CDDL for external tooling.

### Schema evolution: current → target

#### `rag.context.v1` (retrieval context)

| Current | Target (this ADR) |
|---------|-------------------|
| `content: string` (generic) | `query: string` — original retrieval query |
| — | `chunks: [{text, source_uri, score}]` — retrieved chunks |
| — | `retrieval_model: string` — embedding/retrieval model used |
| — | `retrieved_at: timestamp` — when retrieval happened |
| `parents: []` | `parents: []` (unchanged) |

#### `rag.result.v1` (LLM answer)

| Current | Target |
|---------|--------|
| `content: string` (generic) | `answer: string` — LLM-generated answer |
| — | `context_artifacts: [ArtifactID]` — rag.context refs used |
| — | `citations: [{artifact_id, chunk_index, quote}]` — grounded citations |
| — | `model: string` — LLM model identifier |

#### `agent.state.v1` (memory snapshot)

| Current | Target |
|---------|--------|
| `content: string` (generic) | `state_hash: string` — blake3 of compressed state |
| — | `state_uri: string` — Arweave URI of state blob |
| — | `agent_id: string` — agent identity |
| — | `sequence: number` — monotonic counter (0 = initial) |
| — | `parent_state: ArtifactID?` — previous state (continuity chain) |

#### `receipt.v1` (execution record)

| Current | Target |
|---------|--------|
| `content: string` (generic) | `task_id: string` — opaque task identifier |
| — | `input_artifacts: [ArtifactID]` — consumed inputs |
| — | `output_artifacts: [ArtifactID]` — produced outputs |
| — | `status: "completed" \| "failed" \| "partial"` |
| — | `started_at: timestamp` |
| — | `completed_at: timestamp` |

#### `memory.v1` (backward compatibility)

The existing `memory.v1` schema is preserved as-is for backward compatibility with
the `sign_memory` MCP tool. It uses the generic `content: string` field.

### Registry interface

```rust
// Resolve schema by (type, version)
fn get_schema(type: &str, version: u32) -> Option<&ArtifactSchema>;

// Validate payload against schema — return violations
fn validate_artifact(artifact: &Value, schema: &ArtifactSchema) -> Result<(), Vec<SchemaViolation>>;

// Strip unknown fields before CBOR encoding
fn strip_unknown_fields(artifact: &Value, schema: &ArtifactSchema) -> Value;

// Return CBOR field order for codec
fn cbor_field_order(type: &str, version: u32) -> &[&str];
```

### Validation errors

| Error | HTTP | When |
|-------|------|------|
| `SCHEMA_NOT_FOUND` | 400 | Unknown `(type, version)` combination |
| `SCHEMA_VIOLATION` | 400 | Missing required field or wrong type |
| `UNKNOWN_FIELDS_STRIPPED` | (warning, not error) | Extra fields silently removed |

### On-chain implications

The schema version is already part of the canonical CBOR encoding (it's in
`cbor_field_order` for all schemas). This means:

- The content hash (blake3) covers the schema version
- Changing the schema of an existing artifact changes its hash
- The Solana anchor (v3) includes the embedding model but not the schema version
  explicitly — it's implicit in the content hash

---

## Open questions for implementation

1. **Should JSON Schema and CDDL definitions be compiled into the Rust binary or
   served from files?** Compiled-in is simpler and ensures consistency; files are
   easier to update and publish externally.

2. **Should `memory.v1` be upgraded to use structured fields?** The `sign_memory` MCP
   tool currently passes flat `content: string`. Upgrading would require changing the
   tool interface. Recommendation: keep `memory.v1` as-is, add structured schemas for
   new artifact types only.

3. **Should schema validation be opt-in or mandatory?** Mandatory is safer (prevents
   invalid artifacts from being anchored). But it requires all producers to know the
   exact schema fields. Recommendation: mandatory for new artifact types, lenient for
   `memory.v1`.

---

## Consequences

### Positive

- Cross-agent artifact interoperability — two producers emitting `rag.result.v1` produce
  the same CBOR structure, enabling cross-verification
- Verifiable RAG becomes real — `rag.result` must reference `context_artifacts`, creating
  an auditable retrieval-to-answer chain
- External tooling can consume schemas via JSON Schema / CDDL without running Mnemonic
- Schema versioning prevents breaking changes

### Negative

- Additional complexity in the upload pipeline (validate → strip → encode)
- Producers must know the exact field structure for each artifact type
- Schema evolution requires coordination (version bumps)

### Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Schema design error in v1 discovered post-publish | Low | 5-day review window before first external producer |
| `additionalProperties: false` breaks existing test fixtures | Medium | Audit all fixtures before integration |
| CBOR field order disagreement between codec and registry | Low | Single source of truth: registry owns order |

---

## Implementation estimate

5 days — see detailed task breakdown in the implementation task spec.

---

## Related ADRs

- **ADR-017**: Open embedder validation (nomic-embed-text-v1.5) — embedding model referenced in schemas
- **ADR-018**: Reliability oracle — consumes `receipt.v1` artifacts for scoring
- **ADR-019**: Agent commerce model — payment for artifact writes
