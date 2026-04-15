# Mnemonic — Implementation Status and Scope Map

**Date:** 2026-04-15  
**Purpose:** Prevent confusion between the legacy prototype / research architecture and the current Rust MCP implementation.

---

## Executive summary

This repository currently contains **two different but related tracks**:

1. **Legacy prototype / research track**
   - now represented by `legacy/` and older top-level design documents
   - focused on compressed shadow-index retrieval, snapshot/restore, encryption, and research validation

2. **Current active implementation track**
   - represented by `mcp/` on `main`
   - focused on an MCP server with CBOR/COSE artifacts, blake3 hashing, SQLite recall, optional Arweave/Solana persistence, and payment-aware HTTP serving

These tracks share the same broader Mnemonic thesis, but they are **not the same implementation**.

---

## What is current on `main`

The active implementation on `main` is:

- `mcp/`

Current implementation characteristics:

- Rust MCP server
- HTTP + stdio
- 5 Mnemonic tools
- canonical CBOR + COSE artifact signing
- blake3 content hashing for current artifacts
- SQLite local recall index
- storage modes:
  - `local`
  - `full`
- optional Solana + Arweave persistence in `full` mode
- payment layer (`none`, `balance`, `x402`, `both`)
- current recall path uses **full embeddings in SQLite**
- no end-to-end encryption layer in the active MCP sign/verify flow

Current implementation docs:

- `mcp/README.md`
- `docs/versions/v0.0.3/API.md`
- `docs/versions/v0.0.3/SPEC.md`
- `docs/IMPLEMENTATION_AUDIT.md`

---

## What is legacy / research / prototype lineage

The older prototype and research architecture describes a different design center:

- compressed shadow index
- 2-stage retrieval cascade
- snapshot/restore portability flow
- encryption-before-hash snapshot commitment
- Python-centric prototype modules and benchmarks

That material is still valuable as:

- research context
- design lineage
- roadmap / thesis material
- explanation of why Mnemonic exists

But it should not be read as an exact description of the current `mcp/` implementation unless explicitly stated.

Legacy/research-heavy docs include:

- `docs/WHITEPAPER.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STATE.md`
- `docs/BLOCKERS.md`
- `docs/adr/ADR.md` (many entries describe the prototype and pre-MCP evolution)
- `docs/research/*`
- `legacy/`

---

## Key differences

| Topic | Legacy / prototype docs | Current MCP implementation |
|------|--------------------------|----------------------------|
| Implementation center | Python prototype / research stack | `mcp/` Rust server |
| Hashing | Often described as SHA3-256 snapshot commitment | blake3 for current artifacts; legacy SHA-256 verification fallback |
| Artifact format | Snapshot / JSON-centric | canonical CBOR + COSE_Sign1 |
| Retrieval | compressed candidate generation + exact rerank | full-embedding SQLite recall |
| Compression role | core retrieval architecture | artifact-side compression exists, but not current local retrieval index path |
| Encryption | described in prototype architecture | not currently implemented in active MCP path |
| Storage model | snapshot/restore + on-chain commit | `local` or `full` runtime storage modes |

---

## Reading guide

### If you want the current implementation truth
Read these first:

1. `mcp/README.md`
2. `docs/versions/v0.0.3/SPEC.md`
3. `docs/versions/v0.0.3/API.md`
4. `docs/IMPLEMENTATION_AUDIT.md`

### If you want research thesis / product lineage
Read these after:

1. `docs/WHITEPAPER.md`
2. `docs/ARCHITECTURE.md`
3. `docs/PROJECT_STATE.md`
4. `docs/research/*`
5. `docs/adr/ADR.md`

---

## Documentation rule of thumb

When docs disagree:

- **current implementation behavior** → trust `mcp/` + `docs/versions/v0.0.3/*`
- **research/design intent** → trust whitepaper / architecture / ADR / research docs

If a top-level doc discusses the prototype architecture, it should be treated as:

> design lineage and research context, not necessarily the current code path

---

## Recommended next cleanup direction

The repository should gradually converge on this split:

- **current implementation docs**
  - MCP/API/SPEC/README under versioned implementation docs
- **research and legacy docs**
  - clearly labeled as prototype / design lineage / future roadmap

That keeps the historical work valuable without implying it is identical to the current Rust MCP server.
