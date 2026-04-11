# mnemonic-verify

Minimal verifiable memory round-trip CLI. Proves Mnemonic's write/storage/recall
integrity guarantees mechanically against local test nodes.

## What it does

1. **Write** — embed text, quantize, hash, store on Arweave, anchor hash on Solana
2. **Recall** — fetch anchor from Solana, fetch content from Arweave, verify hash match
3. **Tamper** — create a tampered copy to demonstrate detection

## Prerequisites

```bash
# Rust
rustup update stable

# Node.js (for arlocal)
npm install -g arlocal

# Solana CLI
sh -c "$(curl -sSfL https://release.solana.com/stable/install)"
```

## Quick start

```bash
# Terminal 1: start local nodes
bash scripts/start-local-nodes.sh

# Terminal 2: build and run
cargo build
cargo run -- status
cargo run -- write "The interest rate was cut by 25bps on March 15 2026"
cargo run -- recall <SOLANA_TX_SIG>
```

## Commands

```
mnemonic-verify write    <TEXT>           Write memory and return receipt
mnemonic-verify recall   <SOLANA_TX_SIG>  Recall and verify memory
mnemonic-verify tamper   <SOLANA_TX_SIG>  Create tampered copy (demo)
mnemonic-verify status                   Check local node connectivity
```

## Tests

```bash
# Requires arlocal + solana-test-validator running
cargo test
```

Tests gracefully skip if local nodes are not running.

## Environment

Copy `.env.example` to `.env` and adjust if needed:

```
ARWEAVE_URL=http://localhost:1984
SOLANA_RPC_URL=http://localhost:8899
```

## Architecture

```
write(text)
  -> embed (all-MiniLM-L6-v2, 384-dim ONNX)
  -> quantize (f32 -> i8, scalar)
  -> hash (SHA-256, canonical JSON)
  -> arweave.write (arlocal)
  -> arweave.mine
  -> solana.write_anchor (SPL Memo)
  -> receipt

recall(solana_tx_sig)
  -> solana.read_anchor -> AnchorRecord { arweave_tx_id, content_hash }
  -> arweave.read(arweave_tx_id) -> bytes
  -> hash(bytes) -> actual_hash
  -> compare actual_hash vs content_hash
  -> Verified | Tampered
```
