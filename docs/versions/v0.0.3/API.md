# Mnemonic MCP Server — API Reference

**Implementation:** `mcp` (Rust)  
**Date:** 2026-04-15  
**Status:** Updated to current `main`

---

## Overview

The server exposes two surfaces:

| Surface | Purpose |
|---------|---------|
| **MCP JSON-RPC** (`POST /mcp`) | Five Mnemonic tools consumed by AI clients |
| **Management REST** | API key lifecycle, balance, deposits, P&L stats |

Both surfaces run on the same HTTP port (default `3000`).  
The stdio transport only exposes the MCP surface.

Current implementation also has two storage modes:

| Storage mode | Meaning |
|--------------|---------|
| `local` | SQLite only, no Solana/Arweave writes, synthetic tx ids |
| `full` | Arweave + Solana + SQLite |

---

## MCP JSON-RPC — `POST /mcp`

Follows JSON-RPC 2.0 and the MCP handler shape implemented in `mcp/src/mcp.rs`.

### Request envelope

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "mnemonic_sign_memory",
    "arguments": {
      "content": "hello world"
    }
  }
}
```

### Response envelope

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "{ ... }"}]
  }
}
```

### Supported methods

| Method | Description |
|--------|-------------|
| `initialize` | Handshake — returns protocol version, capabilities, serverInfo |
| `tools/list` | List all available tools |
| `tools/call` | Invoke a named tool |
| `ping` | Heartbeat/no-op |
| `notifications/initialized` | Client-ready notification (no-op) |

### `initialize` response

```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": {"tools": {}},
  "serverInfo": {"name": "mnemonic", "version": "0.1.0"}
}
```

---

## Tool semantics

Current implementation uses:

- **developer-facing JSON** at the MCP boundary
- **canonical CBOR + COSE_Sign1** for the signed artifact format
- **blake3** for current artifact hashing
- legacy JSON + SHA-256 verification fallback for older artifacts

---

## MCP Tools

### `mnemonic_whoami`

Returns the server's cryptographic identity, attestation count, and storage mode.

**Input:** _(no arguments)_

**Output:**
```json
{
  "public_key": "8xGz...Kp9",
  "did_sol": "did:sol:8xGz...Kp9",
  "did_key": "did:key:z6Mk...",
  "attestation_count": 42,
  "storage_mode": "local"
}
```

---

### `mnemonic_sign_memory`

Creates a signed memory artifact.

Current pipeline:

1. embed content
2. TurboQuant-compress embedding
3. build typed artifact JSON
4. canonicalize to CBOR
5. compute **blake3** hash
6. sign as **COSE_Sign1**
7. persist to:
   - SQLite only in `local` mode
   - Arweave + Solana + SQLite in `full` mode

**Cost:** charged per call on HTTP when `PAYMENT_MODE != none` and `STORAGE_MODE != local`.

**Input:**
```json
{
  "content": "string (required)",
  "tags": ["string"]
}
```

**Output:**
```json
{
  "attestation_id": "uuid",
  "content_hash": "blake3 hex",
  "hash_algorithm": "blake3",
  "encoding": "cbor+cose",
  "solana_tx": "base58 tx signature or local:*",
  "arweave_tx": "arweave tx id or local:*",
  "signer": "base58 pubkey",
  "did_sol": "did:sol:...",
  "timestamp": "ISO 8601",
  "storage_mode": "local",
  "embedding": {
    "model": "all-MiniLM-L6-v2",
    "provider": "fastembed",
    "dim": 384,
    "verifiable": true
  },
  "compression": {
    "algorithm": "TurboQuant",
    "bits": 4,
    "ratio": "32.0x",
    "original_bytes": 1536,
    "compressed_bytes": 48
  }
}
```

Notes:

- current production providers are `fastembed` and `openai`
- hash embedder is test-only
- `verifiable=true` means open-weight embeddings are used and third parties can re-embed independently
- `storage_mode=local` returns synthetic ids like `local:abcd1234`

---

### `mnemonic_verify`

Verifies a memory artifact.

Behavior depends on artifact/storage mode:

- **current full artifacts:** COSE verification + integrity checks
- **legacy full artifacts:** raw JSON + SHA-256 fallback verification
- **local mode:** SQLite lookup + local integrity check

**Input:** _(at least one required)_
```json
{
  "solana_tx": "base58 tx signature (optional)",
  "arweave_tx": "tx id (optional)"
}
```

**Current full-mode verified output:**
```json
{
  "status": "verified",
  "encoding": "cbor+cose",
  "checks": {
    "content_integrity": true,
    "cose_signature": true,
    "algorithm_valid": true
  },
  "content_hash": "blake3 hex",
  "hash_algorithm": "blake3",
  "solana_tx": "...",
  "arweave_tx": "...",
  "signer": "base58 pubkey",
  "content_preview": "first 200 chars"
}
```

**Legacy fallback output shape:**
```json
{
  "status": "verified",
  "encoding": "json+sha256 (legacy v1)",
  "content_hash": "sha256 hex",
  "hash_algorithm": "sha256",
  "solana_tx": "...",
  "arweave_tx": "...",
  "signer": "...",
  "content_preview": "..."
}
```

**Local mode output shape:**
```json
{
  "status": "verified",
  "storage_mode": "local",
  "content_hash": "...",
  "solana_tx": "local:...",
  "arweave_tx": "local:...",
  "signer": "...",
  "content_preview": "...",
  "note": "local mode checks content integrity; full COSE verification requires STORAGE_MODE=full"
}
```

Possible statuses include:

- `verified`
- `tampered`
- `anchor_not_found`
- `arweave_not_found`
- `hash_computed`
- `not_found`
- `error`

---

### `mnemonic_prove_identity`

Signs an arbitrary challenge with the server's Ed25519 key.

**Input:**
```json
{
  "challenge": "string (required)"
}
```

**Output:**
```json
{
  "public_key": "base58",
  "did_sol": "did:sol:...",
  "challenge": "...",
  "signature": "hex (128 chars)",
  "algorithm": "Ed25519"
}
```

---

### `mnemonic_recall`

Semantic search over the local SQLite attestation index using stored full embeddings.

**Input:**
```json
{
  "query": "string (required)",
  "limit": 5
}
```

**Output:**
```json
{
  "query": "...",
  "results": [
    {
      "attestation_id": "uuid",
      "content": "...",
      "content_hash": "...",
      "tags": ["..."],
      "solana_tx": "...",
      "arweave_tx": "...",
      "created_at": "ISO 8601",
      "relevance_score": 0.94
    }
  ],
  "total_attestations": 42,
  "embed_provider": "fastembed",
  "embed_model": "all-MiniLM-L6-v2",
  "verifiable": true
}
```

Note:
- current recall path queries full embeddings from SQLite
- compressed embeddings are produced during signing, but local recall does not yet run through a compressed index

---

## Storage model

### `STORAGE_MODE=local`

- default mode in current config
- SQLite only
- no Solana / Arweave writes
- no sign-memory payment enforcement on HTTP
- ideal for offline development and UX testing

### `STORAGE_MODE=full`

- writes COSE bytes to Arweave
- writes anchor memo to Solana
- stores searchable embeddings in SQLite
- payment gate applies on HTTP when enabled

---

## Payment

`mnemonic_sign_memory` is the only paid tool on HTTP.

Payment gate is active only when:

- `PAYMENT_MODE != none`
- `STORAGE_MODE != local`

| Mode | Behaviour |
|------|-----------|
| `none` | Open access |
| `balance` | `Authorization: Bearer mnm_<key>` header; balance checked and reserved |
| `x402` | `X-Payment: <json>` header with verified Solana USDC tx |
| `both` | balance or x402 |

### Balance mode

Current code behavior:

- checks balance against the **live pricing engine quote**
- reserves `SIGN_MEMORY_COST_MICRO_USDC` before execution
- refunds on tool failure

Caveat:

- quoted price and reserved amount can diverge in current code if dynamic price differs from configured floor/base charge

### x402 mode

Step 1: request without payment returns HTTP 402 body.

Step 2: retry with:

```text
X-Payment: {"tx_sig":"<base58 solana tx>","network":"solana-mainnet"}
```

The server verifies the USDC transfer and marks the tx sig as used.

---

## Management Endpoints

### `POST /api-keys`

Create a new API key.

**Request:**
```json
{ "owner_pubkey": "base58 (optional)" }
```

**Response:**
```json
{
  "api_key": "mnm_...",
  "balance_micro_usdc": 0
}
```

---

### `GET /balance?api_key=<key>`

**Response:**
```json
{
  "api_key": "mnm_...",
  "balance_micro_usdc": 42000,
  "balance_usdc": 0.042
}
```

---

### `POST /deposit`

Credits a verified USDC transfer to an API key.

Current code verifies:

- transfer reached treasury
- mint matches configured USDC mint
- API key has an `owner_pubkey`
- **owner pubkey is a signer of the deposit transaction**

**Request:**
```json
{
  "api_key": "mnm_...",
  "tx_sig": "base58 solana tx signature"
}
```

**Success response:**
```json
{
  "api_key": "mnm_...",
  "deposited_micro_usdc": 50000,
  "new_balance_micro_usdc": 92000
}
```

Potential error classes:

- invalid treasury or mint transfer
- owner pubkey missing on API key
- owner pubkey not among tx signers
- duplicate deposit tx
- Solana RPC failure

---

### `GET /admin/stats?days=<N>`

Returns aggregated P&L and current pricing info.

### `GET /health`

Returns:

```json
{ "status": "ok" }
```

---

## Error Responses

### JSON-RPC errors

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": { "code": -32603, "message": "..." }
}
```

### HTTP errors

```json
{ "error": "human-readable message" }
```
