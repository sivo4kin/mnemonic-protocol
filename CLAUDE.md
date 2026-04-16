# CLAUDE.md

## Project overview

Mnemonic is a verifiable memory and artifact infrastructure for AI agents. The canonical implementation is a Rust MCP server in `mcp/` that gives agents a cryptographic identity, durable local or on-chain memory, and tamper-evident, semantically searchable artifacts.

## Quick reference

```bash
# Build
cd mcp && cargo build --release

# Build with local embeddings (recommended for production)
cd mcp && cargo build --release --features local-embed

# Run tests (64 total: 56 unit + 5 integration + 3 proptest)
cd mcp && cargo test

# Run HTTP server (local mode, no blockchain needed)
cd mcp && cargo run -- --transport http --port 3000

# Run stdio server (for Claude Code local integration)
cd mcp && cargo run -- --transport stdio

# Benchmarks
cd mcp && cargo bench --bench decompress
cd mcp && cargo bench --bench cbor_codec
```

## Repository structure

```
mcp/                        # Canonical Rust MCP implementation (all active code)
  src/
    main.rs                 # CLI, HTTP router (Axum), stdio loop, payment-aware entrypoint
    mcp.rs                  # JSON-RPC 2.0 dispatcher, McpState, tool routing
    tools.rs                # 7 MCP tool implementations (whoami, sign_memory, verify, etc.)
    db.rs                   # SQLite store: attestations, embeddings, payments, P&L
    config.rs               # Environment config (all settings from env vars / .env)
    identity.rs             # Ed25519 keypair load/create, did:sol, did:key helpers
    embed.rs                # Embedder trait + implementations (fastembed, OpenAI, hash-test)
    compress.rs             # TurboQuant embedding compression
    lineage.rs              # Parent DAG storage, cycle detection, chain verification
    arweave.rs              # Arweave client (read/write bytes)
    solana.rs               # Solana memo write/read, USDC transfer verification
    payment.rs              # Payment gate logic (balance, x402)
    pricing.rs              # Dynamic pricing engine (Irys + SOL/USD refresh)
    codec/
      mod.rs                # Codec module root
      canonical.rs          # Deterministic CBOR encoding/decoding (RFC 8949)
      hash.rs               # blake3 content hashing
      schema.rs             # Immutable artifact schema registry (5 types)
      sign.rs               # COSE_Sign1 signing and verification
  tests/
    integration_cbor.rs     # CBOR/COSE pipeline integration tests
    proptest_canonical.rs   # Property-based canonicalization tests
  scripts/
    run-tests.sh            # Full test suite runner
    test-http.sh            # HTTP API smoke tests
    start-local.sh          # Local Solana/Arweave node startup
  Cargo.toml                # Dependencies, features, bench config

docs/                       # Documentation
  versions/v0.0.3/          # Current spec and API docs (implementation truth)
  IMPLEMENTATION_AUDIT.md   # Detailed done/partial/not-done checklist
  IMPLEMENTATION_STATUS.md  # Current vs. historical scope clarity
  adr/                      # Architecture decision records (historical lineage)
  research/                 # Research notes and analyses
  usecases/                 # Product use cases and principles

legacy/                     # Historical prototype snapshots (v0.0.0, v0.0.1)
external/                   # Git submodule: turboquant_plus
```

## Architecture

The server uses a two-layer encoding model:
- **External API surface:** JSON-RPC 2.0 over HTTP or stdio
- **Internal signed artifact format:** canonical CBOR + COSE_Sign1 + blake3

**Sign-memory pipeline:** content -> embed -> TurboQuant compress -> build artifact JSON -> canonical CBOR -> blake3 hash -> COSE_Sign1 sign -> persist (SQLite, optionally Arweave + Solana)

**MCP tools:**
| Tool | Purpose |
|------|---------|
| `mnemonic_whoami` | Agent identity (pubkey, DIDs, attestation count) |
| `mnemonic_sign_memory` | Create signed memory artifact |
| `mnemonic_verify` | Verify artifact integrity and signature |
| `mnemonic_prove_identity` | Sign challenge with Ed25519 |
| `mnemonic_lineage` | Traverse parent DAG |
| `mnemonic_verify_chain` | Full DAG verification |
| `mnemonic_recall` | Semantic search over stored embeddings |

**Storage modes:**
- `local` (default): SQLite only, free, no blockchain, synthetic tx IDs
- `full`: Arweave + Solana + SQLite, payment gate active

**Transports:**
- HTTP (Axum, `POST /mcp` + management endpoints)
- stdio (JSON-RPC over stdin/stdout, payment bypassed)

## Key conventions

### Rust patterns
- **Edition 2021**, async runtime is tokio
- Error handling: `anyhow::Result<T>` for most operations, `thiserror` for custom error types
- SQLite via `rusqlite` (not Sync): wrapped in `std::sync::Mutex`, never held across `.await`
- `unsafe impl Send/Sync for McpState` is used because the Mutex discipline is maintained manually
- Logging: `tracing` crate, configured via `RUST_LOG` env var

### Feature flags
- `local-embed`: enables fastembed (local ONNX all-MiniLM-L6-v2, 384-dim). Without this flag, OpenAI embeddings or build failure
- Default features: none (fastembed is opt-in)

### Testing
- Unit tests are `#[cfg(test)]` modules inline in source files
- Integration tests in `mcp/tests/`
- Property-based tests use `proptest` for CBOR determinism validation
- `HashEmbedder` is test-only (deterministic but not semantic) -- never used in production
- `AttestationStore::in_memory()` for test fixtures

### Schema immutability
- Schema versions are immutable once published
- CBOR field order must never change within a schema version
- Five artifact types: `memory`, `rag.context`, `rag.result`, `agent.state`, `receipt`
- Adding fields requires a version bump

### Lineage constraints
- Max 16 parents per artifact (`MAX_PARENTS`)
- Max 64 depth for cycle detection (`MAX_DEPTH`)
- DFS cycle detection runs before any write
- Parent references stored in `artifact_lineage` SQLite table

## Configuration

All config is from environment variables (loaded via `dotenvy` from `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_MODE` | `local` | `local` or `full` |
| `MCP_TRANSPORT` | `http` | `stdio` or `http` |
| `MCP_HTTP_PORT` | `3000` | HTTP listen port |
| `EMBED_PROVIDER` | `fastembed` | `fastembed` or `openai` |
| `OPENAI_API_KEY` | _(empty)_ | Required for `openai` provider |
| `MNEMONIC_KEYPAIR_PATH` | `~/.mnemonic/id.json` | Ed25519 keypair |
| `DATABASE_PATH` | `~/.mnemonic/attestations.db` | SQLite path |
| `TURBO_BITS` | `4` | TurboQuant bit width |
| `PAYMENT_MODE` | `none` | `none`, `balance`, `x402`, `both` |
| `SOLANA_RPC_URL` | `http://localhost:8899` | Solana RPC endpoint |
| `ARWEAVE_URL` | `http://localhost:1984` | Arweave gateway |

## Documentation hierarchy (when docs disagree)

1. **Implementation truth:** `mcp/` source code + `docs/versions/v0.0.3/*`
2. **Historical/research context:** `docs/research/*`, `docs/adr/*`, `legacy/`

The split between current implementation and historical research lineage is intentional and explicit. Do not treat ADRs or research docs as descriptions of current behavior.

## Common development tasks

### Adding a new MCP tool
1. Define the tool function in `mcp/src/tools.rs`
2. Add tool definition JSON in `tool_definitions()` in `mcp/src/mcp.rs`
3. Add dispatch case in `handle_tool_call()` in `mcp/src/mcp.rs`
4. Add tests in the relevant source file's `#[cfg(test)]` module

### Adding a new artifact schema
1. Define the schema constant in `mcp/src/codec/schema.rs`
2. Add the type variant to `ArtifactType` enum
3. Add lookup case in `get_schema()`
4. Ensure `cbor_field_order` covers all required fields

### Running the full verification flow
```bash
# Local mode (no external deps)
STORAGE_MODE=local cargo run -- --transport http --port 3000

# Full mode (requires local Solana + Arweave)
bash mcp/scripts/start-local.sh
STORAGE_MODE=full cargo run -- --transport http --port 3000
```

## Dependencies of note

- `turboquant` — git dependency from `sivo4kin/turboquant-rs` (custom embedding compression)
- `fastembed` — optional, enables local ONNX inference (~22MB model download on first run)
- `solana-sdk` 2.2 — Solana keypair, signing, transaction types
- `coset` 0.3 — COSE_Sign1 standard library
- `ciborium` 0.2 — Deterministic CBOR (RFC 8949)
- `blake3` — Content hashing for current artifacts (replaced SHA-256)
