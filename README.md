Further development has moved to:

👉 **[Github](https://github.com/mnemonik-xyz/monorepo)**

👉 **[Site](https://mnemonik.xyz)**

👉 **[Live MCP server](https://mcp.mnemonik.xyz)**

# mnemonic-protocol

Mnemonic is a verifiable memory / artifact infrastructure project for AI agents.

The canonical implementation on `main` is the Rust MCP server.

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

The active implementation is in:

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

## Historical / research lineage

Older prototype and research material is still relevant for background and design rationale, but it is **not** the canonical description of the current `mcp/` implementation.

On `main`, that material is now represented mainly by:

- `docs/research/*`
- `docs/adr/ADR.md`
- `legacy/` directory snapshots

The dedicated archived-doc split was preserved on the separate Git branch:

- `legacy`

If you need the older whitepaper/prototype doc set intact, use the `legacy` branch.

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

### Historical / research context
- `docs/research/*`
- `docs/adr/ADR.md`
- `legacy/`
- Git branch: `legacy`

---

## Rule of thumb

When docs disagree:

- **implementation truth** = `mcp/` + `docs/versions/v0.0.3/*`
- **historical / research truth** = `docs/research/*`, `docs/adr/*`, `legacy/`, and the `legacy` branch

That split is now intentional and explicit.
