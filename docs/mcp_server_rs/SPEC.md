# Mnemonic MCP Server — Technical Specification

**Implementation:** `mcp-server-rs` (Rust)  
**Date:** 2026-04-14  
**Status:** Current — `feat/auth` branch

---

## 1. Purpose

`mcp-server-rs` is the core production component of the Mnemonic Protocol. It gives any AI agent a persistent, verifiable memory layer by:

1. Embedding user-provided content using configurable vector models
2. Compressing embeddings with TurboQuant (32x ratio, lossless enough for semantic search)
3. Storing the payload permanently on Arweave via Irys (signed ANS-104 bundle item)
4. Anchoring the SHA-256 content hash on Solana via an SPL Memo transaction
5. Indexing locally in SQLite for fast cosine-similarity recall
6. Charging callers via pre-funded API keys (humans) or x402 USDC micropayments (autonomous agents)

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MCP Clients                               │
│   Claude Code · Cursor · Claude Desktop · Autonomous Agent  │
└────────────────────────┬─────────────────────────────────────┘
                         │  JSON-RPC 2.0
              ┌──────────┴──────────┐
              │   stdio             │  HTTP POST /mcp
              │  (trusted local)    │  + payment gate
              └──────────┬──────────┘
                         │
         ┌───────────────▼────────────────────┐
         │          mnemonic-mcp (Rust)        │
         │                                    │
         │  ┌─────────┐  ┌────────────────┐   │
         │  │identity  │  │   MCP proto    │   │
         │  │Ed25519   │  │   JSON-RPC 2.0 │   │
         │  └─────────┘  └────────────────┘   │
         │  ┌─────────┐  ┌────────────────┐   │
         │  │ embed   │  │   payment      │   │
         │  │hash/OAI │  │  balance+x402  │   │
         │  └─────────┘  └────────────────┘   │
         │  ┌─────────┐  ┌────────────────┐   │
         │  │TurboQnt │  │    pricing     │   │
         │  │compress │  │  Irys+CoinGecko│   │
         │  └─────────┘  └────────────────┘   │
         │  ┌─────────────────────────────┐   │
         │  │        SQLite               │   │
         │  │  attestations · api_keys    │   │
         │  │  payment_events · costs     │   │
         │  └─────────────────────────────┘   │
         └──────────┬───────────────┬──────────┘
                    │               │
        ┌───────────▼────┐  ┌───────▼──────────┐
        │  Solana RPC    │  │  Arweave / Irys   │
        │  SPL Memo tx   │  │  ANS-104 upload   │
        └────────────────┘  └──────────────────┘
```

---

## 3. Transports

### HTTP (default)

Axum 0.8 server on `0.0.0.0:3000`.  
Exposes both the MCP JSON-RPC surface (`POST /mcp`) and the management REST API.  
Payment gating applies to `mnemonic_sign_memory` at the HTTP handler layer.

### stdio

Reads JSON-RPC lines from stdin, writes to stdout.  
Used by Claude Code's local MCP integration.  
**Payment is bypassed** — stdio callers are trusted (same machine as server).

---

## 4. Identity

Each server instance has a single Ed25519 keypair loaded from `MNEMONIC_KEYPAIR_PATH` (auto-generated if absent).

The keypair serves three purposes:
- **Arweave signing** — signs ANS-104 bundle items for Irys (signer type 3 = SOLANA)
- **Solana transactions** — pays for and signs SPL Memo anchoring transactions
- **Identity proofs** — `mnemonic_prove_identity` challenge-response

DIDs derived from the keypair:
- `did:sol:<base58_pubkey>` — Solana DID
- `did:key:z6Mk...` — W3C DID Key (Ed25519)

---

## 5. Sign-Memory Pipeline

```
content
  │
  ├─ embed()          → f32[384] (hash-based offline or OpenAI text-embedding-3-small)
  │
  ├─ TurboQuant       → compressed bytes (4-bit, 32x ratio vs f32)
  │
  ├─ SHA-256          → content_hash (hex)
  │
  ├─ Arweave write    → arweave_tx
  │   └─ ANS-104 data item, signed with server Ed25519 keypair
  │   └─ tags: Content-Type=application/json, App-Name=mnemonic-protocol
  │   └─ payload JSON includes: content, hash, tags, signer, timestamp,
  │                              embedding_compressed (base64), embed_provider/dim/bits
  │
  ├─ Solana SPL Memo  → solana_tx
  │   └─ memo JSON: {"h": content_hash, "a": arweave_tx, "v": 1}
  │
  └─ SQLite save      → attestation_id (UUID)
      ├─ attestations row (content, hash, tags, tx ids, signer, timestamp)
      ├─ attestation_embeddings row (full f32 vector for cosine search)
      └─ attestation_costs row (irys_lamports, tx_fee, sol_price, earned)
```

---

## 6. Embedding & Compression

### Embedder (`embed_provider`)

| Value | Backend | Dimension | Notes |
|-------|---------|-----------|-------|
| `hash` (default) | SHA-256 shards, offline | 384 | No API calls, deterministic |
| `openai` | `text-embedding-3-small` | 1536 | Requires `OPENAI_API_KEY` |

### TurboQuant compression

Scalar quantisation on embedding values. Default `TURBO_BITS=4`.

| Bits | Compression ratio | Storage (384-dim) |
|------|------------------|-------------------|
| 2 | 64x | 12 bytes |
| 3 | 42.7x | 18 bytes |
| 4 | 32x | 24 bytes |

The full f32 vector is stored locally in SQLite for accurate cosine recall.  
The compressed vector is stored on Arweave to enable future remote index reconstruction.

---

## 7. Arweave Storage (Irys Production)

### ANS-104 data item format

All production uploads use the Irys/Bundlr bundle item format (SOLANA signer type 3):

```
[sig_type: u16 = 3]          2 bytes
[signature: Ed25519]         64 bytes
[pubkey: Ed25519]            32 bytes
[target: absent]             1 byte (0x00)
[anchor: absent]             1 byte (0x00)
[num_tags: u64 LE]           8 bytes
[tags_bytes_len: u64 LE]     8 bytes
[tags: Avro-encoded]         variable
[data: payload bytes]        variable
```

**Signing message:** `deep_hash(["dataitem", "1", "3", pubkey, "", "", avro_tags, data])`  
**Deep hash:** SHA-384 based recursive hash per Arweave ANS-104 spec.

### arlocal (development)

When `ARWEAVE_URL` points to localhost, a simplified unsigned stub transaction is sent to arlocal. No real signing or payment required.

---

## 8. Solana Anchoring

`mnemonic_sign_memory` writes one SPL Memo transaction per attestation:

```json
{"h": "<sha256_hex>", "a": "<arweave_tx_id>", "v": 1}
```

The transaction is signed by the server keypair and confirmed (`confirmed` or `finalized` status).

**`mnemonic_verify`** reads this memo back via `getTransaction` (jsonParsed encoding), extracts the hash and Arweave TX ID, fetches the Arweave payload, and recomputes the SHA-256 hash for comparison.

---

## 9. Payment Architecture

Two payment paths run in parallel. Set via `PAYMENT_MODE`.

### Path A — Pre-funded balance (Cursor, Claude Desktop, humans)

MCP clients that cannot self-sign transactions (standard Cursor/Claude Desktop) use this path.

```
Operator                       MCP Client
   │                               │
   ├── POST /api-keys ─────────────┤  create key (zero balance)
   ├── send USDC → treasury        │
   ├── POST /deposit (tx_sig) ─────┤  server verifies & credits
   │                               │
   │                     ┌─────────▼────────┐
   │                     │ POST /mcp         │
   │                     │ Authorization:    │
   │                     │  Bearer mnm_xxx   │
   │                     └─────────┬────────┘
   │                               │
   │                   check balance ≥ cost
   │                   execute tool
   │                   deduct balance
```

**API key format:** `mnm_` + 48 hex chars (96 bits of randomness, counter-seeded PRNG).

### Path B — x402 per-call payment (autonomous agents)

Agents with on-chain wallets pay per attestation via a Solana USDC transfer.

```
Agent
  │
  ├── POST /mcp (mnemonic_sign_memory, no X-Payment)
  │       ← HTTP 402 + x402 JSON (amount, treasury, USDC mint)
  │
  ├── [agent sends USDC to treasury on Solana]
  │
  ├── POST /mcp (same request + X-Payment: {"tx_sig":"...", "network":"solana-mainnet"})
  │       server verifies SPL token balance delta
  │       server marks tx_sig as used (x402_nonces table, unique constraint)
  │       execute tool
  │       ← JSON-RPC success response
```

**Replay prevention:** `x402_nonces` table stores used tx sigs. Second use returns `x402 payment already used`.

**USDC transfer verification:** `getTransaction` with jsonParsed encoding. Compares `postTokenBalances` vs `preTokenBalances` for the treasury account with the USDC mint.

---

## 10. Dynamic Pricing

Server costs (Irys upload + Solana tx fee) are denominated in SOL. Revenue is in USDC. The pricing engine reconciles these.

### Formula

```
total_lamports = irys_lamports + sol_tx_fee_lamports
cost_micro_usdc = total_lamports × sol_price_usdc / 1_000
quoted_price = ceil(cost_micro_usdc × (1 + margin_bps / 10_000))
quoted_price = max(quoted_price, MIN_SIGN_MEMORY_COST_MICRO_USDC)
```

### Background refresh loop

Starts at server startup, repeats every `PRICE_REFRESH_SECS` (default 1800s = 30 min):

1. `GET https://uploader.irys.xyz/price/solana/<TYPICAL_PAYLOAD_BYTES>` → lamports
2. `GET https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd` → USD/SOL
3. Recompute and atomically store new price

Price is stored in `AtomicI64`/`AtomicU64` — reads are always wait-free, no lock contention on hot path.

### Initial startup

On first boot, the engine attempts a price fetch before accepting connections. If the fetch fails (no network, API down), the server falls back to `SIGN_MEMORY_COST_MICRO_USDC` as a floor price and logs a warning.

---

## 11. P&L Tracking

Every completed `mnemonic_sign_memory` call appends a row to `attestation_costs`:

| Column | Description |
|--------|-------------|
| `attestation_id` | FK to attestations |
| `irys_cost_lamports` | Irys quote at time of call |
| `sol_tx_fee_lamports` | Memo tx fee estimate |
| `sol_price_usdc` | SOL/USDC rate at time of call |
| `earned_micro_usdc` | Amount charged to caller |
| `created_at` | Timestamp |

`GET /admin/stats?days=N` aggregates this table to show earned, cost (converted to micro-USDC), net margin, and current pricing state.

---

## 12. Database Schema

SQLite at `DATABASE_PATH` (default `~/.mnemonic/attestations.db`).

```sql
attestations (
    attestation_id TEXT PK,
    content TEXT,
    content_hash TEXT,
    tags TEXT,              -- JSON array
    solana_tx TEXT,
    arweave_tx TEXT,
    signer_pubkey TEXT,
    created_at TEXT
);

attestation_embeddings (
    attestation_id TEXT PK → attestations,
    embedding_dim INTEGER,
    embedding BLOB          -- f32 little-endian packed
);

api_keys (
    api_key TEXT PK,
    owner_pubkey TEXT,
    balance_micro_usdc INTEGER,
    created_at TEXT,
    last_used_at TEXT
);

payment_events (
    event_id TEXT PK,
    api_key TEXT,
    amount_micro_usdc INTEGER,
    event_type TEXT,        -- 'deposit' | 'charge' | 'refund'
    tx_sig TEXT,
    description TEXT,
    created_at TEXT
);

x402_nonces (
    tx_sig TEXT PK,         -- UNIQUE, prevents replay
    used_at TEXT
);

attestation_costs (
    attestation_id TEXT PK → attestations,
    irys_cost_lamports INTEGER,
    sol_tx_fee_lamports INTEGER,
    sol_price_usdc REAL,
    earned_micro_usdc INTEGER,
    created_at TEXT
);
```

---

## 13. Configuration Reference

All configuration via environment variables (`.env` supported via `dotenvy`).

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `http` | `http` or `stdio` |
| `MCP_HTTP_HOST` | `0.0.0.0` | Listen address |
| `MCP_HTTP_PORT` | `3000` | Listen port |
| `SOLANA_RPC_URL` | `http://localhost:8899` | Solana RPC endpoint |
| `ARWEAVE_URL` | `http://localhost:1984` | Arweave gateway (localhost = arlocal) |
| `MNEMONIC_KEYPAIR_PATH` | `~/.mnemonic/id.json` | Ed25519 keypair (auto-generated) |
| `DATABASE_PATH` | `~/.mnemonic/attestations.db` | SQLite file |
| `EMBED_PROVIDER` | `hash` | `hash` or `openai` |
| `OPENAI_API_KEY` | _(empty)_ | Required when `EMBED_PROVIDER=openai` |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | OpenAI embed model |
| `TURBO_BITS` | `4` | TurboQuant quantisation bits (2/3/4) |
| `PAYMENT_MODE` | `none` | `none` / `balance` / `x402` / `both` |
| `TREASURY_PUBKEY` | _(empty)_ | Solana pubkey receiving USDC payments |
| `USDC_MINT` | `EPjFWdd5...` | USDC SPL mint (mainnet default) |
| `SIGN_MEMORY_COST_MICRO_USDC` | `1000` | Floor price (1000 μUSDC = $0.001) |
| `PRICE_REFRESH_SECS` | `1800` | Pricing refresh interval (seconds) |
| `PRICING_MARGIN_BPS` | `2000` | Margin above break-even (2000 = 20%) |
| `TYPICAL_PAYLOAD_BYTES` | `2048` | Byte count used for Irys price quotes |
| `SOL_TX_FEE_LAMPORTS` | `5000` | Memo tx fee estimate (lamports) |

---

## 14. Source Map

```
mcp-server-rs/src/
├── main.rs        — CLI, server startup, HTTP router, background pricing task
├── mcp.rs         — JSON-RPC dispatcher, McpState, tool routing
├── tools.rs       — 5 tool implementations (whoami, sign_memory, verify, prove_identity, recall)
├── db.rs          — SQLite store (attestations, payment, P&L tables)
├── identity.rs    — keypair load/create, did:sol, did:key, sign_bytes
├── embed.rs       — Embedder trait, HashEmbedder, OpenAIEmbedder, build_embedder()
├── compress.rs    — TurboQuant wrapper (EmbeddingCompressor)
├── arweave.rs     — ArweaveClient: arlocal stub + Irys ANS-104 production upload
├── solana.rs      — SolanaClient: SPL Memo write/read, USDC transfer verification
├── payment.rs     — PaymentGate enum, check_payment(), x402 wire types, balance path
├── pricing.rs     — PricingEngine (atomic), Irys/CoinGecko fetchers, compute_price()
└── config.rs      — Config struct, from_env()
```

---

## 15. Security Notes

- **x402 replay prevention:** `x402_nonces` uses a `UNIQUE` primary key. A race condition where two requests present the same tx_sig simultaneously is resolved by SQLite's serialised write lock — only one succeeds.
- **Balance deduction:** deducted _after_ successful tool execution. A failed Arweave or Solana call does not charge the caller.
- **Keypair storage:** stored at `MNEMONIC_KEYPAIR_PATH` as a JSON array of bytes. Restrict file permissions (`chmod 600`). The key signs both Arweave bundle items and Solana transactions.
- **Admin endpoint:** `GET /admin/stats` is currently unauthenticated. For production, place behind a reverse proxy with IP allowlist or add an `ADMIN_SECRET` header check.
- **USDC mint verification:** the deposit and x402 paths verify both the _recipient_ (treasury pubkey) and the _mint_ (USDC). A transfer of a different SPL token to the treasury is rejected.
