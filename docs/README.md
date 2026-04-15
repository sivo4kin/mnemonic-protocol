# Documentation Map

This repository contains both:

1. the **current active implementation** of Mnemonic, and
2. older **research / prototype / legacy design lineage** docs.

To avoid split-brain reading, use this page as the entry point.

---

## 1. Current implementation truth

If you want to know what the code on `main` does today, read these first:

- `../mcp/README.md`
- `versions/v0.0.3/SPEC.md`
- `versions/v0.0.3/API.md`
- `IMPLEMENTATION_AUDIT.md`
- `IMPLEMENTATION_STATUS.md`

### Current implementation summary

The active implementation is the Rust MCP server in:

- `mcp/`

Current implementation characteristics:

- MCP over HTTP + stdio
- canonical CBOR + COSE artifacts
- blake3 hashing for current artifacts
- SQLite full-embedding recall
- storage modes: `local`, `full`
- payment-aware HTTP serving

---

## 2. Research / legacy / prototype lineage

These docs describe the older prototype and broader design thesis:

- `legacy/WHITEPAPER.md`
- `legacy/ARCHITECTURE.md`
- `legacy/PROJECT_STATE.md`
- `legacy/BLOCKERS.md`
- `adr/ADR.md`
- `research/*`

Use them for:

- research context
- design rationale
- roadmap lineage
- historical prototype architecture

Do **not** assume they are exact descriptions of the current `mcp/` code unless they explicitly say so.

---

## 3. Practical reading order

### For implementation work
1. `../mcp/README.md`
2. `versions/v0.0.3/SPEC.md`
3. `versions/v0.0.3/API.md`
4. `IMPLEMENTATION_AUDIT.md`
5. `IMPLEMENTATION_STATUS.md`

### For research/product framing
1. `legacy/WHITEPAPER.md`
2. `legacy/ARCHITECTURE.md`
3. `adr/ADR.md`
4. `research/*`

---

## 4. Rule of thumb

When docs disagree:

- **implementation truth** = `mcp/` + `docs/versions/v0.0.3/*`
- **research / roadmap truth** = `docs/legacy/*`, `docs/adr/*`, `docs/research/*`

That split is intentional and should remain explicit.
