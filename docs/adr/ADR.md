# Architecture Decision Record — Mnemonic

> **Scope note:** This ADR index is historical and mixed-scope.
>
> Many entries document the legacy prototype / research evolution of Mnemonic and should not be assumed to describe the current Rust MCP implementation in `mcp/` exactly.
>
> For current implementation truth, prefer:
> - `mcp/README.md`
> - `docs/versions/v0.0.3/API.md`
> - `docs/versions/v0.0.3/SPEC.md`
> - `docs/IMPLEMENTATION_STATUS.md`
>
> This ADR file remains valuable as design lineage, rationale history, and roadmap context.

Last updated: 2026-04-15

---

## How to read this ADR file

There are three kinds of entries mixed together here:

1. **Prototype / research decisions**
   - compressed retrieval
   - snapshot/restore
   - encryption-before-hash design
   - prototype benchmark and validation work

2. **Current MCP-adjacent implementation decisions**
   - CBOR / COSE artifact work
   - current MCP API and storage behavior
   - implementation audit items

3. **Roadmap / future-system decisions**
   - multi-party reliability
   - broader agent-commerce distribution model
   - future network or platform direction

That means this file should be read as:

> historical decision record and design lineage

not:

> exact single-source description of the current `main` implementation

---

## Current implementation reminder

The active implementation on `main` is the Rust MCP server in `mcp/`.

Current implementation characteristics include:

- typed artifacts using canonical CBOR + COSE
- blake3 content hashing for current artifacts
- SQLite full-embedding recall
- storage modes: `local` and `full`
- payment-aware HTTP transport

This differs materially from parts of the earlier prototype lineage documented below.

---

## ADR history

Historical ADR entries are preserved below as design record.

When an older ADR discusses:
- Python prototype modules
- compressed shadow-index retrieval
- encrypt-before-hash snapshots
- snapshot/restore portability

that should be interpreted as prototype or research lineage unless explicitly updated for `mcp/`.

---

For detailed current implementation status, see:
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/IMPLEMENTATION_AUDIT.md`
