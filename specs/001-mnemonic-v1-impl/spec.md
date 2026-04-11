# Feature Specification: Mnemonic Protocol V1 Implementation

**Feature Branch**: `001-mnemonic-v1-impl`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "We are going to implement mnemonic protocol v1 Lets check do we have enough info to start work and prepare all for implementation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Builder Searches Compressed Memory (Priority: P1)

An agent developer integrates the Mnemonic SDK into their agent pipeline. They ingest memory items, generate embeddings with the canonical open embedder (nomic-embed-text-v1.5), build a compressed shadow index, and retrieve memories using the 2-stage cascade (compressed candidate generation followed by exact rerank). The developer gets high-quality retrieval results at 25% of the full index memory footprint.

**Why this priority**: This is the core value proposition. Without working compressed retrieval via SDK, nothing else in V1 matters.

**Independent Test**: Can be fully tested by ingesting 1000 memory items, running queries, and verifying recall@10 >= 0.94 with 8-bit compression. Delivers the fundamental compressed retrieval capability.

**Acceptance Scenarios**:

1. **Given** a corpus of 1000 memory items, **When** an agent ingests all items via the SDK and queries "what evidence links lobbying to regulatory delay", **Then** the 2-stage cascade returns top-10 results with final recall@10 >= 0.94 compared to exact brute-force search.
2. **Given** an 8-bit compressed index on 1000 items, **When** the agent checks compression stats, **Then** the compressed index uses <= 30% of the full float32 index size.
3. **Given** a running memory store with ingested items, **When** the agent queries with k=10 and n_candidates=50, **Then** results are returned in under 200ms (local, 1000 memories).

---

### User Story 2 - Agent Builder Persists and Restores Memory (Priority: P1)

An agent developer saves the current memory state to SQLite, shuts down, and later restores it. The restored index produces identical retrieval results to the original.

**Why this priority**: Persistence is essential for any real-world usage. Without it, memory is session-scoped and not useful for production agents.

**Independent Test**: Can be tested by ingesting items, saving to SQLite, loading back, and comparing recall retention (must be 1.000).

**Acceptance Scenarios**:

1. **Given** a memory store with 1000 ingested items and a built quantized index, **When** the developer calls save_to_sqlite followed by load_from_sqlite, **Then** recall retention is exactly 1.000 (identical retrieval results).
2. **Given** a saved SQLite file, **When** it is loaded into a fresh memory store instance, **Then** all memory items, embeddings, quantizer state, and packed codes are restored without data loss.

---

### User Story 3 - Agent Builder Switches Embedding Provider (Priority: P2)

An agent developer migrates their agent from one embedding provider to another (e.g., nomic to OpenAI, or vice versa). They snapshot the memory to raw text, re-embed with the new provider, rebuild the compressed index, and verify that retrieval quality is preserved.

**Why this priority**: Provider independence is a key differentiator. It proves memory is not locked to any single model or vendor.

**Independent Test**: Can be tested by ingesting with Provider A, snapshotting, restoring with Provider B, querying the same queries, and verifying recall retention >= 0.95.

**Acceptance Scenarios**:

1. **Given** 1000 memories embedded with Provider A, **When** the developer snapshots to raw text and restores with Provider B, **Then** the same queries return contextually equivalent results with recall retention >= 0.95.
2. **Given** a snapshot file, **When** inspected, **Then** it contains only raw text content and metadata (no embeddings), making it fully provider-agnostic.

---

### User Story 4 - Agent Builder Commits Memory On-Chain (Priority: P2)

An agent developer commits the current memory state to permanent decentralized storage. The memory blob is encrypted (AES-256-GCM), hashed (SHA3-256), uploaded to Arweave, and the hash is anchored to Solana via a memo transaction.

**Why this priority**: On-chain verifiability is the second major differentiator. Without it, this is just another vector store.

**Independent Test**: Can be tested by committing a memory state and verifying the Arweave blob exists, Solana memo contains the correct hash, and the decrypted blob matches the original.

**Acceptance Scenarios**:

1. **Given** a memory state ready for commitment, **When** the developer calls the commit operation, **Then** the blob is encrypted with AES-256-GCM, hashed with SHA3-256, uploaded to Arweave, and the hash is committed to Solana.
2. **Given** a committed memory state, **When** the developer calls verify, **Then** the system fetches the blob, recomputes the hash, and confirms it matches the on-chain commitment.
3. **Given** a committed memory state, **When** someone without the correct keypair attempts to decrypt, **Then** decryption fails with a clear error message.

---

### User Story 5 - Agent Builder Runs the Live Demo (Priority: P3)

An agent developer or prospective user runs the V1 live demo to see the full pipeline in action: search, compression comparison, provider switch, on-chain commitment, and verification via a web UI.

**Why this priority**: The demo is the showcase for the entire V1 SDK. It communicates the value proposition and validates all prior stories end-to-end.

**Independent Test**: Can be tested by running the demo server, walking through all 5 acts, and verifying each act completes successfully.

**Acceptance Scenarios**:

1. **Given** the demo is started with a single command, **When** the user loads the web UI, **Then** a pre-loaded corpus of ~1000 research memories is ready for querying.
2. **Given** the demo is running, **When** the user walks through all 5 acts (Search, Compression Comparison, Provider Switch, Commit, Verify), **Then** each act completes successfully and demonstrates the stated capability.
3. **Given** no internet connection, **When** the demo is run in offline mode (mock commit, local embeddings), **Then** all acts complete successfully with mock chain operations.

---

### User Story 6 - Agent Builder Uses the SDK API (Priority: P2)

An agent developer integrates the Mnemonic SDK into their own application using a clean, documented public API. The API covers ingestion, retrieval, persistence, snapshot/restore, and on-chain commitment.

**Why this priority**: The SDK API surface is how developers actually consume V1. Without a clean, documented API, adoption is blocked.

**Independent Test**: Can be tested by importing the SDK, calling each public API method, and verifying correct behavior and clear error messages.

**Acceptance Scenarios**:

1. **Given** the SDK is installed, **When** the developer imports and calls the core operations (ingest, retrieve, persist, snapshot, restore), **Then** each call succeeds with correct behavior.
2. **Given** the SDK is imported, **When** the developer passes invalid inputs (empty content, wrong types), **Then** clear, actionable error messages are returned.

---

### Edge Cases

- What happens when the corpus is empty and a query is made? The system returns an empty result set without crashing.
- What happens when a memory item has extremely long content (>10,000 tokens)? The embedding provider handles truncation per its own limits; the SDK documents this behavior.
- What happens when the quantizer is not yet calibrated and retrieval is attempted? The system raises a clear error indicating the index needs to be built first.
- What happens when a SQLite file from a different schema version is loaded? The system detects the mismatch and provides a clear error.
- What happens when Arweave or Solana is unavailable during commitment? The system fails gracefully with a retry-friendly error without corrupting local state.
- What happens when two agents attempt to write to the same memory store simultaneously? V1 is single-writer; the system documents this limitation clearly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a Python SDK package (`mnemonic`) with a public API for memory ingestion, retrieval, persistence, snapshot/restore, and on-chain commitment.
- **FR-002**: System MUST support the 2-stage retrieval cascade: compressed candidate generation on the quantized shadow index followed by exact reranking on full-precision embeddings.
- **FR-003**: System MUST support corpus-calibrated per-dimension scalar quantization at 8-bit (default) and 4-bit (experimental) bit widths.
- **FR-004**: System MUST persist memory state to SQLite with lossless round-trip fidelity (recall retention = 1.000).
- **FR-005**: System MUST support snapshot (raw items to provider-agnostic JSONL, no embeddings) and restore (re-embed with any provider, rebuild quantized index).
- **FR-006**: System MUST encrypt memory blobs with AES-256-GCM before on-chain commitment, using HKDF key derivation from the Solana keypair.
- **FR-007**: System MUST commit encrypted blobs to Arweave and anchor SHA3-256 hashes to Solana via memo transactions.
- **FR-008**: System MUST verify committed memory by fetching the blob, recomputing the hash, and comparing against the on-chain commitment.
- **FR-009**: System MUST support at least three embedding providers: mock (offline), OpenAI (text-embedding-3-small), and Nomic (nomic-embed-text-v1.5 as V1 canonical).
- **FR-010**: System MUST provide a web-based live demo demonstrating the 5-act narrative: Load & Search, Compression Comparison, Provider Switch, On-Chain Commitment, and Verification.
- **FR-011**: System MUST include a demo corpus of ~1000 fictional journalism research memories across 5 domains (sources, documents, timeline events, connections, hypotheses).
- **FR-012**: System MUST provide a CLI entry point for demo, benchmark, persist-test, multidomain, and provider-switch operations.
- **FR-013**: System MUST serialize the quantizer state (per-dimension alphas and steps arrays) alongside packed codes during persistence and snapshot operations.
- **FR-014**: System MUST support configurable retrieval parameters: k (final results, default 10), n_candidates (shortlist size, default 50), and bit width (default 8).

### Key Entities

- **MemoryItem**: A unit of agent memory containing content, type (episodic/semantic/decision/project), importance score, tags, and timestamps. The source of truth for what the agent remembers.
- **EmbeddingRecord**: Full-precision float32 embedding vector linked to a MemoryItem, including model identity and dimension. Used for exact reranking (correctness layer).
- **QuantizedRecord**: Compressed representation of an embedding as packed integer codes at a given bit width. Used only for candidate generation (acceleration layer).
- **CalibratedScalarQuantizer**: Per-dimension calibration state (alphas, steps arrays) fitted from corpus statistics. Must be serialized alongside the index.
- **Memory Snapshot**: A provider-agnostic JSONL export of raw memory items (no embeddings). The portable unit for provider migration.
- **On-Chain Commitment**: An encrypted blob on Arweave paired with a SHA3-256 hash on Solana. The tamper-evident proof that a memory state existed at a given time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Agent developers can ingest 1000 memory items and retrieve results with final recall@10 >= 0.94 using 8-bit compression.
- **SC-002**: Compressed index uses <= 30% of the full float32 index size at 8-bit, <= 15% at 4-bit.
- **SC-003**: End-to-end retrieval completes in under 200ms for 1000 memories on a standard development machine.
- **SC-004**: SQLite round-trip preserves perfect fidelity: recall retention = 1.000 after save and restore.
- **SC-005**: Provider switch (snapshot, re-embed, rebuild) preserves retrieval quality with recall retention >= 0.95.
- **SC-006**: On-chain commitment cost is under $0.50 per snapshot for corpora up to 10,000 memories.
- **SC-007**: The live demo can be started with a single command and walked through in under 5 minutes by a new user.
- **SC-008**: Multi-domain retrieval (4+ domains) achieves recall@10 >= 0.95 and purity@10 >= 0.90.
- **SC-009**: All 5 demo acts (Search, Compression Comparison, Provider Switch, Commit, Verify) complete successfully end-to-end.
- **SC-010**: The SDK API surface is documented with usage examples for all core operations (ingest, retrieve, persist, snapshot, commit, verify).

## Assumptions

- V1 is single-writer by design. Concurrent writer support (event-sourced delta log per ADR-006) is deferred to V1.1.
- V1 targets corpora up to 10,000 memories. Performance at 100k+ is not a V1 requirement but the design should not preclude future scaling.
- The V1 canonical embedding model is nomic-embed-text-v1.5 (768-dim, Apache 2.0, open weights). OpenAI is supported as an alternative.
- Memory pruning, eviction, and lifecycle management are deferred to post-V1 (ADR-007 design exists).
- Security model for V1 assumes honest-but-curious operator and public-storage observer threats. Malicious collaborator mitigations are researched (ADR-009) but implementation is deferred.
- The existing mnemonic/ Python package, on-chain commitment module (onchain/commit.mjs), and test suite form the foundation. V1 implementation extends and productizes these existing components.
- On-chain operations use Solana mainnet and Arweave mainnet for the live demo; local Solana validator for development and testing.
- No consumer-facing UI in V1. The web demo is a developer showcase, not a production application.
- Memory write semantics (merge, deduplication, contradiction handling) are V1.1 scope; V1 uses simple append.
- Key management is single-owner keypair for V1. Multi-party access via key wrapping is designed but deferred to V2.
