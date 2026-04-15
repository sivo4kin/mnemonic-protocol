# mnemonic-protocol

**Verifiable memory attestation primitive for AI agents.**

> Mnemonic gives any AI agent a Solana keypair identity and the ability to create
> permanent, hash-anchored, semantically searchable proofs of its work on Arweave.

No agent can cryptographically prove who it is, what it has done, or why it should
be trusted. Mnemonic fills that gap — at the attestation layer, not the identity
registry layer (ERC-8004), key management layer (Lit Protocol), or naming layer (ENS).

An agent that can prove *"I am keypair X, I signed memory Y at time Z, and the full
content is retrievable at Arweave TX W"* has a meaningful identity claim.

---

## What it does

Five MCP tools, one Solana keypair, one permanent storage layer:

| Tool | What it proves |
|------|---------------|
| `mnemonic_whoami` | "I am this keypair" — pubkey, did:sol, did:key |
| `mnemonic_sign_memory` | "I attested this content at this time" — embed → CBOR → COSE → blake3 → Arweave + Solana |
| `mnemonic_verify` | "This attestation is untampered" — fetch → recompute hash → compare on-chain |
| `mnemonic_prove_identity` | "I control this key right now" — Ed25519 challenge-response |
| `mnemonic_recall` | "Here's what I attested about X" — semantic search over memory history |

---

## Architecture

```
MCP Client (Claude Code / Cursor / Codex)
    │
    │  JSON-RPC (stdio or HTTP)
    ▼
mnemonic-mcp (Rust)
    ├── identity      Ed25519 keypair, did:sol, did:key
    ├── codec          CBOR canonical encoding + COSE_Sign1 (RFC 9052)
    ├── embed          fastembed (MiniLM, open weights) or OpenAI
    ├── compress       TurboQuant (PolarQuant + QJL, 4-bit)
    ├── storage        SQLite (local) + Arweave (permanent) + Solana (anchor)
    └── payment        balance, x402, dynamic pricing
```

---

## Quick start

```bash
cd mcp/
cargo build --release
./target/release/mnemonic-mcp --transport http --port 3000
```

Local mode (free, no blockchain):
```bash
STORAGE_MODE=local ./target/release/mnemonic-mcp --transport http --port 3000
```

Claude Code config:
```json
{
  "mcpServers": {
    "mnemonic": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

---

## Why this exists

The full thesis is in [`docs/WHITEPAPER.md`](docs/WHITEPAPER.md):

> Can a compressed shadow index reduce storage cost while preserving retrieval
> quality well enough through exact reranking? Can on-chain commitment make agent
> memory verifiable and tamper-evident without killing usability?

Both questions are answered yes. The compressed retrieval engine (TurboQuant-inspired)
achieves 7.7x compression with >94% recall@10. On-chain commitment via SPL Memo
costs ~$0.001 per attestation. Arweave permanent storage costs ~$0.04 per 1000 memories.

---

## Documentation

### Design & rationale (the "why")
- [`docs/WHITEPAPER.md`](docs/WHITEPAPER.md) — full thesis, compression approach, on-chain commitment
- [`docs/ADR.md`](docs/ADR.md) — all architecture decisions (ADR-001 through ADR-020)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — ingestion, retrieval, storage design
- [`docs/BLOCKERS.md`](docs/BLOCKERS.md) — product + technical blocker analysis
- [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — current phase, gates, remaining work

### Implementation (the "what")
- [`mcp/README.md`](mcp/README.md) — Rust MCP server: setup, config, endpoints
- [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md) — checklist audit vs spec
- [`docs/adr/ADR-020-artifact-schema-registry.md`](docs/adr/ADR-020-artifact-schema-registry.md) — typed artifact schemas (proposed)

### Research
- [`docs/research/`](docs/research/) — TurboQuant analysis, D-RAG landscape, concurrent writers, memory eviction
- [`Agent Identity PDF`](docs/research/) — agent identity protocols survey + Mnemonic positioning

---

## Repository structure

```
mcp/                    Rust MCP server (production backend)
mcp-server/             Python MCP server (reference/MVP)
v0/mnemonic-verify/     Rust CLI — original write/verify proof-of-concept
src/                    Python mnemonic package (retrieval engine prototype)
external/               turboquant_plus submodule
docs/                   Design docs, ADRs, whitepaper, research
```

---

## Key properties

- **Deterministic encoding**: CBOR canonical (RFC 8949 §4.2) → same content always produces same hash
- **Standard signatures**: COSE_Sign1 (RFC 9052) with Ed25519 → verifiable by any COSE library
- **Open embeddings**: fastembed (all-MiniLM-L6-v2, Apache 2.0) → third parties can re-embed and verify
- **Permanent storage**: Arweave → content survives indefinitely
- **Sub-cent anchoring**: Solana SPL Memo → ~$0.001 per attestation
- **Provider-independent**: memory survives model/provider switches
