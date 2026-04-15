# Mnemonic — Implementation Status and Scope Map

**Date:** 2026-04-15  
**Purpose:** Prevent confusion between the historical research/prototype lineage and the current Rust MCP implementation.

---

## Executive summary

The canonical implementation on `main` is the Rust MCP server in:

- `mcp/`

At the same time, the repository still contains historical research and design lineage material.

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

## What counts as historical / research lineage

Historical or research-oriented material includes:

- ADR history and design rationale
- research notes and analyses
- legacy directory snapshots
- the archived `legacy` branch

These are useful for:

- research context
- design lineage
- roadmap / thesis material
- explaining why Mnemonic exists

But they should not be read as exact descriptions of the current `mcp/` implementation unless explicitly stated.

Historical/research-heavy sources include:

- `docs/adr/ADR.md`
- `docs/research/*`
- `legacy/`
- Git branch: `legacy`

---

## Key differences to keep in mind

| Topic | Historical / prototype lineage | Current MCP implementation |
|------|---------------------------------|----------------------------|
| Implementation center | prototype / research stacks | `mcp/` Rust server |
| Hashing | older snapshot-hash designs appear in history | blake3 for current artifacts; legacy SHA-256 verification fallback |
| Artifact format | earlier snapshot / JSON-centric thinking | canonical CBOR + COSE_Sign1 |
| Retrieval | historical compressed-cascade emphasis | full-embedding SQLite recall |
| Compression role | often central to retrieval architecture | artifact-side compression exists, but not current local retrieval index path |
| Encryption | discussed in historical designs | not currently implemented in active MCP path |
| Storage model | historical snapshot/commit approaches | `local` or `full` runtime storage modes |

---

## Reading guide

### If you want the current implementation truth
Read these first:

1. `mcp/README.md`
2. `docs/versions/v0.0.3/SPEC.md`
3. `docs/versions/v0.0.3/API.md`
4. `docs/IMPLEMENTATION_AUDIT.md`

### If you want historical thesis / product lineage
Read these after:

1. `docs/adr/ADR.md`
2. `docs/research/*`
3. `legacy/`
4. Git branch `legacy`

---

## Documentation rule of thumb

When docs disagree:

- **current implementation behavior** → trust `mcp/` + `docs/versions/v0.0.3/*`
- **historical/design intent** → trust ADR/research/legacy materials

That split is now intentional and explicit.
