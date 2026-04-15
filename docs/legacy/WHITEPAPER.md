# Verifiable Persistent Agent Memory via Compressed On-Chain Embeddings

**Research Whitepaper / Prototype Lineage**  
**Draft v0.2 — April 2026**

This document is a **research whitepaper** describing the prototype architecture and long-range Mnemonic thesis.

It should be read as:
- research framing
- prototype lineage
- systems thesis
- design context

It should **not** be read as the canonical description of the current Rust MCP implementation on `main`.

For current implementation truth, read instead:
- `../../mcp/README.md`
- `../versions/v0.0.3/SPEC.md`
- `../versions/v0.0.3/API.md`
- `../IMPLEMENTATION_STATUS.md`

## What this whitepaper is about

The architecture described here is centered on:

- compressed semantic retrieval
- 2-stage retrieval cascade
- snapshot/restore portability
- encrypted snapshot commitment
- provider migration via re-embedding from raw payloads

That architecture reflects the legacy prototype and research direction.

## Important difference from current MCP

The active Rust MCP implementation currently uses a different implementation center:

- typed artifacts signed as **canonical CBOR + COSE_Sign1**
- **blake3** hashing for current artifacts
- SQLite recall over **full embeddings**
- runtime storage modes: `local` and `full`
- no current encrypt-before-hash snapshot flow in the active MCP path

## Why keep this whitepaper

Because it still provides useful context for:

- why Mnemonic exists
- what problem it aims to solve
- how the prototype validated compression/retrieval ideas
- where future convergence may happen

## Reading guidance

Use this whitepaper for:
- thesis
- research
- design lineage
- product framing

Use the versioned MCP docs for:
- current behavior
- active API surface
- implementation semantics
- storage model and verification behavior

---

The full original whitepaper content remains below and should be interpreted within that scope.
