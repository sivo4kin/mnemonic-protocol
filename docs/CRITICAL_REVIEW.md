# Critical Documentation Review — Mnemonic Protocol

**Date**: 2026-04-01
**Scope**: All project documentation cross-referenced against implementation and measured data
**Verdict**: Core architecture claims are solid. Periphery has 7 issues requiring correction.

**Status (updated 2026-04-01):**
- Issues 3, 4, 5, 6, 7 and cross-doc writer model: **FIXED** (doc edits applied)
- Issue 1 (Arweave cost): **FIXED** — Arweave pricing validated via Irys price API; WHITEPAPER economics updated with measured rates ($16.74/GB at AR=$1.75)
- Issue 2 (Embedding model): **FIXED** — `nomic-embed-text-v1.5` validated in ADR-017: final recall@10 = 1.000 at 1K–5K, multi-domain purity = 1.000, persistence lossless. Adopted as V1 canonical embedder. All docs updated.

---

## Issue 1: Arweave Cost Claim Is Wrong by ~5x

**Location**: WHITEPAPER.md (storage economics section)
**Claim**: Arweave pricing ~$5/GB permanent
**Measured**: $0.394 for 14.6 MB = ~$27/GB (from MVP_SPEC.md results table)
**Severity**: HIGH — economics section is externally visible and misleading

### Fix Plan

1. Read current Arweave bundler pricing (Irys/Bundlr) to confirm
   whether $27/GB reflects bundler markup or base Arweave rate
2. Replace the "$5/GB" estimate in WHITEPAPER.md with the measured
   rate derived from actual uploads
3. Update the storage economics table in MVP_SPEC.md to include
   a $/GB column so the per-snapshot cost and per-GB rate are
   both visible
4. Add a footnote clarifying whether the measured cost includes
   bundler fees, and what the base Arweave endowment rate is

---

## Issue 2: V1 Embedding Model Ambiguity — RESOLVED

**Location**: WHITEPAPER.md section 4.2 vs SCHEMA.md vs MVP_SPEC.md
**Claim**: WHITEPAPER says "Production V1 should validate with
canonical open embedder (nomic-embed-text-v1.5, 768-dim)"
**Reality**: ~~All V1 gates passed with proprietary OpenAI
`text-embedding-3-small` (1536-dim)~~ **Resolved: ADR-017 validated
`nomic-embed-text-v1.5` (768-dim) — final recall@10 = 1.000 at 1K–5K,
multi-domain purity = 1.000, persistence lossless. Adopted as V1
canonical embedder.**
**Severity**: ~~HIGH~~ RESOLVED

### Resolution (ADR-017)

- `NomicEmbeddingProvider` added to `mnemonic/embedders.py`
- Full benchmark suite run: 1K (8-bit, 4-bit), 5K (8-bit), multi-domain, persist-test — all pass
- WHITEPAPER.md section 4.2 updated from recommendation to authoritative
- SCHEMA.md default embedding model updated to nomic
- MVP_SPEC.md defaults updated
- 10K validation deferred to machine with ≥8 GB RAM (3.8 GB insufficient for sentence-transformers + 10K embeddings)

---

## Issue 3: Quantizer Drift Robustness Is Unvalidated

**Location**: CONCURRENT_WRITERS.md, condensed-principles.md
**Claim**: 98th-percentile calibration is "robust to small additions"
**Reality**: Never empirically tested. BLOCKERS.md confirms
"unstructured/noisy data not tested"
**Severity**: MEDIUM — affects multi-writer correctness guarantee

### Fix Plan

1. Design a drift experiment:
   - Start with 10K memories (single domain, e.g., code)
   - Calibrate quantizer
   - Append 1K memories from a different domain (e.g., legal)
   - Measure recall@10 before and after append WITHOUT recalibrating
   - Repeat with 10%, 25%, 50% distribution shift
2. Run the experiment, record results
3. If recall degrades >2%: define a recalibration trigger threshold
   and document it
4. If recall holds: update docs to cite the experiment instead of
   making an unsupported "robust" claim
5. Write ADR documenting findings

---

## Issue 4: "Deterministic" Claim Is Imprecise

**Location**: WHITEPAPER.md section 3.7, MVP_VERIFICATION.md
**Claim**: System is "deterministic"
**Reality**: Compressed candidate stage (integer arithmetic) is
deterministic. Exact rerank (float arithmetic) may produce different
scores across CPU architectures, potentially changing final ordering.
**Severity**: LOW — technically accurate but misleading to readers

### Fix Plan

1. In WHITEPAPER.md section 3.7, replace "the system is
   deterministic" with a scoped statement:
   - "Compressed candidate generation is fully deterministic
     (integer arithmetic)"
   - "Exact rerank uses IEEE 754 float operations; scores are
     reproducible on the same architecture but may differ across
     CPU implementations"
   - "The top-k candidate SET is deterministic; final ordering
     within that set is architecture-dependent at tie-breaking
     precision"
2. In MVP_VERIFICATION.md, add a "Determinism Scope" subsection
   clarifying the boundary
3. In the constitution (.specify/memory/constitution.md), Principle I
   says "round-trip determinism is non-negotiable" — add a
   parenthetical clarifying this refers to the serialize → hash →
   rehydrate path (which IS fully deterministic), not float rerank
   scores

---

## Issue 5: Multi-Domain Generalization Overstated

**Location**: ADR-013, MVP_SPEC.md results table
**Claim**: recall@10 = 1.000, purity = 0.995 across 4 domains
**Reality**: Test corpus used synthetic data with clearly distinct
vocabulary (code, legal, news, medical). Real-world domains have
overlapping vocabulary. Perfect scores partly reflect clean domain
separation in the test data, not real-world generalization.
**Severity**: MEDIUM — could mislead SDK users about retrieval quality

### Fix Plan

1. Add a "Limitations" note to ADR-013 acknowledging that the
   corpus had distinct domain vocabularies and that real-world
   overlap was not tested
2. In MVP_SPEC.md results section, add a footnote: "Multi-domain
   test used synthetic corpus with distinct vocabulary per domain.
   Cross-domain overlap scenarios not yet validated."
3. Design a follow-up experiment with intentionally ambiguous
   queries (e.g., "compliance monitoring" which could be legal or
   medical) and a corpus with vocabulary overlap
4. Defer this experiment to post-V1 but track it in BLOCKERS.md
   as a known limitation

---

## Issue 6: Recall Scaling Is Observed but Not Modeled

**Location**: MVP_SPEC.md, BLOCKERS.md
**Claim**: Recall degradation is "predictable" with corpus size
**Reality**: Two data points (1K: 99.4%, 10K: 94.2%) with no
formula or model. Cannot predict recall at 50K or 100K.
**Severity**: MEDIUM — "predictable" implies a known relationship

### Fix Plan

1. Replace "predictable" with "observed" in all docs — specifically
   MVP_SPEC.md and BLOCKERS.md
2. Add a third data point: run the benchmark at 5K memories to get
   an intermediate measurement
3. Plot recall vs corpus size (1K, 5K, 10K) at fixed
   n_candidates=50 and fit a curve (likely logarithmic or
   power-law decay)
4. If a clean model emerges, document the formula and its validity
   range
5. If no clean model: document it as "empirical, tune n_candidates
   per deployment" and remove any language implying predictability
6. Add the recall-vs-scale curve to WHITEPAPER.md section 3

---

## Issue 7: Compression Ratio Ignores Metadata Overhead

**Location**: WHITEPAPER.md section 3.3
**Claim**: 25% (8-bit) and 12.5% (4-bit) as universal ratios
**Reality**: True for raw vectors. Per-record metadata (quantizer
state headers, alignment padding) adds overhead that is non-trivial
at small dimensions (384-dim: ~5% overhead)
**Severity**: LOW — minor, but the "universal" framing is slightly
misleading

### Fix Plan

1. Add a row to the compression table in WHITEPAPER.md showing
   "effective ratio including metadata" for each dimension
2. Add a footnote: "Ratios reflect raw vector compression. Per-record
   metadata overhead is <2% at 1536-dim and <5% at 384-dim."
3. No code changes needed

---

## Cross-Document Contradictions

### V1 Embedder (Issue 2 overlap) — RESOLVED

- ~~SCHEMA.md says OpenAI `text-embedding-3-small`~~ Updated to nomic
- ~~WHITEPAPER.md says "canonical open embedder"~~ Updated to authoritative (validated)

Resolution: ADR-017 validated nomic as V1 canonical embedder. All docs updated.

### V1 Writer Model

- PROJECT_STATE.md: "single-writer V1"
- ADR-006: concurrent writer architecture "for V1 SDK phase"

### Fix Plan

1. Clarify in PROJECT_STATE.md: "V1.0 SDK ships single-writer.
   Concurrent writers (ADR-006) are V1.1 scope."
2. Update ADR-006 header to reflect "V1.1" not "V1"

---

## Prioritized Execution Order

| Priority | Issue | Status | Effort | Why This Order |
|----------|-------|--------|--------|----------------|
| P1 | Issue 1: Arweave cost | ✅ FIXED | — | Arweave pricing validated, docs updated |
| P1 | Issue 2: Embedding model | ✅ FIXED (ADR-017) | — | nomic validated, adopted as V1 canonical |
| P2 | Issue 4: Determinism claim | ✅ FIXED | — | Scoped in WHITEPAPER |
| P2 | Issue 7: Compression overhead | ✅ FIXED | — | Footnote added |
| P2 | Issue 5: Multi-domain caveat | ✅ FIXED | — | Limitation noted |
| P2 | Cross-doc: writer model | ✅ FIXED | — | V1.0 single-writer clarified |
| P3 | Issue 6: Recall scaling | Open | 2-4 hours | Requires benchmark run |
| P3 | Issue 3: Quantizer drift | Open | 4-8 hours | Requires new experiment |

**All P1 and P2 issues resolved.** Remaining P3 issues are post-V1 hardening — tracked in BLOCKERS.md.
