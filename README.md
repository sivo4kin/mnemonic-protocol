# mnemonic-protocol

Mnemonic is a verifiable memory / artifact infrastructure project for AI agents.

This repository currently contains both:

1. the **active Rust MCP implementation** on `main`, and
2. older **research / prototype / design-lineage** material.

To avoid split-brain interpretation, treat the current implementation docs as canonical.

---

## Canonical implementation truth

If you want to know what the code does **today**, start here:

- `mcp/README.md`
- `docs/versions/v0.0.3/SPEC.md`
- `docs/versions/v0.0.3/API.md`
- `docs/IMPLEMENTATION_AUDIT.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/README.md`

### Current implementation summary

The active implementation is the Rust MCP server in:

- `mcp/`

Current implementation characteristics:

- MCP over HTTP + stdio
- 5 Mnemonic tools
- canonical CBOR + COSE artifact signing
- blake3 hashing for current artifacts
- SQLite recall over full embeddings
- storage modes: `local` and `full`
- optional Solana + Arweave persistence in `full` mode
- payment-aware HTTP serving

---

## Research / legacy / prototype lineage

Older prototype and research documents are still kept because they explain:

- the compression/retrieval thesis
- snapshot/restore portability ideas
- encrypted snapshot commitment lineage
- benchmark and roadmap context

Those docs are now grouped under:

- `docs/legacy/`
- `docs/research/`
- `docs/adr/`

Important:

> These materials are valuable context, but they are **not** the canonical description of the current `mcp/` implementation unless explicitly stated.

---

## Documentation map

### Current implementation docs
- `docs/README.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/IMPLEMENTATION_AUDIT.md`
- `docs/versions/v0.0.3/SPEC.md`
- `docs/versions/v0.0.3/API.md`

### Current code
- `mcp/`

### Legacy / research lineage
- `docs/legacy/WHITEPAPER.full.md`
- `docs/legacy/ARCHITECTURE.full.md`
- `docs/legacy/PROJECT_STATE.full.md`
- `docs/legacy/BLOCKERS.full.md`
- `docs/research/*`
- `docs/adr/ADR.md`
- `legacy/`

---

## Rule of thumb

When docs disagree:

- **implementation truth** = `mcp/` + `docs/versions/v0.0.3/*`
- **research / legacy truth** = `docs/legacy/*`, `docs/research/*`, `docs/adr/*`

That split is intentional and explicit.

---

## Current goal

The repository is being cleaned up so that:

- current implementation docs are easy to find and trust
- research / prototype lineage remains available without pretending to be the current code path

That is the policy going forward.
