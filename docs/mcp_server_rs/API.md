# Mnemonic MCP Server — API Reference

**Implementation:** `mcp-server-rs` (Rust)  
**Date:** 2026-04-14  
**Status:** Current — `feat/auth` branch

---

## Overview

The server exposes two surfaces:

| Surface | Purpose |
|---------|---------|
| **MCP JSON-RPC** (`POST /mcp`) | Five attestation tools consumed by AI clients |
| **Management REST** | API key lifecycle, balance, deposits, P&L stats |

Both surfaces run on the same HTTP port (default `3000`).  
The stdio transport only exposes the MCP surface (no payment, trusted local client).

---

## MCP JSON-RPC — `POST /mcp`

Follows [JSON-RPC 2.0](https://www.jsonrpc.org/specification) and the [MCP protocol spec `2025-06-18`](https://modelcontextprotocol.io).

### Request envelope

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "mnemonic_sign_memory",
    "arguments": { }
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
| `initialize` | Handshake — returns server capabilities |
| `tools/list` | List all available tools |
| `tools/call` | Invoke a named tool |
| `ping` | Heartbeat |
| `notifications/initialized` | Client-ready notification (no-op) |

---

## MCP Tools

### `mnemonic_whoami`

Returns the server's cryptographic identity and attestation count. Sync, no payment required.

**Input:** _(no arguments)_

**Output:**
```json
{
  "public_key": "8xGz...Kp9",
  "did_sol": "did:sol:8xGz...Kp9",
  "did_key": "did:key:z6Mk...",
  "attestation_count": 42
}
```

---

### `mnemonic_sign_memory`

Creates a verifiable memory attestation. Full pipeline: embed → TurboQuant compress → SHA-256 → Arweave (Irys, ANS-104 signed) → Solana SPL Memo anchor → SQLite index.

**Cost:** charged per call when `PAYMENT_MODE != none` (see [Payment](#payment)).

**Input:**
```json
{
  "content": "string (required) — text to attest",
  "tags":    ["string"] "(optional)"
}
```

**Output:**
```json
{
  "attestation_id":  "uuid",
  "content_hash":    "sha256 hex",
  "solana_tx":       "base58 tx signature",
  "arweave_tx":      "base64url tx id",
  "signer":          "base58 pubkey",
  "did_sol":         "did:sol:...",
  "timestamp":       "ISO 8601",
  "embed_provider":  "hash | openai",
  "embed_dim":       384,
  "compression": {
    "algorithm":        "TurboQuant",
    "bits":             4,
    "ratio":            "32.0x",
    "original_bytes":   1536,
    "compressed_bytes": 48
  }
}
```

---

### `mnemonic_verify`

Fetches and cross-checks an attestation. Reads the Solana memo for the content hash and Arweave TX ID, fetches Arweave payload, recomputes SHA-256, compares.

**Input:** _(at least one required)_
```json
{
  "solana_tx":  "base58 tx signature (optional)",
  "arweave_tx": "base64url tx id (optional)"
}
```

**Output — verified:**
```json
{
  "status":          "verified",
  "content_hash":    "sha256 hex",
  "solana_tx":       "...",
  "arweave_tx":      "...",
  "signer":          "base58 pubkey",
  "content_preview": "first 200 chars",
  "has_compressed_embedding": true
}
```

**Output — tampered:**
```json
{
  "status":        "tampered",
  "expected_hash": "...",
  "actual_hash":   "..."
}
```

**Other statuses:** `anchor_not_found`, `arweave_not_found`, `hash_computed`

---

### `mnemonic_prove_identity`

Signs an arbitrary challenge with the server's Ed25519 key. Pure crypto, no network calls, no payment.

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
  "did_sol":    "did:sol:...",
  "challenge":  "...",
  "signature":  "hex (128 chars)",
  "algorithm":  "Ed25519"
}
```

---

### `mnemonic_recall`

Semantic search over the local attestation index using cosine similarity on stored embeddings.

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
  "query":               "...",
  "embed_provider":      "hash | openai",
  "total_attestations":  42,
  "results": [
    {
      "attestation_id":  "uuid",
      "content":         "...",
      "content_hash":    "sha256 hex",
      "tags":            ["..."],
      "solana_tx":       "...",
      "arweave_tx":      "...",
      "created_at":      "ISO 8601",
      "relevance_score": 0.94
    }
  ]
}
```

---

## Payment

`mnemonic_sign_memory` is the only paid tool. Set `PAYMENT_MODE` in env:

| Mode | Behaviour |
|------|-----------|
| `none` | Open access — no payment required (default, local dev) |
| `balance` | `Authorization: Bearer mnm_<key>` header; balance deducted on success |
| `x402` | `X-Payment: <json>` header with verified Solana USDC tx |
| `both` | Balance checked first; x402 accepted as fallback |

### Balance mode — Authorization header

```
Authorization: Bearer mnm_6a2f...c91d
```

Balance is deducted **after** successful tool execution. Insufficient balance returns HTTP 401.

### x402 mode — per-call USDC payment

**Step 1 — no payment header:** server returns HTTP 402
```json
{
  "x402Version": 1,
  "accepts": [{
    "scheme":             "exact",
    "network":            "solana-mainnet",
    "maxAmountRequired":  "1284",
    "asset":              "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "payTo":              "<TREASURY_PUBKEY>",
    "description":        "mnemonic_sign_memory attestation fee"
  }]
}
```

**Step 2 — retry with payment proof:**
```
X-Payment: {"tx_sig":"<base58 solana tx>","network":"solana-mainnet"}
```
or base64-encoded JSON (Coinbase CDK format).

The server verifies the on-chain USDC transfer (SPL token balance delta), marks the tx sig as used (replay prevention), then proceeds.

---

## Management Endpoints

### `POST /api-keys`

Create a new pre-funded API key with zero initial balance.

**Request:**
```json
{ "owner_pubkey": "base58 (optional)" }
```

**Response `200`:**
```json
{
  "api_key":            "mnm_6a2f...c91d",
  "balance_micro_usdc": 0
}
```

---

### `GET /balance?api_key=<key>`

Query balance for an API key.

**Response `200`:**
```json
{
  "api_key":            "mnm_6a2f...c91d",
  "balance_micro_usdc": 42000,
  "balance_usdc":       0.042
}
```

**Response `404`:** key not found.

---

### `POST /deposit`

Credit a confirmed on-chain USDC transfer to an API key balance.

The caller must first send USDC to `TREASURY_PUBKEY` on Solana, then POST the tx sig. The server verifies the SPL token balance delta and credits the key.

**Request:**
```json
{
  "api_key": "mnm_6a2f...c91d",
  "tx_sig":  "base58 solana tx signature"
}
```

**Response `200`:**
```json
{
  "api_key":               "mnm_6a2f...c91d",
  "deposited_micro_usdc":  50000,
  "new_balance_micro_usdc": 92000
}
```

**Response `400`:** tx does not transfer USDC to treasury, or already applied.  
**Response `502`:** Solana RPC error.

---

### `GET /admin/stats?days=<N>`

P&L dashboard. Aggregates over the last `N` days (default `7`).

**Response `200`:**
```json
{
  "period_days":          7,
  "attestations":         142,
  "earned_micro_usdc":    142000,
  "earned_usdc":          0.142,
  "cost_sol_lamports":    1291200,
  "cost_micro_usdc_equiv": 91000,
  "cost_usdc_equiv":      0.091,
  "net_micro_usdc":       51000,
  "net_usdc":             0.051,
  "margin_pct":           35.9,
  "avg_sol_price_usdc":   142.5,
  "pricing": {
    "current_price_micro_usdc": 1284,
    "current_sol_price_usdc":   142.5,
    "current_irys_lamports":    4200
  }
}
```

---

### `GET /health`

Liveness check.

```json
{ "status": "ok" }
```

---

## Error Responses

### JSON-RPC errors (MCP surface)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": { "code": -32603, "message": "..." }
}
```

| Code | Meaning |
|------|---------|
| `-32700` | Parse error |
| `-32603` | Internal / tool error |
| `-32600` | Payment / auth error |

### HTTP errors (management surface)

```json
{ "error": "human-readable message" }
```

| Status | Meaning |
|--------|---------|
| `400` | Bad request / validation |
| `401` | Missing or invalid auth |
| `402` | Payment required (x402 body) |
| `404` | Resource not found |
| `500` | Server error |
| `502` | Upstream RPC error |
