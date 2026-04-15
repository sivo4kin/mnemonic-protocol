# V0_SCOPE.md

## Purpose

Define what V0 of Mnemonic verification must prove, and what is intentionally out of scope.

## V0 goal

V0 proves a deterministic, local, end-to-end trust loop for memory records:

1. write memory payload
2. store payload in Arweave (local arlocal)
3. anchor digest in Solana (local validator)
4. recall and verify integrity
5. detect tampering reliably

## In scope (implemented)

### 1) CLI verification product
- Rust CLI `mnemonic-verify` with four commands:
  - `write <TEXT>`
  - `recall <SOLANA_TX_SIG>`
  - `tamper <SOLANA_TX_SIG>`
  - `status`
- Human-readable and JSON outputs for receipts/verdicts.

### 2) Deterministic memory payload + hashing
- Text embedding + quantization pipeline.
- Canonical hash flow used consistently across write and recall.
- Hash mismatch produces explicit tamper verdict.

### 3) Arweave local persistence path
- Arweave writes are valid signed v2 transactions (not dummy txs).
- Local JWK-based signing via `ARWEAVE_JWK_PATH`.
- Local wallet funding retry behavior for arlocal token errors.
- Mining step included so written tx becomes readable.

### 4) Solana local anchoring path
- Anchor record written via SPL Memo transaction.
- Anchor record read back from transaction/memo.
- Verification compares recalled content hash vs anchored hash.

### 5) Tamper simulation + detection
- `tamper` command creates corrupted content + mismatched anchor.
- `recall` on tampered signature returns `Tampered`.
- Expected hash is preserved from Solana anchor for forensic comparison.

### 6) Local infra automation
- Reusable infra bootstrap library in `scripts/lib/local-infra.sh`.
- Local nodes start/reuse + readiness checks.
- Shared test entrypoint:
  - `bash scripts/run-tests.sh integration`
  - `bash scripts/run-tests.sh all`
- CLI roundtrip verifier:
  - `bash scripts/verify-cli.sh`
  - Asserts correctness of write/recall/tamper correspondence.

### 7) Test coverage for V0 behavior
- Unit + integration tests for:
  - write/recall success path
  - receipt/hash consistency
  - distinct writes uniqueness
  - tamper detection
  - anchor-not-found behavior

## Out of scope (V0 non-goals)

- Mainnet deployment or production wallet/key management.
- Remote/shared infrastructure and hosted services.
- Multi-tenant auth/access control.
- Public verification web UX.
- Blob/file storage and attachments.
- Checkpoint versioning and restore workflows.
- Protocol-grade economics/incentive model.
- Hardening for adversarial production traffic.

## V0 acceptance criteria

V0 is complete when all are true:

1. `status` reports local Arweave + Solana reachable.
2. `write` returns receipt with `arweave_tx_id`, `solana_tx_sig`, `content_hash`.
3. `recall` of the fresh signature returns `Verified` and matching hashes/text.
4. `tamper` followed by `recall` returns `Tampered` with hash mismatch.
5. `bash scripts/verify-cli.sh` exits successfully with all assertions passing.
6. `bash scripts/run-tests.sh integration` and `bash scripts/run-tests.sh all` pass locally.

## Bottom line

V0 proves that Mnemonic can produce and mechanically verify a local cryptographic memory integrity loop (write → anchor → recall → verify/tamper-detect) with reproducible tooling and tests.