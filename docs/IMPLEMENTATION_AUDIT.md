# Mnemonic MCP — Implementation Audit

**Date:** 2026-04-15  
**Branch:** `feat/CBOR` (commit `10175e4`)  
**Tests:** 59 passing (51 unit + 5 integration + 3 proptest)

Legend:
- [x] Done — implemented and tested
- [~] Partial — foundation exists, needs enhancement
- [ ] Not done — not started
- [N/A] Not applicable — out of scope or deferred by design

---

## 1. CBOR / COSE Refactor

### Codec Foundation
- [x] `toCanonicalCBOR(artifact)` — deterministic, pure, schema-driven field order (`codec/canonical.rs`, 1000x determinism test)
- [x] `blake3(canonical_cbor_bytes)` — content hash over canonical form only (`codec/hash.rs`)
- [x] `signArtifact()` — COSE_Sign1 using existing Solana Ed25519 keypair (`codec/sign.rs`)
- [x] `verifyArtifact()` — COSE verify works with standard coset library, no Mnemonic-specific code needed (`codec/sign.rs`)
- [x] Timestamps encoded as CBOR tag 1 (epoch integer, not ISO string) (`canonical.rs:json_to_cbor`, test confirms)
- [~] Float fields banned — floats are encoded as text strings in `json_to_cbor`, but no explicit validation rejects float input at the schema level
- [ ] CBOR tag 42 used for CID/IPFS link references — not implemented (no IPFS integration yet)

### Encoding Rules
- [x] Deterministic CBOR (RFC 8949 §4.2) — nested map keys sorted, no indefinite-length (`canonical.rs`)
- [~] dag-cbor format for IPFS/IPLD native CIDv1 compatibility — CBOR is valid but not explicitly tagged as dag-cbor (no CID wrapping)
- [x] Raw text never stored as primary object — canonical CBOR is the stored form on Arweave
- [ ] zstd compression applied after CBOR encoding — `zstd` crate is in Cargo.toml but not wired into the pipeline

### External API (unchanged surface)
- [~] `POST /artifact` — not implemented as a separate endpoint; artifacts are created via `mnemonic_sign_memory` MCP tool which accepts JSON and stores CBOR internally
- [~] `GET /artifact/{id}` — not implemented as a REST endpoint; `mnemonic_verify` fetches and verifies but doesn't return deserialized JSON artifact
- [~] `POST /verify` — `mnemonic_verify` MCP tool returns `checks` with `content_integrity`, `cose_signature`, `algorithm_valid`; missing `anchor_exists` and `lineage_valid` fields

### Cross-library Verification
- [ ] Sign in TypeScript, verify in Python — not tested (only Rust-to-Rust verification tested)
- [ ] dag-cbor artifact added to IPFS, retrieved by CID, hash matches — not implemented

---

## 2. Schema Registry

### Registry Core
- [x] Schema lookup by `(type, version)` — `get_schema()` in `codec/schema.rs`
- [x] `validate_artifact()` returns violations per missing required field
- [~] `strip()` removes unknown fields — not explicitly implemented; canonical CBOR encoding only includes fields in `cbor_field_order`, effectively stripping unknowns
- [x] `cborFieldOrder()` is the single source of truth consumed by CBOR codec
- [~] `(type, version)` lookup fails clearly — returns `None`, not a `400 SCHEMA_NOT_FOUND` HTTP error (no REST artifact endpoint exists yet)

### Schema Definitions
- [~] All five schemas defined (`rag.context.v1`, `rag.result.v1`, `agent.state.v1`, `receipt.v1`, `memory.v1`) BUT with generic fields only (`content`, `tags`, `metadata`, `parents`). Domain-specific fields (query, chunks, citations, etc.) proposed in ADR-020 but not implemented.
- [ ] `rag.context.v1` — domain fields NOT implemented (query, chunks, retrieval_model, retrieved_at)
- [ ] `rag.result.v1` — domain fields NOT implemented (answer, context_artifacts, citations, model)
- [ ] `agent.state.v1` — domain fields NOT implemented (agent_id, sequence, state_hash, state_uri)
- [ ] `receipt.v1` — domain fields NOT implemented (task_id, input_artifacts, output_artifacts, status)
- [ ] JSON Schema Draft 7 definitions — not implemented
- [ ] CDDL definitions — not implemented

### Validation Quality
- [ ] JSON Schema files validated by ajv in CI — N/A (no JSON Schema files exist)
- [ ] CDDL files validated by cddl CLI in CI — N/A (no CDDL files exist)
- [ ] `additionalProperties: false` enforced — not implemented (effectively achieved by CBOR field order stripping)
- [ ] `POST /artifact` returns `400 SCHEMA_VIOLATION` — no REST artifact endpoint exists

### Immutability Controls
- [ ] v1 schema files marked read-only in CI — not implemented
- [ ] `published_at` timestamp set and frozen — not implemented
- [ ] Schema extension documented in `SCHEMAS.md` — ADR-020 drafted but no SCHEMAS.md

### Publication
- [ ] JSON Schema served at `/.well-known/schemas/` — not implemented
- [ ] CDDL served alongside — not implemented

---

## 3. Parent DAG / Lineage

### Data Model
- [x] `parents: ParentRef[]` field in all schemas + CBOR field order (`codec/schema.rs`)
- [x] `ParentRef` type with `artifact_id` and optional `role` (`codec/schema.rs`)
- [x] `parents[]` included in canonical CBOR body — modifying parents changes hash
- [x] Root artifacts with `parents: []` accepted
- [x] Max 16 parents enforced (`lineage.rs:MAX_PARENTS`)
- [x] Max 64 depth enforced (`lineage.rs:MAX_DEPTH`)

### Write-time Validation
- [x] Parent existence check via pluggable function (`lineage.rs:validate_parents`)
- [~] Parent integrity check — existence is checked but hash verification of parent content is not implemented (the `attestation_exists` callback only checks if the ID exists in the store, not if the hash matches)
- [x] `PARENT_NOT_FOUND` error returned (tested)
- [ ] `PARENT_NOT_VERIFIED` error — not implemented (no parent hash verification)
- [x] `CYCLE_DETECTED` error returned (tested with A→B→C→A scenario)
- [x] `TOO_MANY_PARENTS` error returned (tested)
- [ ] `DEPTH_EXCEEDED` error — cycle detection has depth limit but no standalone depth-exceeded error

### Cycle Detection
- [x] DFS from each proposed parent upward before write (`lineage.rs:detect_cycle`)
- [x] Depth-limited to 64 hops
- [ ] Property-based test: random DAG generation — not implemented (only handcrafted tests)

### Lineage Index
- [x] SQLite `artifact_lineage` table with `child_id, parent_id, role, created_at`
- [x] Indexes on `parent_id` and `child_id`
- [x] Persistent in SQLite (survives restart)
- [ ] Rebuildable from Arweave scan — not implemented

### API
- [ ] `GET /artifact/{id}/lineage` endpoint — not wired into HTTP server
- [~] `traverse_lineage()` function exists with `nodes{}`, `edges[]`, direction control — but not exposed as HTTP endpoint
- [~] Each node includes basic info but no `verified` or `anchor` fields in traversal result

### `verify_chain(id)` SDK Function
- [ ] Full DAG traversal with fetch → hash → COSE → anchor → recurse — not implemented
- [ ] Per-node failure reporting — not implemented
- [ ] Works without Mnemonic server — not implemented (would need standalone function)
- [ ] 10-node chain benchmark — not implemented

---

## 4. Cross-cutting

- [x] Property-based test: 1000 iterations identical CBOR bytes (proptest + unit test)
- [ ] Cross-library round-trip: TypeScript → Python → hash match — not tested
- [x] All pre-existing MCP tools work unchanged (59 tests pass)
- [N/A] `@mnemonic/verifier` standalone package — follow-up task
- [N/A] CIDv1 as primary artifact ID — follow-up task (currently ULID)
- [N/A] Dynamic schema namespacing — follow-up task

---

## Summary

| Area | Done | Partial | Not Done | N/A |
|------|------|---------|----------|-----|
| **CBOR/COSE Codec** | 6 | 4 | 3 | 0 |
| **Schema Registry** | 3 | 3 | 10 | 2 |
| **Parent DAG** | 9 | 3 | 6 | 0 |
| **Cross-cutting** | 2 | 0 | 1 | 3 |
| **Total** | **20** | **10** | **20** | **5** |

### What's solid
- Canonical CBOR encoding is deterministic and tested (proptest + 1000x)
- COSE_Sign1 sign/verify works with standard library
- blake3 hashing over canonical CBOR is consistent
- Lineage index with cycle detection works
- All 5 MCP tools functional, 59 tests passing
- Solana anchor includes embedding model ID (v3)
- Hash embedder removed from production

### What needs work (prioritized)
1. **Wire lineage into MCP pipeline** — validate_parents in sign_memory, lineage endpoint
2. **zstd compression** — dependency exists, not wired
3. **REST artifact endpoints** — POST/GET/verify as HTTP routes (not just MCP tools)
4. **verify_chain traversal** — the killer feature for external verifiers
5. **Domain-specific schema fields** — per ADR-020
6. **Cross-library verification test** — sign Rust, verify Python/JS

### Not supposed to be done now (deferred by design)
- IPFS/dag-cbor integration (CID tag 42, CIDv1 IDs)
- Dynamic schema namespacing
- Standalone verifier SDK package
- Cross-instance DAG traversal
- Schema publication at well-known URLs
