# MCP Server Backend Features Comparison

**Project:** `mnemonic-protocol`  
**Compared backends:** `mcp-server` (Python) vs `mcp-server-rs` (Rust)  
**Date:** 2026-04-14  
**Branch analyzed:** `feat/auth`

## Executive summary

The Rust backend is not just a port of the Python MCP server. It is materially more complete as a production backend.

At a high level:

- **Python (`mcp-server`)** is a solid MVP / local-first implementation.
- **Rust (`mcp-server-rs`)** is the production-oriented backend with:
  - HTTP transport
  - payment gating
  - API key and deposit flows
  - x402 support
  - dynamic pricing
  - TurboQuant compression
  - richer Arweave payloads
  - P&L accounting
  - stronger docs/spec alignment

If the question is **which backend exposes the fuller backend feature set**, the answer is clearly **`mcp-server-rs`**.

---

## Scope of comparison

This report compares backend capabilities across:

- transports and deployment model
- MCP tool surface
- embeddings and retrieval
- Arweave write path
- Solana anchoring and verification
- payment and monetization features
- storage schema
- observability/admin endpoints
- security and production readiness
- spec/documentation alignment

Files reviewed include:

- `mcp-server/mnemonic_mcp/server.py`
- `mcp-server/mnemonic_mcp/tools.py`
- `mcp-server/mnemonic_mcp/embed.py`
- `mcp-server/mnemonic_mcp/arweave_client.py`
- `mcp-server/mnemonic_mcp/solana_client.py`
- `mcp-server/mnemonic_mcp/db.py`
- `mcp-server-rs/src/main.rs`
- `mcp-server-rs/src/tools.rs`
- `mcp-server-rs/src/payment.rs`
- `mcp-server-rs/src/db.rs`
- `mcp-server-rs/src/embed.rs`
- `mcp-server-rs/src/arweave.rs`
- `docs/mcp_server_rs/SPEC.md`
- `docs/mcp_server_rs/API.md`

---

## High-level verdict

### Python backend strengths

The Python backend is good at:

- simple stdio MCP integration
- fast local iteration
- a minimal 5-tool memory-attestation flow
- local embeddings via `fastembed` with deterministic hash fallback
- a straightforward SQLite semantic recall path

It is better thought of as:

- a **reference implementation**, or
- an **MVP/local agent backend**

than a complete remote production backend.

### Rust backend strengths

The Rust backend adds the missing backend features required for a hosted or monetized service:

- remote HTTP MCP serving
- stdio + HTTP dual transport
- balance-based access control
- x402 payment flow
- dynamic pricing engine
- admin/API key endpoints
- per-attestation cost accounting
- TurboQuant compressed embedding persistence
- signed ANS-104 / Irys bundle-item upload path

It is the first backend here that looks like an actual **service backend**, not just an MCP adapter.

---

## Feature matrix

| Capability | Python `mcp-server` | Rust `mcp-server-rs` | Notes |
|---|---|---|---|
| MCP stdio transport | Yes | Yes | Both support local MCP usage |
| MCP HTTP transport | No | Yes | Rust exposes `POST /mcp` |
| Management REST API | No | Yes | API keys, balance, deposit, stats, health |
| 5 MCP tools | Yes | Yes | Same conceptual tool surface |
| Local semantic recall | Yes | Yes | Both use SQLite + stored embeddings |
| Configurable embed provider | Partial | Yes | Python: fastembed/hash fallback; Rust: hash/OpenAI |
| Offline embedding mode | Yes | Yes | Both support deterministic hash embeddings |
| OpenAI embeddings | No | Yes | Rust supports `text-embedding-3-small` path |
| TurboQuant compression | No | Yes | Major backend differentiation |
| Compressed embedding stored in Arweave payload | No | Yes | Rust includes compressed vector metadata |
| Production Arweave/Irys signed ANS-104 upload | No | Yes | Python uploads raw body to Irys, Rust builds signed data item |
| Arlocal support | Yes | Yes | Both support local/dev mode |
| Solana memo anchoring | Yes | Yes | Both write/read SPL Memo |
| Verify hash from anchor + Arweave | Yes | Yes | Both implement verification flow |
| Payment gating | No | Yes | Rust gates `mnemonic_sign_memory` |
| Pre-funded API keys | No | Yes | Rust only |
| Deposit verification flow | No | Yes | Rust only |
| x402 support | No | Yes | Rust only |
| Replay protection for payments | No | Yes | `x402_nonces` in Rust |
| Dynamic pricing | No | Yes | Rust pricing engine with background refresh |
| Cost / P&L tracking | No | Yes | Rust `attestation_costs` + admin stats |
| Health endpoint | No | Yes | Rust `/health` |
| Admin stats endpoint | No | Yes | Rust `/admin/stats` |
| Branch docs/spec alignment | Partial | Strong | Rust has dedicated spec/API docs |

---

## Detailed comparison

## 1. Transport and deployment model

### Python

Python is **stdio-only**.

From `mcp-server/mnemonic_mcp/server.py`:

- uses `mcp.server.stdio.stdio_server`
- exposes only MCP tool calls over stdin/stdout
- no HTTP listener
- no separate control plane

This is good for:

- Claude Code local integration
- desktop/local agent usage
- prototyping

But it limits:

- remote hosting
- multi-client access
- payment enforcement at the network boundary
- admin/API management

### Rust

Rust supports **both stdio and HTTP**.

From `mcp-server-rs/src/main.rs`:

- `--transport stdio`
- `--transport http`
- HTTP routes include:
  - `/mcp`
  - `/api-keys`
  - `/balance`
  - `/deposit`
  - `/admin/stats`
  - `/health`

This is a major backend capability gap. HTTP support turns the MCP server into an actual remotely consumable service.

**Winner:** Rust

---

## 2. MCP tool surface

Both backends implement the same five conceptual tools:

- `mnemonic_whoami`
- `mnemonic_sign_memory`
- `mnemonic_verify`
- `mnemonic_prove_identity`
- `mnemonic_recall`

This is the area of strongest parity.

### Important nuance

The tool names match, but the **backend behavior is richer in Rust**, especially for `mnemonic_sign_memory`:

- Python: embed → hash → Arweave → Solana → SQLite
- Rust: embed → TurboQuant compress → hash → signed Arweave/Irys data item → Solana → SQLite + cost accounting

So the tool surface is similar, but backend semantics are not equivalent.

**Winner:** Tie on surface, Rust on depth

---

## 3. Embeddings and recall

### Python

Python embedding layer (`embed.py`) supports:

- `fastembed` local model when available
- deterministic hash fallback otherwise
- automatic dimension detection for the local model

That is actually nice for local development because it avoids external API dependence.

### Rust

Rust embedding layer (`embed.rs`) supports:

- deterministic hash embedder (384 dim)
- OpenAI embeddings API
- provider metadata returned to callers

### Tradeoff

- Python is stronger for **local/offline semantic quality** when `fastembed` works.
- Rust is stronger for **backend productization**, because provider selection is explicit and documented.

### Retrieval

Both backends:

- store full embeddings in SQLite
- compute cosine similarity locally
- return ranked results

Rust additionally returns embed provider metadata in recall results.

**Verdict:** slight edge to Rust overall for backend design, but Python has a genuinely useful local-embedding story.

---

## 4. Compression and storage efficiency

This is one of the clearest deltas.

### Python

Python does **not** implement TurboQuant compression.

Its Arweave payload contains only:

- content
- content hash
- tags
- signer
- timestamp

Its SQLite DB stores only the full float embedding blob.

### Rust

Rust adds a dedicated compression layer:

- `compress.rs`
- `EmbeddingCompressor`
- configurable `TURBO_BITS`
- compressed embedding bytes included in Arweave payload
- compression metadata returned from `mnemonic_sign_memory`

Rust payload includes:

- `embedding_compressed`
- `embed_provider`
- `embed_dim`
- `turbo_bits`

This matters because the whole protocol story is stronger when the permanent artifact contains enough information for future reconstruction or portability.

**Winner:** Rust by a wide margin

---

## 5. Arweave / Irys write path

### Python

Python's Arweave client is functional but thinner.

Observations from `arweave_client.py`:

- arlocal path creates a minimal unsigned tx stub
- production path posts raw bytes to `https://uploader.irys.xyz/upload`
- it does **not** appear to construct a signed ANS-104 data item
- custom tags are prepared but not clearly sent in the Irys upload request

So for production it behaves more like a simple upload adapter.

### Rust

Rust's Arweave path is much more complete.

Observations from `mcp-server-rs/src/arweave.rs`:

- explicitly constructs an ANS-104 bundle item
- uses Solana signer type 3
- deep-hash implementation included
- Avro tag encoding included
- signs the payload with the server's Ed25519 keypair
- uploads the signed item to Irys

That is substantially closer to a cryptographically coherent backend.

**Winner:** Rust

---

## 6. Solana anchoring and verification

### Shared behavior

Both backends:

- write SPL Memo transactions
- read transactions back for verification
- parse memo payloads
- compare expected hash with recomputed hash from Arweave content

### Differences

Rust verification output includes an explicit `has_compressed_embedding` indicator when present.

Python verification is simpler and includes timestamp/signer/content preview, but not the richer payload semantics.

### Assessment

Functionally, both are pretty close here.

**Winner:** near tie, slight Rust edge for richer verification context

---

## 7. Payments and monetization features

This is the single biggest backend-feature gap.

### Python

Python has **no payment layer**.

Missing features include:

- no auth gate on paid tools
- no API keys
n- no balance tracking
- no deposit verification
- no x402 flow
- no replay protection
- no pricing logic
- no revenue/cost accounting

For a hosted backend, that means Python currently cannot serve as the monetized service implementation without substantial additional work.

### Rust

Rust includes a full payment subsystem:

- `PAYMENT_MODE` = `none | balance | x402 | both`
- `Authorization: Bearer mnm_...` flow
- `X-Payment` x402 flow
- USDC transfer verification
- nonce replay protection via `x402_nonces`
- deposit crediting
- API key balance deduction

This is not just feature-complete relative to Python; it is an entirely different maturity tier.

**Winner:** Rust, decisively

---

## 8. Pricing engine

### Python

No pricing engine.

### Rust

Rust has explicit dynamic pricing:

- fetches Irys upload cost
- fetches SOL/USD price
- computes price in micro-USDC
- applies configurable margin and floor
- refreshes in the background
- exposes current pricing in admin stats

That is exactly the kind of backend logic expected in a production service.

**Winner:** Rust

---

## 9. Database schema and operational data

### Python schema

Python stores:

- `attestations`
- `attestation_embeddings`
- indexes for signer and content hash

This is enough for MVP storage and recall.

### Rust schema

Rust stores all of the above plus:

- `api_keys`
- `payment_events`
- `x402_nonces`
- `attestation_costs`

This makes the Rust backend operationally aware, not just functionally aware.

It can answer:

- who is authorized
- how much balance remains
- whether a payment was replayed
- how much each attestation cost
- what margin the service is actually making

**Winner:** Rust

---

## 10. Admin and observability features

### Python

No admin HTTP surface.

### Rust

Rust includes:

- `/health`
- `/admin/stats`
- `/balance`
- `/api-keys`
- `/deposit`

This is basic but important backend infrastructure.

A service backend without health/admin APIs is workable for a prototype, but painful in production.

**Winner:** Rust

---

## 11. Security and correctness notes

### Python

Python is simpler, which reduces some complexity risk, but it also lacks important protections because the relevant features do not exist yet.

Examples:

- no auth or payment boundary
- no replay prevention layer
- production Irys upload path appears weaker from a signing/provenance perspective

### Rust

Rust adds meaningful protections, including:

- payment replay prevention
- explicit payment modes
- stronger signing story for production Arweave uploads
- cost-aware and access-controlled HTTP boundary

### Caveat on Rust

There are still a few implementation concerns worth cleaning up:

1. In `main.rs`, balance deduction is commented as happening **before** execution, with refund on failure.
2. The code currently uses `state.sign_memory_cost_micro_usdc` when deducting balance, while payment gating uses `current_cost` from the pricing engine.
3. That mismatch suggests a potential pricing/charge inconsistency if dynamic price diverges from the floor/base config.
4. Deposit owner verification is marked `TODO`, so ownership binding is not fully enforced yet.

So Rust is clearly ahead, but it is not finished.

**Winner:** Rust overall, with some implementation debt noted

---

## 12. Spec and documentation alignment

### Python

Python README documents the 5 tools and local architecture, but the implementation is lighter than the broader protocol vision.

### Rust

Rust has dedicated docs:

- `docs/mcp_server_rs/SPEC.md`
- `docs/mcp_server_rs/API.md`

And the implementation maps much more closely to those docs:

- HTTP transport
- payment modes
- pricing
- admin endpoints
- compressed embedding persistence

This matters because a backend is easier to evolve when code and docs are marching in the same direction.

**Winner:** Rust

---

## Backend-by-backend assessment

## Python `mcp-server`: what it is good for

Use Python when you want:

- fastest prototyping
- local MCP integration over stdio
- a simple reference implementation
- easy iteration on tool semantics
- local embedding quality through `fastembed`

It is currently best positioned as:

- reference backend
- MVP backend
- developer/local backend
- test harness for tool semantics

## Python `mcp-server`: what it lacks

It currently lacks most of the features required for a hosted backend product:

- HTTP serving
- admin plane
- payments
- dynamic pricing
- cost accounting
- compressed permanent embeddings
- stronger production Arweave signing flow

## Rust `mcp-server-rs`: what it is good for

Use Rust when you want:

- hosted MCP backend
- service monetization
- remote clients
- production-ish deployment story
- backend observability and pricing
- durable protocol artifacts with compressed vectors

It is currently the real backend foundation for the product direction.

## Rust `mcp-server-rs`: where it still needs work

Recommended next fixes:

1. **Resolve dynamic pricing deduction mismatch**
   - ensure charge, quote, refund, and recorded revenue all use the same effective price

2. **Finish deposit signer ownership verification**
   - enforce that the API key owner actually signed or funded the deposit tx

3. **Lock down admin endpoints**
   - `/admin/stats` and related management routes should be authenticated in production

4. **Add parity tests between Python and Rust tool outputs**
   - especially for `whoami`, `verify`, and `recall`

5. **Document backend positioning explicitly**
   - state that Python is MVP/reference and Rust is production backend

---

## Recommendation

### Short recommendation

For any doc or architecture statement about the **backend feature-complete MCP server**, point to **`mcp-server-rs`**.

### Suggested wording

> The Rust MCP server (`mcp-server-rs`) is the primary backend implementation for production features. It extends the Python MVP with HTTP transport, payments, pricing, TurboQuant compression, richer Arweave payloads, and operational/admin APIs.

### Practical repo positioning

A clean framing would be:

- `mcp-server/` → Python reference/MVP/local stdio server
- `mcp-server-rs/` → Rust production/backend server

That framing matches the code reality much better than implying both are equally capable backends.

---

## Final conclusion

The backend feature comparison is not close.

- **Python** proves the protocol and the 5-tool MCP interaction model.
- **Rust** implements the actual backend platform features.

If this report is intended to guide docs, product messaging, or implementation focus, the right conclusion is:

> `mcp-server-rs` is the authoritative backend for backend/service features, while `mcp-server` remains the simpler reference/MVP implementation.

That is the clearest and most honest characterization of the current repository state.
