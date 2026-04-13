# mnemonic-mcp

Verifiable memory attestation primitive for AI agents, delivered as an MCP server.

> Mnemonic gives any AI agent a Solana keypair identity and the ability to create
> permanent, hash-anchored, semantically searchable proofs of its work on Arweave.

## 5 Tools

| Tool | Description |
|------|-------------|
| `mnemonic_whoami` | Returns agent identity: pubkey, did:sol, did:key, attestation count |
| `mnemonic_sign_memory` | Embed + hash + Arweave + Solana SPL Memo → attestation proof |
| `mnemonic_verify` | Fetch anchor + content → recompute hash → Verified/Tampered |
| `mnemonic_prove_identity` | Sign arbitrary challenge with Ed25519 key |
| `mnemonic_recall` | Semantic search over attested memory history |

## Quick start

```bash
cd mcp-server
pip install -r requirements.txt
cp .env.example .env

# Run as MCP server (stdio)
python -m mnemonic_mcp
```

## Claude Code config

```json
{
  "mcpServers": {
    "mnemonic": {
      "command": "python",
      "args": ["-m", "mnemonic_mcp"],
      "cwd": "/path/to/mnemonic-protocol/mcp-server",
      "env": {
        "SOLANA_RPC_URL": "https://api.devnet.solana.com",
        "ARWEAVE_URL": "http://localhost:1984"
      }
    }
  }
}
```

## Local testing

```bash
# Start local nodes
npx arlocal &
solana-test-validator --reset --quiet &

# Run tests
python -m pytest tests/ -v
```

## Architecture

```
MCP Host (Claude Code / Cursor / Codex)
    │ JSON-RPC (stdio)
    ▼
mnemonic-mcp-server
    ├── identity.py      ← Ed25519 keypair, did:sol, did:key
    ├── solana_client.py  ← SPL Memo write/read
    ├── arweave_client.py ← permanent storage write/read
    ├── embed.py          ← fastembed (384-dim, local)
    ├── db.py             ← SQLite attestation index
    ├── tools.py          ← 5 tool implementations
    └── server.py         ← MCP protocol handler
```
