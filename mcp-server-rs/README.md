# mnemonic-mcp (Rust)

Verifiable memory attestation MCP server for AI agents. Rust implementation.

> Mnemonic gives any AI agent a Solana keypair identity and the ability to create
> permanent, hash-anchored, semantically searchable proofs of its work on Arweave.

## Status

This is the **production-oriented backend** in the repository.

Current code includes:

- MCP over **HTTP** and **stdio**
- 5 core attestation tools
- SQLite recall index
- hash or OpenAI embeddings
- TurboQuant compression of stored Arweave payload embeddings
- payment modes: `none`, `balance`, `x402`, `both`
- API key creation, balance lookup, deposit crediting
- dynamic pricing engine
- admin stats and health endpoints

Current caveats to be aware of:

- balance mode currently reserves configured cost before execution and refunds on failure
- live dynamic quoted price and reserved balance amount can diverge in current code
- `/deposit` verifies treasury + mint transfer, but full transaction-signer ownership verification is still TODO
- `/admin/stats` is unauthenticated in-app and should be protected externally in production

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
| `mnemonic_sign_memory` | Embed + TurboQuant + SHA-256 + Arweave + Solana SPL Memo → proof |
| `mnemonic_verify` | Fetch anchor + content → recompute hash → Verified/Tampered |
| `mnemonic_prove_identity` | Ed25519 challenge-response signing |
| `mnemonic_recall` | Semantic search over attested memory history |

## HTTP endpoints

- `POST /mcp`
- `POST /api-keys`
- `GET /balance?api_key=...`
- `POST /deposit`
- `GET /admin/stats?days=7`
- `GET /health`

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
    │  │ hash/OAI │  │ + payments │  │    │
    │  └──────────┘  └────────────┘  │    │
    │  ┌──────────┐  ┌────────────┐  │    │
    │  │ compress │  │ pricing    │  │    │
    │  │ TurboQnt │  │ + x402     │  │    │
    │  └──────────┘  └────────────┘  │    │
    └──────┬──────────────┬──────────┘    │
           │              │               │
    ┌──────▼──────┐ ┌────▼─────┐         │
    │  Solana RPC │ │ Arweave  │         │
    │  SPL Memo   │ │ / Irys   │         │
    └─────────────┘ └──────────┘         │
```

## Environment

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `http` | `stdio` or `http` |
| `MCP_HTTP_HOST` | `0.0.0.0` | HTTP listen host |
| `MCP_HTTP_PORT` | `3000` | HTTP listen port |
| `SOLANA_RPC_URL` | `http://localhost:8899` | Solana RPC |
| `ARWEAVE_URL` | `http://localhost:1984` | Arweave gateway |
| `MNEMONIC_KEYPAIR_PATH` | `~/.mnemonic/id.json` | Ed25519 keypair |
| `DATABASE_PATH` | `~/.mnemonic/attestations.db` | SQLite path |
| `EMBED_PROVIDER` | `hash` | `hash` or `openai` |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | OpenAI embeddings model |
| `TURBO_BITS` | `4` | TurboQuant bit width |
| `PAYMENT_MODE` | `none` | `none`, `balance`, `x402`, `both` |
| `TREASURY_PUBKEY` | _(empty)_ | Solana treasury pubkey |
| `USDC_MINT` | mainnet USDC | SPL token mint for payment verification |
| `SIGN_MEMORY_COST_MICRO_USDC` | `1000` | Base/floor configured sign-memory charge |
| `PRICE_REFRESH_SECS` | `1800` | Dynamic pricing refresh interval |
| `PRICING_MARGIN_BPS` | `2000` | Pricing margin in basis points |
| `TYPICAL_PAYLOAD_BYTES` | `2048` | Irys quote payload size assumption |
| `SOL_TX_FEE_LAMPORTS` | `5000` | Memo tx fee estimate |
