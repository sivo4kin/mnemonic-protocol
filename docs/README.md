# Documentation Map

Use this page as the entry point.

The canonical implementation on `main` is the Rust MCP server.

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

- `../mcp/`

Current implementation characteristics:

- MCP over HTTP + stdio
- canonical CBOR + COSE artifacts
- blake3 hashing for current artifacts
- SQLite full-embedding recall
- storage modes: `local`, `full`
- payment-aware HTTP serving

---

## 2. Historical / research lineage

Historical and research material is still useful, but it is not the canonical description of current `mcp/` behavior.

On `main`, use these for background:

- `adr/ADR.md`
- `research/*`
- `../legacy/`

If you want the archived prototype-heavy docs set, use the Git branch:

- `legacy`

---

## 3. Practical reading order

### For implementation work
1. `../mcp/README.md`
2. `versions/v0.0.3/SPEC.md`
3. `versions/v0.0.3/API.md`
4. `IMPLEMENTATION_AUDIT.md`
5. `IMPLEMENTATION_STATUS.md`

### For historical/product framing
1. `adr/ADR.md`
2. `research/*`
3. Git branch `legacy`

---

## 4. Rule of thumb

When docs disagree:

- **implementation truth** = `mcp/` + `docs/versions/v0.0.3/*`
- **historical / roadmap truth** = `docs/research/*`, `docs/adr/*`, `legacy/`, and the `legacy` branch

That split is intentional and explicit.
