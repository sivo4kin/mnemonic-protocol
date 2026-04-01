<!--
Sync Impact Report
===================
Version change: 0.0.0 → 1.0.0 (initial ratification)
Modified principles: N/A (first version)
Added sections:
  - Core Principles (7 principles)
  - On-Chain Constraints
  - Development Workflow
  - Governance
Removed sections: N/A
Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ no update needed (Constitution Check section is generic, will be filled per-feature)
  - .specify/templates/spec-template.md — ✅ no update needed (requirements and success criteria sections are generic)
  - .specify/templates/tasks-template.md — ✅ no update needed (phase structure accommodates principle-driven tasks)
  - .specify/templates/commands/*.md — ✅ no command templates exist
Follow-up TODOs: none
-->

# Mnemonic Constitution

## Core Principles

### I. Verifiability First

Every memory state MUST be independently verifiable by any party
holding the decryption key. This means:

- All memory snapshots MUST be committed on-chain with a
  content-addressable hash
- The hash chain MUST be append-only; rollback attempts MUST be
  detectable via commitment chain references
- Round-trip determinism is non-negotiable: serialize → hash →
  rehydrate MUST produce identical retrieval results
- No silent data loss — quantization, compression, and persistence
  layers MUST preserve lossless round-trip fidelity

### II. Non-Censored Storage

Memory MUST live on decentralized, permissionless storage. No single
platform, provider, or operator can revoke, alter, or deny access to
committed memory. Specifically:

- Primary storage layer MUST be Arweave (or equivalent permanent,
  permissionless store)
- On-chain commitment MUST use Solana memo (or equivalent public
  ledger) for hash anchoring
- Encrypted blobs are public by default (V1); only the keypair
  holder can decrypt
- The system MUST NOT depend on any centralized service for
  retrieving committed memory

### III. Provider Independence

Agents MUST be able to switch embedding providers, models, or
infrastructure without losing accumulated memory. This means:

- Memory snapshots MUST be self-contained: embeddings, quantizer
  state, and metadata travel together
- The retrieval layer MUST NOT assume a specific embedding model
  at query time
- Quantizer calibration state MUST be serialized alongside packed
  codes — never stored separately from the index it calibrates
- Model migration (re-embedding with a new provider) MUST be a
  supported operation, not a data loss event

### IV. Compression-Aware Retrieval

The retrieval architecture MUST use a 2-stage cascade: compressed
candidate generation followed by exact reranking. This is the
fundamental design contract:

- Stage 1: quantized shadow index for fast, broad candidate
  generation (cheap, lossy)
- Stage 2: full-precision embeddings for exact reranking on the
  shortlist (expensive, lossless)
- Full-precision embeddings are the source of truth; compressed
  embeddings are acceleration, never authority
- Quantization parameters (bit width, calibration) are tuning
  knobs, not architectural commitments — the cascade contract
  MUST hold regardless of compression settings

### V. Test-Driven Validation

No retrieval gate, compression strategy, or architectural claim
ships without empirical evidence. Specifically:

- Every retrieval quality claim MUST be backed by a benchmark run
  with documented corpus, parameters, and metrics
- Recall@k, round-trip determinism, and compression ratio MUST be
  measured before any gate is declared passed
- Multi-domain corpus tests MUST verify cross-domain
  generalization — single-domain benchmarks are necessary but
  not sufficient
- Adversarial scenarios MUST be researched and documented before
  countermeasures are implemented

### VI. Shared Memory Between Agents

Multiple agents MUST be able to read from and contribute to the
same committed memory store. This is the core product thesis:

- Memory layout MUST support multi-writer scenarios
- Per-entry signing MUST identify the writing agent
- Conflict resolution strategy MUST be defined before multi-writer
  is enabled (append-only with commitment chain is the V1 default)
- The protocol MUST NOT assume single-agent ownership of a memory
  store

### VII. Earn the Complexity

Start with the simplest implementation that validates the
architecture. Add complexity only when empirical results demand it:

- No random rotation, residual QJL, or learned codebooks until
  scalar quantization is proven insufficient
- No production infrastructure (gRPC, horizontal scaling) until
  the SDK is validated
- No consumer-facing UI until V1 infrastructure is complete
- Every added layer of complexity MUST cite the benchmark or user
  need that justifies it

## On-Chain Constraints

### Storage Economics

On-chain operations are cost-constrained. All design decisions
MUST account for real storage costs:

- Arweave cost scales linearly with blob size — compression
  directly reduces per-snapshot cost
- Solana memo cost is fixed per transaction — batch commits where
  possible
- Target: sub-$0.50/snapshot for corpora up to 10K memories at
  8-bit compression (validated: $0.39 at 10K)
- Cost regressions MUST be caught by benchmark — any change that
  increases per-snapshot cost by >20% requires explicit
  justification

### Security Model

The threat model assumes a malicious collaborator with legitimate
write access:

- Ranking manipulation (crafted embeddings) — mitigate with
  outlier rejection at ingest
- Quantization poisoning (skewed calibration) — mitigate by
  locking calibration after initial fit
- Stale replay (old snapshot re-commit) — mitigate with
  commitment chain referencing prior hash
- Payload injection (malicious content) — mitigate with per-entry
  signing and provenance tracking
- All mitigations MUST be researched and documented (ADR) before
  implementation

## Development Workflow

### Architecture Decision Records

Every non-trivial technical decision MUST be documented in an ADR
before implementation begins:

- ADRs MUST state the decision, alternatives considered, and
  rationale
- Experimental results that inform the decision MUST be linked
- ADRs are append-only; superseded decisions get a "Superseded by
  ADR-XXX" note, not deletion

### Gate-Based Progression

Features and capabilities progress through gates:

- Research gate: problem understood, experiments designed
- Validation gate: experiments run, metrics meet targets
- Implementation gate: ADR written, design reviewed
- Ship gate: tests pass, benchmarks stable, documentation updated

No gate may be skipped. A gate that cannot be passed blocks
downstream work until resolved.

### V1 / V2 Scope Discipline

- V1 = SDK and infrastructure only. No consumer UI, no
  production serving layer
- V2 = SDK + Personal Research Assistant application
- Features MUST be tagged with their version scope; scope creep
  across version boundaries requires explicit re-scoping

## Governance

This constitution is the highest-authority document for the
Mnemonic project. All architectural decisions, feature
specifications, and implementation plans MUST be consistent with
these principles.

### Amendment Procedure

1. Propose amendment via ADR or dedicated discussion
2. Document the principle change, rationale, and migration impact
3. Update constitution version per semantic versioning:
   - MAJOR: principle removal or backward-incompatible redefinition
   - MINOR: new principle or material expansion of existing guidance
   - PATCH: clarification, wording, or non-semantic refinement
4. Update all dependent artifacts (specs, plans, tasks) to reflect
   the amended principles

### Compliance

- All PRs and reviews MUST verify consistency with this
  constitution
- Violations MUST be flagged before merge, not after
- Complexity MUST be justified against Principle VII (Earn the
  Complexity)

**Version**: 1.0.0 | **Ratified**: 2026-04-01 | **Last Amended**: 2026-04-01
