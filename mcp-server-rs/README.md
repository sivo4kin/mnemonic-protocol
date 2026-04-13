# mnemonic-mcp (Rust)

Verifiable memory attestation MCP server for AI agents. Rust implementation.

> Mnemonic gives any AI agent a Solana keypair identity and the ability to create
> permanent, hash-anchored, semantically searchable proofs of its work on Arweave.

## Transports

| Mode | Use case | Config |
|------|----------|--------|
| **HTTP** (default) | Remote MCP server in Claude Code, Cursor, etc. | `--transport http --port 3000` |
| **stdio** | Local MCP server via command | `--transport stdio` |

## Quick start

```bash
cargo build --release

# HTTP mode (remote server)
./target/release/mnemonic-mcp --transport http --port 3000

# stdio mode (local)
./target/release/mnemonic-mcp --transport stdio
```

## Claude Code config (remote)

```json
{
  "mcpServers": {
    "mnemonic": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

## Claude Code config (local)

```json
{
  "mcpServers": {
    "mnemonic": {
      "command": "./target/release/mnemonic-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

## 5 Tools

| Tool | Description |
|------|-------------|
| `mnemonic_whoami` | Agent identity: pubkey, did:sol, did:key, attestation count |
| `mnemonic_sign_memory` | Embed + SHA-256 + Arweave + Solana SPL Memo → proof |
| `mnemonic_verify` | Fetch anchor + content → recompute hash → Verified/Tampered |
| `mnemonic_prove_identity` | Ed25519 challenge-response signing |
| `mnemonic_recall` | Semantic search over attested memory history |

## Testing

```bash
# Unit tests (no infra needed)
cargo test --lib

# Start local test nodes
bash scripts/start-local.sh

# HTTP API tests
cargo run -- --transport http --port 3000 &
bash scripts/test-http.sh 3000

# Full test suite
bash scripts/run-tests.sh

# Benchmark tests
cargo bench --bench decompress
cargo bench --bench decompress -- "embedding_decompress/4bit/384"
```

## Architecture

```
                    ┌─────────────────┐
                    │  MCP Client     │
                    │  (Claude Code)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │ stdio        │ HTTP POST    │
              ▼              ▼              │
    ┌─────────────────────────────────┐    │
    │     mnemonic-mcp (Rust)         │    │
    │  ┌──────────┐  ┌────────────┐  │    │
    │  │ identity  │  │ MCP proto  │  │    │
    │  │ Ed25519   │  │ JSON-RPC   │  │    │
    │  └──────────┘  └────────────┘  │    │
    │  ┌──────────┐  ┌────────────┐  │    │
    │  │ embed    │  │ SQLite     │  │    │
    │  │ 384-dim  │  │ attestation│  │    │
    │  └──────────┘  └────────────┘  │    │
    └──────┬──────────────┬──────────┘    │
           │              │               │
    ┌──────▼──────┐ ┌────▼─────┐         │
    │  Solana RPC │ │ Arweave  │         │
    │  SPL Memo   │ │ Gateway  │         │
    └─────────────┘ └──────────┘         │
```

## Environment

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `http` | `stdio` or `http` |
| `MCP_HTTP_PORT` | `3000` | HTTP listen port |
| `SOLANA_RPC_URL` | `http://localhost:8899` | Solana RPC |
| `ARWEAVE_URL` | `http://localhost:1984` | Arweave gateway |
| `MNEMONIC_KEYPAIR_PATH` | `~/.mnemonic/id.json` | Ed25519 keypair |
| `DATABASE_PATH` | `~/.mnemonic/attestations.db` | SQLite path |
