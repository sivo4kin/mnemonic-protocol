# V1 Live Demo Specification

**Date:** 2026-04-01
**Status:** Draft
**Blocks:** V1 SDK release — demo is a required V1 deliverable

---

## The one thing the demo must prove

> Your agent's memory is **yours** — it survives provider switches, lives on
> permanent storage, and anyone can verify it wasn't tampered with. No other
> memory system does this.

If someone walks away remembering one thing, it's that.

---

## Demo narrative (the "wow" chain)

The demo tells a story in 5 acts. Each act builds on the previous one.
The visitor *does* things — this is not a slideshow.

### Act 1 — Load & Search

A pre-loaded corpus of ~1000 research memories (investigative journalism
theme: sources, documents, connections, timelines). The visitor types a
natural-language query. Results appear instantly from the compressed index
+ exact rerank cascade.

**What the visitor sees:**
- Query input box
- Retrieved memories ranked by relevance (top 5–10)
- Per-result: relevance score, memory type, timestamp
- Sidebar: corpus stats (1000 memories, 768-dim nomic embeddings, 8-bit
  compressed, 25% of full size)

**What this proves:** The retrieval engine works. Compressed search +
exact rerank returns high-quality results.

### Act 2 — Compression Comparison

A toggle or split view: "Exact search" vs "Compressed + Rerank" for the
same query. Side-by-side results showing they're nearly identical.

**What the visitor sees:**
- Two columns: exact brute-force results vs compressed cascade results
- Overlap indicator: "9/10 results identical" or "10/10 match"
- Compression stats: "Using 25% of the memory. Same answers."

**What this proves:** You don't lose quality by compressing. The 2-stage
cascade works.

### Act 3 — Switch Provider

The "wow button." One click: the system snapshots all memories to raw
text (no embeddings), re-embeds with a *different* model, rebuilds the
compressed index. The visitor asks the same query again.

**What the visitor sees:**
- Button: "Switch embedding provider" (e.g., nomic → mock, or a visual
  label like "Provider A → Provider B")
- Progress indicator: snapshot → re-embed → rebuild index
- Same query, same results (or near-identical)
- Banner: "Your context survived a complete provider switch."

**What this proves:** Memory is not locked to any model or provider. Raw
text is the portable unit. This is the V2 product promise demonstrated.

### Act 4 — On-Chain Commitment

The visitor clicks "Commit to chain." The system encrypts the memory
blob, hashes it, and shows:
- The SHA3-256 hash
- The (simulated or real devnet) Solana transaction
- The Arweave transaction ID
- Total cost: "$0.04 for 1000 memories, permanent."

**What the visitor sees:**
- Step-by-step commitment animation (encrypt → hash → upload → anchor)
- Final commitment card: hash, Solana tx, Arweave tx, cost
- "This memory state is now permanent and tamper-evident."

**What this proves:** On-chain commitment is real, cheap, and fast.

### Act 5 — Verify

The visitor clicks "Verify." The system fetches the blob (from local
cache or Arweave), recomputes SHA3-256, and shows it matches the
on-chain commitment.

**What the visitor sees:**
- Hash comparison: computed vs on-chain (green checkmark if match)
- "Nobody — not even us — altered these memories since commitment."
- Optional: decrypt and show the first memory item as proof of content

**What this proves:** Tamper evidence works. Verifiability is not a
marketing claim — it's a cryptographic proof the visitor just witnessed.

---

## Demo corpus: Investigative Journalism Research Trail

**Why journalism:** "Proof of what you knew and when" is the unique
on-chain value that no other memory system offers. Academic priority,
source protection timelines, investigation documentation — these are
real use cases where verifiable memory matters.

**Corpus structure (~1000 items):**

| Domain | Items | Example |
|--------|-------|---------|
| Sources & contacts | ~200 | "Met with whistleblower J.D. on 2026-01-15. Claims internal audit was suppressed." |
| Documents & evidence | ~250 | "Obtained memo RE: Q3 compliance review. Key finding: 3 facilities failed inspection." |
| Timeline events | ~200 | "2025-11-03: Company announces restructuring. 2025-11-10: First layoffs begin." |
| Connections & analysis | ~200 | "Link between lobbying spend increase (Q2) and regulatory delay (Q3) is consistent with..." |
| Hypotheses & decisions | ~150 | "Working hypothesis: delayed inspections correlate with board meeting dates. Need to verify." |

The corpus should feel real enough that querying it produces meaningful,
contextually rich results. It should NOT contain real people or events —
use a fictional but plausible investigation scenario.

---

## Technical architecture

### Phase 1: Local-first (`python -m mnemonic serve`)

Fastest to build. No hosting, no deployment complexity. Proves the demo
works before investing in infrastructure.

```
┌─────────────────────────────────────────────┐
│           Browser (localhost:8080)            │
│                                              │
│  ┌────────────┐  ┌──────────┐  ┌─────────┐  │
│  │ Query box  │  │ Results  │  │ Sidebar │  │
│  │            │  │ panel    │  │ stats   │  │
│  └────────────┘  └──────────┘  └─────────┘  │
│  ┌────────────────────────────────────────┐  │
│  │ Action bar: Switch | Commit | Verify  │  │
│  └────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────┘
                       │ HTTP API
              ┌────────▼────────┐
              │  Python backend │
              │  (mnemonic +    │
              │   FastAPI/Flask)│
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
   ┌─────▼─────┐ ┌────▼────┐ ┌─────▼──────┐
   │  SQLite   │ │ Nomic   │ │  Solana    │
   │  (local)  │ │ (local) │ │  devnet    │
   └───────────┘ └─────────┘ └────────────┘
```

**Backend endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/search` | POST | Query → compressed + rerank → results |
| `/api/search/exact` | POST | Query → brute-force exact → results (for comparison) |
| `/api/stats` | GET | Corpus size, dimensions, compression ratio, quantizer info |
| `/api/switch-provider` | POST | Snapshot → re-embed → rebuild index |
| `/api/commit` | POST | Encrypt → hash → (simulated) Arweave + Solana commit |
| `/api/verify` | POST | Recompute hash → compare against commitment |

**Frontend:** Single-page app. Minimal — no framework needed for Phase 1.
Plain HTML + JS + CSS is acceptable. Upgrade to React/Svelte in Phase 2
if needed.

### Phase 2: Hosted (optional, post-V1)

Deploy backend on Fly.io or Railway. Frontend on Vercel or Cloudflare
Pages. Add real Solana devnet transactions and Arweave uploads.

### Phase 3: Solana dApp (V2 scope)

Connect wallet. Memories anchored to visitor's keypair. Real on-chain
verification. This becomes the V2 Personal Research Assistant entry
point.

---

## Implementation plan

### Step 1: CLI narrative script (1 day)

`python -m mnemonic showcase` — runs the full 5-act story in the
terminal. This crystallizes the narrative before building UI.

Output:

```
═══════════════════════════════════════════════════════════
  MNEMONIC — Verifiable Agent Memory
═══════════════════════════════════════════════════════════

  ACT 1: Loading 1000 research memories...
         Embedding with nomic-embed-text-v1.5 (768-dim)
         Compressed index: 768 KB (25% of full size)

  QUERY: "What evidence links the lobbying spend to the
          regulatory delay?"

  Top 5 results (compressed + rerank):
    1. [0.94] Connection analysis: lobbying spend increase...
    2. [0.91] Document: Q2 lobbying disclosure shows...
    ...

  ACT 2: Comparing compressed vs exact search...
         9/10 results identical. Compression works.

  ACT 3: Switching provider...
         Snapshot: 1000 items → raw text (no embeddings)
         Re-embedding with Provider B...
         Rebuilding compressed index...

         Same query, same top results. Context survived.

  ACT 4: Committing to chain...
         Encrypt: AES-256-GCM ✓
         Hash: SHA3-256 = a1b2c3...
         Arweave: [simulated] tx_abc123
         Solana: [simulated] tx_def456
         Cost: $0.04 for 1000 memories. Permanent.

  ACT 5: Verifying...
         Fetched blob. Recomputed hash.
         On-chain: a1b2c3...
         Computed: a1b2c3...
         ✓ MATCH — memories are tamper-evident.

═══════════════════════════════════════════════════════════
  Memory that is provably yours, survives across providers,
  and can be verified by anyone. That's Mnemonic.
═══════════════════════════════════════════════════════════
```

### Step 2: Generate demo corpus (0.5 day)

Create `data/demo_corpus.jsonl` — 1000 fictional journalism research
memories with the domain structure above. Use an LLM to generate
realistic content. Embed with nomic and cache.

### Step 3: Web backend (1 day)

`mnemonic/serve.py` — FastAPI app exposing the 6 endpoints above.
Loads corpus on startup, serves API. Add `serve` subcommand to CLI.

### Step 4: Web frontend (1-2 days)

Single HTML page with:
- Query input + results panel
- Compression comparison toggle
- Provider switch button
- Commit + verify buttons
- Stats sidebar

Served by the Python backend as static files. No build step.

### Step 5: Polish & test (0.5 day)

Error handling, loading states, mobile responsiveness, README
instructions for running the demo.

**Total estimate: 4-5 days.**

---

## Success criteria

| Criterion | Target |
|-----------|--------|
| Time to first query result | < 200ms (1000 memories, local) |
| Provider switch completes | < 30s (1000 items, nomic re-embed) |
| Visitor understands value prop | Within 60 seconds of landing |
| Demo runs with zero config | `pip install mnemonic && mnemonic serve` |
| Works without internet | Yes (mock commit mode, local embeddings) |
| Works with real chain | Yes (Solana devnet + Arweave, optional) |

---

## What this is NOT

- Not a production app — it's a demo
- Not the V2 Personal Research Assistant — it's the V1 SDK showcase
- Not multi-user — single local instance
- Not a database product — it's a protocol demonstration
- Not trying to replace vector DBs — it's showing what vector DBs can't
  do (verifiability, portability, permanence)

---

## Relationship to other docs

- **PROJECT_STATE.md** — live demo added as V1 SDK deliverable
- **WHITEPAPER.md** — Phase 4 roadmap updated to include demo
- **BLOCKERS.md** — demo listed as V1 gate
- **ADR-011** — demo serves as proof-of-concept for V2 Research Assistant
