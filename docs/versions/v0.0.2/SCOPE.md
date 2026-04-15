# V1_1_SCOPE.md

## Purpose

This document records the features intentionally deferred out of V1 so they do not get lost.

## V1.1 goal

V1.1 should extend the minimal V1 memory product into a more protocol-like and tool-usable system.

## Deferred from V1 into V1.1

### 1. MCP server
- expose workspace/memory operations to agents and AI tools
- make Mnemonic usable through MCP-compatible clients

### 2. File/blob storage
- file uploads
- attachment handling
- durable blob/object storage layer

### 3. Checkpoints
- create checkpoint
- list checkpoints
- inspect checkpoint metadata
- restore prior state

### 4. Verification
- public verify page
- checkpoint verification UX
- trust-oriented surface beyond internal app state

### 5. Solana anchoring
- on-chain commitment flow
- anchored verification story
- protocol-facing trust layer

## Design rule

V1.1 should build on the same core workspace/memory model proven in V1.

Nothing deferred here should require a second memory system or a second product core.

## Bottom line

V1 proves the usable memory product.

V1.1 proves the broader protocol-like trust and integration surface.
