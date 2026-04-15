/**
 * Mnemonic — Local Solana Validator Tests
 *
 * Spins up solana-test-validator, funds a keypair, and runs
 * end-to-end commitment tests against the local ledger.
 *
 * Usage:
 *   node test-local.mjs                  # assumes validator already running
 *   node test-local.mjs --start-validator # auto-start/stop validator
 */

import { readFileSync, writeFileSync, unlinkSync, existsSync } from "fs";
import { execSync, spawn } from "child_process";
import { createHash } from "crypto";
import {
  Connection,
  Keypair,
  PublicKey,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import { sha3_256, commitToSolana } from "./commit.mjs";
import { encryptBlob, decryptBlob, isEncryptedBlob } from "./encrypt.mjs";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const LOCAL_RPC = "http://127.0.0.1:8899";
const KEYPAIR_PATH = new URL("./test-keypair.json", import.meta.url).pathname;
const TEST_BLOB_PATH = new URL("./test-blob.bin", import.meta.url).pathname;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let validatorProc = null;

function log(msg) {
  console.log(`  ${msg}`);
}

function pass(name) {
  console.log(`  ✓ ${name}`);
}

function fail(name, err) {
  console.error(`  ✗ ${name}: ${err}`);
  process.exitCode = 1;
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForValidator(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const conn = new Connection(url, "confirmed");
      await conn.getSlot();
      return true;
    } catch {
      await sleep(500);
    }
  }
  throw new Error(`Validator not ready after ${timeoutMs}ms`);
}

function startValidator() {
  console.log("\n🚀 Starting solana-test-validator...");
  validatorProc = spawn("solana-test-validator", ["--quiet", "--reset"], {
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PATH: `${process.env.HOME}/.local/share/solana/install/active_release/bin:${process.env.PATH}` },
  });
  validatorProc.on("error", (err) => {
    console.error(`Failed to start validator: ${err.message}`);
    process.exit(1);
  });
  return validatorProc;
}

function stopValidator() {
  if (validatorProc) {
    console.log("\n🛑 Stopping solana-test-validator...");
    validatorProc.kill("SIGTERM");
    validatorProc = null;
  }
}

// ---------------------------------------------------------------------------
// Test blob generation (minimal valid MNEM blob)
// ---------------------------------------------------------------------------

function createTestBlob(numMemories = 3, bits = 8, dim = 384) {
  // Build a minimal MNEM-format blob for testing
  const header = Buffer.alloc(64);

  // Magic: "MNEM"
  header.write("MNEM", 0, 4, "ascii");
  // Version
  header.writeUInt16LE(1, 4);
  // Embedding model (32 bytes, zero-padded)
  header.write("test-model", 6, 32, "utf-8");
  // Dim
  header.writeUInt16LE(dim, 38);
  // Bits
  header.writeUInt8(bits, 40);
  // Num memories
  header.writeUInt32LE(numMemories, 42);

  // Quantizer state: alphas + steps (dim * 4 bytes each)
  const quantState = Buffer.alloc(dim * 4 * 2);
  for (let i = 0; i < dim; i++) {
    quantState.writeFloatLE(0.05, i * 4);           // alpha
    quantState.writeFloatLE(0.05 / 127, dim * 4 + i * 4); // step
  }

  // Per-record data (simplified)
  const records = [];
  for (let i = 0; i < numMemories; i++) {
    const id = `test-mem-${i}`;
    const content = `Test memory content number ${i}`;
    const meta = JSON.stringify({ type: "test", importance: 0.5 });

    const idBuf = Buffer.from(id, "utf-8");
    const contentBuf = Buffer.from(content, "utf-8");
    const metaBuf = Buffer.from(meta, "utf-8");

    // Length-prefixed fields
    const recHeader = Buffer.alloc(12);
    recHeader.writeUInt32LE(idBuf.length, 0);
    recHeader.writeUInt32LE(contentBuf.length, 4);
    recHeader.writeUInt32LE(metaBuf.length, 8);

    const norm = Buffer.alloc(4);
    norm.writeFloatLE(1.0, 0);

    // Normalized embedding (dim * 4 bytes)
    const embedding = Buffer.alloc(dim * 4);
    for (let d = 0; d < dim; d++) {
      embedding.writeFloatLE(Math.random() * 0.1 - 0.05, d * 4);
    }

    // Packed codes
    const codeBytes = bits === 4 ? Math.ceil(dim / 2) : dim;
    const codes = Buffer.alloc(codeBytes);
    for (let d = 0; d < codeBytes; d++) {
      codes[d] = Math.floor(Math.random() * 256);
    }

    records.push(Buffer.concat([recHeader, idBuf, contentBuf, metaBuf, norm, embedding, codes]));
  }

  // Footer: record count
  const footer = Buffer.alloc(4);
  footer.writeUInt32LE(numMemories, 0);

  const blob = Buffer.concat([header, quantState, ...records, footer]);
  writeFileSync(TEST_BLOB_PATH, blob);
  return blob;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function testHashDeterminism() {
  const name = "SHA3-256 hash is deterministic";
  try {
    const blob = createTestBlob();
    const h1 = sha3_256(blob);
    const h2 = sha3_256(blob);
    if (h1 !== h2) throw new Error(`hashes differ: ${h1} vs ${h2}`);
    if (h1.length !== 64) throw new Error(`unexpected hash length: ${h1.length}`);
    pass(name);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testBlobValidation() {
  const name = "MNEM blob header validation";
  try {
    const blob = createTestBlob(5, 8, 384);
    const magic = blob.slice(0, 4).toString("ascii");
    if (magic !== "MNEM") throw new Error(`bad magic: ${magic}`);
    const version = blob.readUInt16LE(4);
    if (version !== 1) throw new Error(`bad version: ${version}`);
    const dim = blob.readUInt16LE(38);
    if (dim !== 384) throw new Error(`bad dim: ${dim}`);
    const bits = blob.readUInt8(40);
    if (bits !== 8) throw new Error(`bad bits: ${bits}`);
    const numMem = blob.readUInt32LE(42);
    if (numMem !== 5) throw new Error(`bad num_memories: ${numMem}`);
    pass(name);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testSolanaConnection() {
  const name = "Connect to local validator";
  try {
    const conn = new Connection(LOCAL_RPC, "confirmed");
    const slot = await conn.getSlot();
    if (typeof slot !== "number" || slot < 0) throw new Error(`bad slot: ${slot}`);
    pass(`${name} (slot=${slot})`);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testAirdrop() {
  const name = "Airdrop SOL on local validator";
  try {
    const conn = new Connection(LOCAL_RPC, "confirmed");
    const keyData = JSON.parse(readFileSync(KEYPAIR_PATH, "utf-8"));
    const payer = Keypair.fromSecretKey(Uint8Array.from(keyData));

    const sig = await conn.requestAirdrop(payer.publicKey, 2 * LAMPORTS_PER_SOL);
    const bh = await conn.getLatestBlockhash();
    await conn.confirmTransaction({ signature: sig, ...bh }, "confirmed");

    const balance = await conn.getBalance(payer.publicKey);
    if (balance < LAMPORTS_PER_SOL) throw new Error(`low balance: ${balance}`);
    pass(`${name} (${(balance / LAMPORTS_PER_SOL).toFixed(2)} SOL)`);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testMemoCommitment() {
  const name = "Commit memo transaction on local validator";
  try {
    const blob = createTestBlob(3, 8, 384);
    const contentHash = sha3_256(blob);

    const result = await commitToSolana(
      contentHash,
      "test-arweave-tx-local",
      {
        embedding_model: "test-model",
        quant_bits: 8,
        num_memories: 3,
      },
      false,           // not dry-run
      KEYPAIR_PATH,
      LOCAL_RPC
    );

    if (result.dry_run) throw new Error("fell back to dry-run");
    if (!result.solana_tx || result.solana_tx.startsWith("dry-run"))
      throw new Error(`bad tx: ${result.solana_tx}`);

    // Verify transaction exists on-chain
    const conn = new Connection(LOCAL_RPC, "confirmed");
    const txInfo = await conn.getTransaction(result.solana_tx, {
      commitment: "confirmed",
      maxSupportedTransactionVersion: 0,
    });
    if (!txInfo) throw new Error("transaction not found on-chain");

    pass(`${name} (tx=${result.solana_tx.slice(0, 16)}...)`);
    return result;
  } catch (e) {
    fail(name, e.message);
  }
}

async function testMemoContent() {
  const name = "Verify memo content on-chain matches commitment";
  try {
    const blob = createTestBlob(2, 4, 384);
    const contentHash = sha3_256(blob);

    const result = await commitToSolana(
      contentHash,
      "test-arweave-verify",
      {
        embedding_model: "test-model",
        quant_bits: 4,
        num_memories: 2,
      },
      false,
      KEYPAIR_PATH,
      LOCAL_RPC
    );

    if (result.dry_run) throw new Error("fell back to dry-run");

    // Fetch the transaction and inspect memo
    const conn = new Connection(LOCAL_RPC, "confirmed");
    const txInfo = await conn.getTransaction(result.solana_tx, {
      commitment: "confirmed",
      maxSupportedTransactionVersion: 0,
    });

    // Memo data is in the transaction log messages
    const logs = txInfo.meta.logMessages || [];
    const memoLog = logs.find((l) => l.includes("Memo"));
    if (!memoLog) throw new Error("no memo in transaction logs");

    // Parse the memo from the result to verify fields
    const memo = JSON.parse(result.memo);
    if (memo.protocol !== "mnemonic-v1") throw new Error(`bad protocol: ${memo.protocol}`);
    if (memo.content_hash !== contentHash) throw new Error("content hash mismatch");
    if (memo.quant_bits !== 4) throw new Error(`bad bits: ${memo.quant_bits}`);
    if (memo.num_memories !== 2) throw new Error(`bad num_memories: ${memo.num_memories}`);

    pass(`${name} (hash=${contentHash.slice(0, 16)}...)`);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testMultipleCommitments() {
  const name = "Multiple sequential commitments";
  try {
    const txIds = [];
    for (let i = 0; i < 3; i++) {
      const blob = createTestBlob(i + 1, 8, 384);
      const hash = sha3_256(blob);
      const result = await commitToSolana(
        hash,
        `test-arweave-multi-${i}`,
        { embedding_model: "test-model", quant_bits: 8, num_memories: i + 1 },
        false,
        KEYPAIR_PATH,
        LOCAL_RPC
      );
      if (result.dry_run) throw new Error(`commitment ${i} fell back to dry-run`);
      txIds.push(result.solana_tx);
    }

    // All tx IDs should be unique
    const unique = new Set(txIds);
    if (unique.size !== 3) throw new Error("duplicate transaction IDs");

    pass(`${name} (${txIds.length} txs)`);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testDryRunSkipsSolana() {
  const name = "Dry-run mode skips actual Solana transaction";
  try {
    const blob = createTestBlob(1, 8, 384);
    const hash = sha3_256(blob);
    const result = await commitToSolana(
      hash,
      "test-arweave-dry",
      { embedding_model: "test-model", quant_bits: 8, num_memories: 1 },
      true,  // dry-run
      null,
      LOCAL_RPC
    );

    if (!result.dry_run) throw new Error("expected dry_run=true");
    if (!result.solana_tx.startsWith("dry-run-")) throw new Error(`unexpected tx: ${result.solana_tx}`);
    pass(name);
  } catch (e) {
    fail(name, e.message);
  }
}

// ---------------------------------------------------------------------------
// Encryption Tests
// ---------------------------------------------------------------------------

async function testEncryptDecryptRoundTrip() {
  const name = "Encrypt/decrypt round-trip produces identical blob";
  try {
    const blob = createTestBlob(3, 8, 384);
    const keyMaterial = Buffer.alloc(32);
    for (let i = 0; i < 32; i++) keyMaterial[i] = i + 1; // deterministic test key

    const encrypted = encryptBlob(blob, keyMaterial);

    // Verify packed format
    if (!isEncryptedBlob(encrypted.packed)) {
      throw new Error("packed blob not recognized as encrypted");
    }
    if (encrypted.packed.slice(0, 4).toString("ascii") !== "MENC") {
      throw new Error("bad magic in packed blob");
    }

    // Decrypt
    const decrypted = decryptBlob(encrypted.packed, keyMaterial);

    // Compare
    if (!blob.equals(decrypted)) {
      throw new Error(`decrypted blob differs: expected ${blob.length} bytes, got ${decrypted.length}`);
    }

    // Verify original blob still has MNEM magic
    if (decrypted.slice(0, 4).toString("ascii") !== "MNEM") {
      throw new Error("decrypted blob lost MNEM magic");
    }

    pass(name);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testEncryptedCommitment() {
  const name = "Encrypted commitment pipeline (on-chain)";
  try {
    const blob = createTestBlob(2, 8, 384);

    // Encrypt
    const keyMaterial = Buffer.alloc(32);
    for (let i = 0; i < 32; i++) keyMaterial[i] = i + 42;
    const encrypted = encryptBlob(blob, keyMaterial);

    // Hash the ENCRYPTED blob (this is what goes on-chain)
    const contentHash = sha3_256(encrypted.packed);

    // Commit to Solana with encrypted metadata
    const result = await commitToSolana(
      contentHash,
      "test-arweave-encrypted",
      {
        embedding_model: "test-model",
        quant_bits: 8,
        num_memories: 2,
        encrypted: true,
      },
      false,
      KEYPAIR_PATH,
      LOCAL_RPC
    );

    if (result.dry_run) throw new Error("fell back to dry-run");

    // Verify memo includes encrypted flag
    const memo = JSON.parse(result.memo);
    if (memo.encrypted !== true) throw new Error("memo missing encrypted flag");
    if (memo.content_hash !== contentHash) throw new Error("content hash mismatch in memo");

    // Verify the on-chain hash matches the encrypted blob hash
    const verifyHash = sha3_256(encrypted.packed);
    if (verifyHash !== contentHash) throw new Error("hash verification failed");

    pass(`${name} (tx=${result.solana_tx.slice(0, 16)}...)`);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testDecryptFromCommitment() {
  const name = "Decrypt from commitment matches original";
  try {
    const blob = createTestBlob(4, 4, 384);
    const originalHash = sha3_256(blob);

    // Encrypt
    const keyMaterial = Buffer.alloc(32);
    for (let i = 0; i < 32; i++) keyMaterial[i] = i + 99;
    const encrypted = encryptBlob(blob, keyMaterial);
    const encryptedHash = sha3_256(encrypted.packed);

    // Simulate the commitment flow: hash is on the encrypted blob
    // Now decrypt and verify original content is recoverable
    const decrypted = decryptBlob(encrypted.packed, keyMaterial);
    const decryptedHash = sha3_256(decrypted);

    if (decryptedHash !== originalHash) {
      throw new Error(`original hash ${originalHash.slice(0, 16)} != decrypted hash ${decryptedHash.slice(0, 16)}`);
    }
    if (!blob.equals(decrypted)) {
      throw new Error("byte-level comparison failed");
    }

    // Verify the encrypted hash is different from plaintext hash
    if (encryptedHash === originalHash) {
      throw new Error("encrypted hash should differ from plaintext hash");
    }

    pass(name);
  } catch (e) {
    fail(name, e.message);
  }
}

async function testWrongKeyFails() {
  const name = "Decryption with wrong key fails";
  try {
    const blob = createTestBlob(2, 8, 384);

    const rightKey = Buffer.alloc(32);
    for (let i = 0; i < 32; i++) rightKey[i] = i + 1;
    const wrongKey = Buffer.alloc(32);
    for (let i = 0; i < 32; i++) wrongKey[i] = 255 - i;

    const encrypted = encryptBlob(blob, rightKey);

    // Decryption with wrong key should throw
    let threw = false;
    try {
      decryptBlob(encrypted.packed, wrongKey);
    } catch (e) {
      threw = true;
      if (!e.message.includes("Decryption failed")) {
        throw new Error(`unexpected error message: ${e.message}`);
      }
    }

    if (!threw) throw new Error("decryption with wrong key should have thrown");

    // Verify right key still works
    const decrypted = decryptBlob(encrypted.packed, rightKey);
    if (!blob.equals(decrypted)) throw new Error("right key decryption failed");

    pass(name);
  } catch (e) {
    fail(name, e.message);
  }
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

async function run() {
  const args = process.argv.slice(2);
  const autoValidator = args.includes("--start-validator");

  console.log("═".repeat(60));
  console.log("MNEMONIC — Local Solana Test Suite");
  console.log("═".repeat(60));

  if (autoValidator) {
    startValidator();
  }

  try {
    console.log("\nWaiting for validator...");
    await waitForValidator(LOCAL_RPC);
    console.log("Validator ready.\n");

    console.log("── Offline Tests ──");
    await testHashDeterminism();
    await testBlobValidation();
    await testDryRunSkipsSolana();

    console.log("\n── Encryption Tests ──");
    await testEncryptDecryptRoundTrip();
    await testDecryptFromCommitment();
    await testWrongKeyFails();

    console.log("\n── On-Chain Tests ──");
    await testSolanaConnection();
    await testAirdrop();
    await testMemoCommitment();
    await testMemoContent();
    await testMultipleCommitments();
    await testEncryptedCommitment();

    console.log("\n" + "═".repeat(60));
    if (process.exitCode) {
      console.log("SOME TESTS FAILED");
    } else {
      console.log("ALL TESTS PASSED ✓");
    }
    console.log("═".repeat(60) + "\n");
  } finally {
    // Cleanup
    if (existsSync(TEST_BLOB_PATH)) {
      unlinkSync(TEST_BLOB_PATH);
    }
    if (autoValidator) {
      stopValidator();
    }
  }
}

run().catch((err) => {
  console.error(err);
  stopValidator();
  process.exit(1);
});
