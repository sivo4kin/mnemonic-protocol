# BLOCKERS.md

## Executive Summary

**Status as of 2026-04-01: All V1 retrieval gates closed. V1 SDK development can begin.**

`turbo-quant-agent-memory` has proven technical feasibility at scale with real production embeddings:

- ✅ Compressed retrieval with real OpenAI embeddings: 88.6% candidate recall@10, 94.2% final recall@10 at 10k memories
- ✅ Exact reranking restores quality deterministically — round-trip all_identical at 1k and 10k
- ✅ SQLite snapshot/rehydrate: lossless, recall retention = 1.000
- ✅ Multi-domain corpus: recall@10 = 1.00, purity = 0.995 across code/legal/news/medical
- ✅ Concurrent writers architecture designed: event-sourced delta log (ADR-006)
- ✅ Product direction set: Personal Research Assistant, V2 target (ADR-011)

The remaining blockers are no longer “does the algorithm work?” They are product, security, and operational questions that must be resolved during V1 SDK development:

- secure enough (key management, per-entry signing)
- operationally coherent (pruning, compaction, lifecycle)
- performant enough at 100k+ scale
- understandable to customers
- monetizable
- maintainable under real-world usage

> Technical feasibility is proven. The remaining risk is product execution.

This document lists the blockers to resolve before V1 SDK release.

---

## Blocking Areas

### 1. Product Definition

#### Why this blocks implementation
A product cannot be implemented confidently until the team knows what is being built, for whom, and what problem it solves better than alternatives.

#### What is not covered yet
- first customer profile is not locked
- first product shape is not locked
- primary value proposition is not locked
- it is unclear whether the first offering is:
  - a personal encrypted memory vault
  - a developer SDK/API
  - a team/shared memory platform
  - a crypto-native/verifiable memory layer

#### Open questions
- Who is the first ideal customer profile (ICP)?
- What painful problem do they already feel today?
- What existing behavior/tool does this replace or improve?
- What is the smallest sellable product?
- Is v1 UI-first or API-first?
- Is the initial wedge coding agents, research agents, crypto-native agents, or something else?

#### Blocker status
**High**

---

### 2. Customer and Market Fit

#### Why this blocks implementation
Without a clear first customer and buying motion, engineering effort may optimize for the wrong use case.

#### What is not covered yet
- buying persona is not defined
- deployment expectations are not defined
- user sophistication level is not defined
- trust requirements differ drastically by segment and remain unresolved

#### Open questions
- Is the first buyer an end user, developer, team lead, infra owner, or enterprise buyer?
- Are we selling to individuals, startups, internal AI teams, or crypto-native orgs?
- Is self-hosting expected?
- Is hosted mode acceptable for the target customer?
- What outcome will make the customer pay?

#### Blocker status
**High**

---

### 3. Security and Privacy Model

#### Why this blocks implementation
The system is memory infrastructure. If privacy claims are vague or incorrect, the product becomes untrustworthy immediately.

#### What is not covered yet
- formal threat model
- exact encryption boundaries
- operator visibility
- metadata leakage policy
- security claims for marketing/docs
- privacy guarantees under real hosting conditions

#### Open questions
- What threat model is v1 defending against?
  - honest-but-curious operator?
  - compromised backend?
  - public storage observer?
  - malicious collaborator?
- What is encrypted exactly?
- What remains visible to the server/operator?
- Can embeddings/index structures leak sensitive information?
- What privacy guarantees can be stated honestly?
- What privacy guarantees must *not* be claimed?

#### Blocker status
**Critical**

---

### 4. Encryption Architecture

#### Why this blocks implementation
“Encrypted memory” is currently a concept, not a fully specified design.

#### What is not covered yet
- whether content is encrypted client-side
- whether embeddings are encrypted at rest
- whether compressed index artifacts are encrypted at rest
- whether search happens only in trusted environments
- whether snapshots are encrypted before persistence
- how integrity and confidentiality interact

#### Open questions
- Is encryption performed client-side or server-side?
- Are raw memory items encrypted before any remote write?
- Are snapshots encrypted before being stored or anchored?
- Are embeddings stored plaintext, obfuscated, wrapped, or encrypted?
- Is full retrieval possible without exposing sensitive semantics?
- What is the acceptable privacy-performance tradeoff in v1?

#### Blocker status
**Critical**

---

### 5. Key Management and Recovery

#### Why this blocks implementation
Encryption without a credible key model is not a product—it is a risk.

#### What is not covered yet
- vault key model
- per-user vs per-vault keys
- wallet-based vs passphrase-based vs KMS-based key wrapping
- recovery model
- rotation model
- revocation model
- key-sharing model

#### Open questions
- Who holds the decryption keys?
- Is the product user-owned, operator-assisted, or operator-managed?
- How are keys recovered if a user loses access?
- How does access revocation work?
- How does sharing work safely?
- How does rotation work without re-encrypting everything expensively?

#### Blocker status
**Critical**

---

### 6. Real Agent Integration

#### Why this blocks implementation
The system has not yet been proven as a useful memory layer inside a real agent loop.

#### What is not covered yet
- end-to-end integration into a real agent workflow
- memory write triggers in real usage
- memory retrieval usefulness in iterative sessions
- effect on agent output quality over time
- failure modes inside the actual loop

#### Open questions
- Does this actually improve a live agent’s continuity and decision quality?
- What memories should be written automatically vs manually?
- How often should the agent query memory?
- How much retrieval is too much?
- How do we measure usefulness in a live agent setting?

#### Blocker status
**Critical**

---

### 7. Memory Write Semantics

#### Why this blocks implementation
A production memory system needs explicit rules for what enters memory and how it evolves.

#### What is not covered yet
- write policy
- merge vs append policy
- duplication policy
- contradiction policy
- source-of-truth policy
- confidence/importance model

#### Open questions
- What qualifies as a memory item?
- When does the system write memory?
- When does it merge with an existing memory?
- How are duplicates detected?
- How are contradictions represented?
- What is canonical over time: raw events, normalized memory items, or summaries?

#### Blocker status
**High**

---

### 8. Memory Pruning, Eviction, and Lifecycle

#### Why this blocks implementation
Memory cannot grow forever. Long-lived systems need retention and compaction policy.

#### What is not covered yet
- eviction strategy
- summarization/compaction strategy
- archival tiering
- retention classes
- deletion semantics
- stale/conflicting memory handling

#### Open questions
- What gets pruned first?
- What is importance and how is it computed?
- Are old memories summarized before deletion?
- How does pruning affect retrieval quality?
- Can users pin memories?
- Can some memory types be immutable while others are ephemeral?

#### Blocker status
**Critical**

---

### 9. Concurrent Writers and Consistency Model

#### Why this blocks implementation
The moment multiple sessions or agents write to shared memory, consistency becomes a systems problem.

#### What is not covered yet
- single-writer vs multi-writer model
- append-only vs mutable records
- conflict resolution
- versioning/snapshot boundaries
- ordering semantics
- workspace isolation

#### Open questions
- What happens when two sessions write at the same time?
- Is the system append-only?
- Is last-write-wins acceptable anywhere?
- Are snapshots atomic?
- Do we need optimistic concurrency control?
- Can multiple agents safely write into the same workspace?

#### Blocker status
**Critical**

---

### 10. Retrieval Validation with Real Embeddings

#### Why this blocks implementation
Mock feasibility is encouraging, but product behavior must be proven using real embedding distributions.

#### What is not covered yet
~~- broad testing with real embeddings~~
~~- multiple corpus types~~
~~- multiple domains/tenants~~
~~- calibration behavior across corpora~~

Remaining open: stability over time (rolling ingestion, quantizer drift at high-volume corpora).

#### Open questions
~~- Does quality hold with real embeddings?~~ **Yes. 8-bit: 94.2% final recall@10 at 10k with real OpenAI embeddings (ADR-016).**
~~- Does quantization calibration need per-corpus tuning?~~ **No. Corpus-calibrated fit generalizes across 4 domains and 10k items without retuning (ADR-013).**
~~- How much quality variance appears across domains?~~ **Low. Multi-domain purity@10 = 0.995, recall@10 = 1.000 across code/legal/news/medical (ADR-013).**
- Does recall hold under mixed and messy real-world memory? → Validated for structured JSONL corpus. Unstructured/noisy data not tested.
- Are there pathological corpora where performance collapses? → Open. No adversarial or degenerate corpus tested yet.

#### Blocker status
~~**High**~~ **RESOLVED** for V1 (ADR-016, ADR-013). Remaining items are post-V1 hardening.

---

### 11. Scale Validation

#### Why this blocks implementation
A product cannot be shipped confidently without understanding how the system behaves beyond toy sizes.

#### What is not covered yet
~~- 10k/100k/1M memory behavior~~ → **10k validated (ADR-016). 100k/1M not tested.**
~~- ingest scaling~~ → **10k ingest: 46s (OpenAI batched, ~79 API calls). Acceptable for background ingestion.**
~~- snapshot scaling~~ → **10k serialize: 0.7s, rehydrate: 4.9s. Both fast.**
~~- storage growth curves~~ → **8-bit: 1.46 KB/item at 1536-dim. Predictable linear growth.**
- restore scaling → partially tested (10k). Large SQLite restore speed not benchmarked.
- memory footprint growth → not profiled at 100k+

#### Open questions
~~- What breaks first as corpus size grows?~~ → **At 10k, recall drops predictably with n_candidates/N ratio. Increase n_candidates to compensate.**
~~- How does recall change at larger scale?~~ → **At 0.5% shortlist (10k, n_candidates=50): 94.2% final recall. At 5% shortlist (1k, n_candidates=50): 99.4%. Shortlist ratio is the control knob.**
~~- How does candidate shortlist quality degrade with scale?~~ → **Gracefully and predictably — tunable via n_candidates.**
- How expensive are rebuilds at 100k+? → Open.
- Can memory growth stay operationally manageable? → Linear at $0.039/1k items/snapshot on Arweave. Acceptable for V1 (≤10k items). Needs review at 100k.

#### Blocker status
**High**

---

### 12. Latency and Production Performance

#### Why this blocks implementation
A correct system that is too slow is not a product.

#### What is not covered yet
- p50/p95/p99 latency
- throughput under concurrency
- ingestion/update latency
- restore latency
- cold-start behavior
- optimization plan to NumPy/Rust/C hot paths

#### Open questions
- What is the product latency target?
- Can current Python code meet it?
- Which paths must be optimized first?
- What throughput is required per active customer?
- What is the acceptable end-to-end latency in a live agent loop?

#### Blocker status
**Critical**

---

### 13. Robustness to Noisy or Adversarial Data

#### Why this blocks implementation
Production memory is messy. If the system works only on clean synthetic data, it is not ready.

#### What is not covered yet
- duplicate-heavy inputs
- contradictory inputs
- spam inputs
- very long inputs
- noisy heterogeneous memory
- adversarial retrieval poisoning

#### Open questions
- Can a few bad memories distort calibration?
- Can duplicate clusters dominate retrieval?
- How does the system handle malicious or irrelevant writes?
- What retrieval quality drop is acceptable under noisy conditions?

#### Blocker status
**Medium-High**

---

### 14. Storage Architecture and Economics

#### Why this blocks implementation
A memory product must have a sustainable storage and serving model.

#### What is not covered yet
- storage tiering model
- hosted cost per customer
- snapshot cadence economics
- archival economics
- margin model
- optional on-chain anchoring cost model

#### Open questions
- What does this cost per active vault/team?
- How often are snapshots needed in practice?
- When should snapshots be incremental vs full?
- Does hosted operation have healthy gross margins?
- Is chain anchoring optional, premium, or core?

#### Blocker status
**High**

---

### 15. End-User Experience (UX)

#### Why this blocks implementation
A product requires a clear workflow, not just a backend.

#### What is not covered yet
- onboarding flow
- vault creation flow
- agent connection flow
- inspect/search/delete flow
- restore flow
- sharing flow
- permission management UX
- privacy/trust explanation UX

#### Open questions
- How does a new user get value in the first 5 minutes?
- How do they connect an assistant or tool?
- How do they see what the system remembers?
- How do they delete or correct a memory?
- How do they recover access?
- How do they trust that memory is really private?

#### Blocker status
**High**

---

### 16. Developer Experience (DX)

#### Why this blocks implementation
If this is sold as infrastructure, developer ergonomics will determine adoption.

#### What is not covered yet
- API shape
- SDK ergonomics
- debugging tools
- explainability for retrieval
- local dev mode
- migration/versioning API

#### Open questions
- What are the core API primitives?
- How do developers understand why a memory was returned?
- How do developers test locally?
- How do schema/index changes get rolled forward safely?

#### Blocker status
**Medium-High**

---

### 17. Compliance, Trust, and Data Governance

#### Why this blocks implementation
Memory systems often store sensitive user/project data. Governance matters early.

#### What is not covered yet
- export guarantees
- deletion guarantees
- audit trail model
- data residency implications
- tenant isolation posture
- legal/privacy claims

#### Open questions
- Can a user fully export their data?
- Can a user fully delete their data?
- Can the system prove what was stored and when?
- Is there a durable audit trail?
- What compliance posture is expected by the target market?

#### Blocker status
**High**

---

### 18. Pricing, Packaging, and Monetization

#### Why this blocks implementation
Engineering scope depends on how the product is sold.

#### What is not covered yet
- free tier strategy
- pro/team/enterprise boundaries
- subscription vs usage-based pricing
- premium feature boundaries
- infra vs application packaging

#### Open questions
- What exactly is the paid product?
- What is included in free vs paid?
- Is encryption standard or premium?
- Is verifiable snapshotting standard, premium, or niche?
- Is pricing seat-based, storage-based, usage-based, or hybrid?

#### Blocker status
**Medium-High**

---

### 19. Go-to-Market and Positioning

#### Why this blocks implementation
The product needs a coherent narrative and wedge to avoid building a technically interesting but unsellable system.

#### What is not covered yet
- category positioning
- narrative hierarchy
- wedge market selection
- competitive framing
- distribution path

#### Open questions
- Is this positioned as an AI memory vault, agent memory infrastructure, or verifiable crypto-native memory?
- What is the first wedge market?
- What is the simple story customers repeat to others?
- Why is this better than app-native memory or a vector DB?

#### Blocker status
**High**

---

## Detailed Open Questions

### Product Strategy
1. Who is the first paying customer?
2. What is the first product: vault, API, platform, or crypto-native infra?
3. What urgent pain does the customer already have today?
4. What is the smallest version that delivers paid value?
5. What is the product’s one-sentence positioning?

### Security and Encryption
6. What exactly is encrypted in v1?
7. What data remains visible to the operator or storage layer?
8. Can embeddings or index artifacts leak useful semantic information?
9. What privacy claims are true enough to put on a website?
10. What threat model is the system actually designed for?

### Keys and Access
11. Who controls keys?
12. How are keys recovered?
13. How does sharing work?
14. How does revocation work?
15. How does key rotation work?

### Memory Semantics
16. What qualifies as a memory item?
17. When does the system write memory?
18. When does it append vs merge vs overwrite?
19. How are conflicts and contradictions represented?
20. What makes a memory important enough to keep?

### Lifecycle and Concurrency
21. How does pruning work?
22. How does summarization/compaction work?
23. What happens when two sessions write simultaneously?
24. Are snapshots atomic?
25. What is the consistency model?

### Retrieval and Performance
~~26. Does quality hold with real embeddings?~~ → **Yes. 94.2% final recall@10 at 10k, real OpenAI embeddings (ADR-016).**
~~27. Does quality hold across domains and larger corpora?~~ → **Yes. Multi-domain recall@10=1.00, purity=0.995 across 4 domains at 10k (ADR-013).**
28. What is the acceptable recall threshold for production? → 94%+ final recall is strong; production target ≥ 95% achievable with n_candidates=200.
29. What is the acceptable latency target for production?
30. Which hot paths need optimization or rewrite?

### Product Experience
31. How does a user onboard quickly?
32. How do they inspect, edit, correct, or delete memory?
33. How do they restore a vault?
34. How do they trust the privacy model?
35. How do developers integrate and debug it easily?

### Business Model
36. What is the pricing model?
37. What are the free and paid tiers?
38. Why will a customer pay instead of relying on app-native memory or plain vector storage?
39. What is the target margin profile?
40. Which market is the first realistic wedge?

---

## Recommended Resolution Order

### Phase 0 — Immediate blockers (must clarify before serious product build)
1. **Product definition / first customer / first wedge**
2. **Security and privacy model**
3. **Encryption architecture**
4. **Key management and recovery**
5. **Real agent integration hypothesis**

### Phase 1 — System semantics
6. **Memory write semantics**
7. **Pruning/eviction/lifecycle model**
8. **Concurrent writers / consistency model**
9. **User-facing trust/export/delete semantics**

### Phase 2 — Validation under reality
10. **Real embeddings validation**
11. **Scale validation**
12. **Latency/performance benchmarks**
13. **Robustness/noise/adversarial tests**

### Phase 3 — Productization
14. **UX flows**
15. **DX/API shape**
16. **Storage economics**
17. **Pricing/packaging**
18. **Go-to-market and positioning**

---

## Go / No-Go Criteria

The project should move into real product implementation only if the following are true.

### Product
- First customer profile is explicitly chosen.
- First product shape is explicitly chosen.
- Core paid value is clear and defensible.

### Security
- v1 security model is documented.
- Encryption boundaries are explicitly defined.
- Key custody and recovery are explicitly defined.
- Privacy claims are honest and auditable.

### System Semantics
- Memory write/update/prune policy exists.
- Concurrency/consistency model exists.
- Snapshot/restore semantics are defined.

### Validation
- Real-embedding tests show acceptable retrieval quality.
- Scale tests show acceptable behavior at target corpus size.
- Latency benchmarks meet product targets or there is a credible optimization path.
- Agent-loop tests show real utility in practice.

### Product Experience
- Onboarding, inspect/delete, restore, and sharing flows are defined.
- Export and deletion guarantees are documented.

### Business
- Pricing and packaging are defined enough to inform architecture.
- The first go-to-market wedge is chosen.

If these criteria are not met, implementation should remain in **validation/prototyping mode**, not full product build mode.

---

## Final Assessment

Current status:

- **Algorithm / retrieval concept:** promising
- **Snapshot / integrity concept:** promising
- **Product readiness:** not proven
- **Security/privacy readiness:** not proven
- **Operational semantics readiness:** not proven
- **Commercial readiness:** not proven

Therefore:

> The correct next step is not broad product implementation.
> The correct next step is to resolve the blockers above through specification, validation, and narrowing of scope.

A disciplined path forward would produce four concrete follow-up documents:

1. `PRODUCT_THESIS.md`
2. `SECURITY_MODEL.md`
3. `MEMORY_LIFECYCLE.md`
4. `VALIDATION_PLAN.md`

This would convert the project from a technically interesting prototype into a serious product candidate.
