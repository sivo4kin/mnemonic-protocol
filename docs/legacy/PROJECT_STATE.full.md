# PROJECT_STATE.md

> **Scope note:** This file now distinguishes between the legacy prototype/research lineage and the active implementation on `main`.
>
> - **Current implementation truth:** `mcp/`, `docs/versions/v0.0.3/*`, `docs/IMPLEMENTATION_STATUS.md`
> - **Legacy / research lineage:** whitepaper, prototype architecture, older ADR history, `legacy/`

## Project

`mnemonic-protocol`

## One-line summary

Mnemonic is building verifiable agent memory infrastructure. The repository currently contains both:

- a **legacy research/prototype lineage** centered on compressed retrieval and snapshot/restore ideas
- a **current Rust MCP implementation** centered on signed artifacts, MCP delivery, and storage-mode-aware persistence

## Current implementation status

The active implementation on `main` is:

- `mcp/`

Current behavior includes:

- Rust MCP server
- HTTP + stdio
- canonical CBOR + COSE artifacts
- blake3 hashing for current artifacts
- SQLite local recall index
- `local` and `full` storage modes
- optional Arweave + Solana persistence in `full`
- payment-aware HTTP serving

Current implementation docs:

- `mcp/README.md`
- `docs/versions/v0.0.3/API.md`
- `docs/versions/v0.0.3/SPEC.md`
- `docs/IMPLEMENTATION_AUDIT.md`
- `docs/IMPLEMENTATION_STATUS.md`

## Legacy / research lineage status

The older prototype/research track explored and validated:

- compressed shadow-index retrieval
- exact rerank cascade
- snapshot/restore portability
- encryption-before-hash commitment
- concurrent-writer research direction
- prototype economics and retrieval validation

That material is still valuable design lineage, but it should not be read as a literal description of the current `mcp/` code path.

## Product definition

### What it is
A verifiable agent memory system and artifact layer.

### Current repo reality
At the repository level, there are two layers of truth:

1. **Current implementation truth** — the Rust MCP server in `mcp/`
2. **Research / roadmap truth** — top-level architecture, whitepaper, and prototype lineage docs

### Who it's for
Two simultaneous audiences:
- **Agent builders** — SDK/API consumers who want verifiable memory or artifact infrastructure
- **Future end users** — via higher-level agent applications built on top

### Wedge
Any agent or agent network that needs durable, portable, or verifiable context.

---

## Important repository distinction

### What is current code
Treat these as current implementation sources:

- `mcp/*`
- `docs/versions/v0.0.3/*`
- `docs/IMPLEMENTATION_AUDIT.md`
- `docs/IMPLEMENTATION_STATUS.md`

### What is legacy / design lineage
Treat these as historical, research, or roadmap sources unless explicitly updated for current code:

- `docs/WHITEPAPER.md`
- `docs/ARCHITECTURE.md`
- `docs/BLOCKERS.md`
- `docs/adr/ADR.md`
- `docs/research/*`
- `legacy/*`

---

## What is built now vs what was proven historically

### Built now (`mcp/`)
- MCP tool server
- JSON-RPC MCP transport
- HTTP management API
- typed CBOR/COSE artifact signing
- local/full storage model
- current verification path for current and legacy artifacts
- payment gate and pricing logic

### Proven historically in prototype/research lineage
- compressed retrieval cascade
- snapshot/restore portability path
- encryption-before-hash design
- quantized retrieval benchmarks and evaluation work
- prototype-oriented concurrent writer and reliability research

---

## Current phase

**Docs and implementation are being actively aligned around the Rust MCP implementation.**

The most important project hygiene rule right now is:

> do not assume older prototype docs describe the active `mcp/` implementation unless they explicitly say so.

## Source of truth

### For current implementation behavior
- `mcp/src/*`
- `mcp/README.md`
- `docs/versions/v0.0.3/API.md`
- `docs/versions/v0.0.3/SPEC.md`
- `docs/IMPLEMENTATION_AUDIT.md`

### For research lineage / thesis / roadmap
- `docs/WHITEPAPER.md`
- `docs/ARCHITECTURE.md`
- `docs/adr/ADR.md`
- `docs/research/*`
- `legacy/*`

---

## Main artifacts

### Current implementation
- `mcp/` — active Rust MCP implementation
- `docs/versions/v0.0.3/` — current MCP implementation docs
- `docs/diagrams/` — current Mermaid diagrams for MCP layers and flows

### Research / lineage
- `docs/WHITEPAPER.md`
- `docs/ARCHITECTURE.md`
- `docs/BLOCKERS.md`
- `docs/adr/ADR.md`
- `docs/research/*`
- `legacy/*`

---

## Practical reading order

If you want to know **what the code does today**:
1. `docs/IMPLEMENTATION_STATUS.md`
2. `mcp/README.md`
3. `docs/versions/v0.0.3/SPEC.md`
4. `docs/versions/v0.0.3/API.md`
5. `docs/IMPLEMENTATION_AUDIT.md`

If you want to know **where the idea came from / where it may go**:
1. `docs/WHITEPAPER.md`
2. `docs/ARCHITECTURE.md`
3. `docs/adr/ADR.md`
4. `docs/research/*`

---

## Bottom line

The repo is no longer in the state where one top-level architecture doc can honestly stand in for the entire implementation.

Right now the honest framing is:

- **current implementation:** Rust MCP server in `mcp/`
- **legacy/prototype lineage:** compression + encrypted snapshot architecture documented in older top-level docs

Those two tracks are related, but they are not identical.
