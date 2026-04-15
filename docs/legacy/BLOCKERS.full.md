# BLOCKERS.md

> **Scope note:** This document is primarily about unresolved productization, security, and roadmap blockers in the broader Mnemonic vision. It should not be read as a precise description of what the current Rust MCP implementation in `mcp/` already does or does not do.
>
> Current implementation truth:
> - `mcp/README.md`
> - `docs/versions/v0.0.3/API.md`
> - `docs/versions/v0.0.3/SPEC.md`
> - `docs/IMPLEMENTATION_STATUS.md`
>
> In particular, this file may discuss encryption, snapshotting, pruning, and other roadmap concerns from the legacy/research architecture that are not identical to the active MCP code path.

## Executive Summary

This file tracks the major unresolved blockers for turning Mnemonic into a complete, coherent product and protocol — beyond the currently working MCP implementation.

The active Rust MCP server proves that a meaningful implementation exists today.
The blockers below describe the remaining gaps for the broader product / protocol thesis.

---

## Blocking Areas

### 1. Product Definition

Still open at the product level:
- first paying ICP
- packaging
- who buys the broader system and for what exact pain

**Status:** High

### 2. Customer and Market Fit

Still open:
- target buyer clarity
- hosted vs self-hosted expectations
- what outcome reliably triggers payment

**Status:** High

### 3. Security and Privacy Model

Important clarification:

- older prototype docs describe an encryption-centered privacy model
- the current active MCP implementation does **not** yet provide that same end-to-end encrypted snapshot model

So the blocker here is real: the broader privacy story is still not fully aligned across design docs and active implementation.

Open questions include:
- what privacy guarantees are true today?
- what privacy guarantees belong to future architecture only?
- what can be claimed honestly in product messaging?

**Status:** Critical

### 4. Encryption Architecture

This remains a blocker at the broader system level.

Reason:
- legacy/prototype docs describe encrypt-before-hash snapshots
- active MCP implementation currently does not implement that same path

So encryption is not a closed product capability at the current repo level.

**Status:** Critical

### 5. Key Management and Recovery

Still unresolved at product scale.

**Status:** Critical

### 6. Real Agent Integration

The broader product question remains open:
- how much does verifiable memory improve real agent usefulness in production contexts?
- what are the right write/retrieval policies in real deployments?

**Status:** Critical

### 7. Memory Write Semantics

Still not resolved at the broader product level.

**Status:** High

### 8. Memory Pruning, Eviction, and Lifecycle

Still a real blocker for a complete long-lived memory system.

**Status:** Critical

### 9. Concurrent Writers and Consistency Model

Still open at the broader protocol level.

Important distinction:
- the active MCP implementation is not the same as the legacy concurrent-writers prototype/research direction
- older docs discuss event-sourced/shared-memory futures that are not current MCP behavior

**Status:** Critical

### 10. Retrieval Validation with Real Embeddings

For the current active MCP implementation, this question is shaped differently than in the old prototype.

Why:
- old prototype work focused on compressed retrieval quality
- current MCP recall path uses full embeddings in SQLite, not the compressed candidate cascade

So historical retrieval validation remains useful research, but should not be over-read as validating the current MCP retrieval architecture.

**Status:** Partially resolved historically, but not directly transferable one-to-one to current MCP retrieval behavior

### 11. Scale Validation

Still open for the broader system and current implementation at larger scales.

**Status:** High

### 12. Latency and Production Performance

Still open for current MCP production-grade performance characterization.

**Status:** Critical

### 13. Robustness to Noisy or Adversarial Data

Still open.

**Status:** Medium-High

### 14. Storage Architecture and Economics

Still open as a product/system question.

Current implementation has explicit `local` and `full` modes, but the complete long-term economics and storage posture still need clearer product framing.

**Status:** High

### 15. End-User Experience (UX)

Still open.

**Status:** High

### 16. Developer Experience (DX)

Still open at the broader SDK/platform level.

**Status:** Medium-High

### 17. Compliance, Trust, and Data Governance

Still open.

**Status:** High

### 18. Pricing, Packaging, and Monetization

Still open.

**Status:** Medium-High

### 19. Go-to-Market and Positioning

Still open.

**Status:** High

---

## Key documentation reality check

To avoid future confusion, the most important blockers are not just technical — they are also documentary:

1. **Current implementation vs prototype lineage must stay clearly separated**
2. **Encryption/privacy claims must be scoped precisely**
3. **Compressed retrieval claims must not be mistaken for current MCP recall behavior**
4. **Current implementation docs and product-roadmap docs must not be treated as interchangeable**

---

## Recommended working rule

When evaluating blockers:

- use `mcp/` + versioned MCP docs for current implementation questions
- use whitepaper / architecture / ADR / research docs for broader roadmap and prototype questions

If those are mixed, conclusions become unreliable.

---

## Bottom line

The biggest blocker is not that nothing works.
The biggest blocker is that:

- some things work in current MCP now
- some things were proven in an older prototype/research track
- some things are still roadmap only

The repo must keep those categories explicit.
