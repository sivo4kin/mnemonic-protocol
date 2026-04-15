/**
 * Mnemonic On-Chain Commitment
 *
 * Reads a serialized memory blob, computes SHA3-256 hash,
 * uploads to Arweave, and writes the commitment to Solana devnet.
 *
 * Usage:
 *   node commit.mjs <blob_path> [--dry-run]
 *
 * Outputs JSON with commitment details.
 */

import { readFileSync, writeFileSync, existsSync } from "fs";
import { createHash } from "crypto";
import { encryptBlob, decryptBlob, isEncryptedBlob } from "./encrypt.mjs";
import {
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  TransactionInstruction,
  SystemProgram,
  sendAndConfirmTransaction,
} from "@solana/web3.js";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const SOLANA_RPC = process.env.SOLANA_RPC_URL || "https://api.devnet.solana.com";
const ARWEAVE_GATEWAY = "https://arweave.net";
const MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr";

// ---------------------------------------------------------------------------
// Hashing
// ---------------------------------------------------------------------------

function sha3_256(data) {
  return createHash("sha3-256").update(data).digest("hex");
}

// ---------------------------------------------------------------------------
// Arweave upload (simplified — uses bundlr/turbo or direct tx)
// ---------------------------------------------------------------------------

async function uploadToArweave(blob, dryRun = false) {
  if (dryRun) {
    // Simulate: return content-addressed ID based on hash
    const hash = sha3_256(blob);
    return {
      arweave_tx: `dry-run-${hash.slice(0, 32)}`,
      arweave_url: `${ARWEAVE_GATEWAY}/dry-run-${hash.slice(0, 32)}`,
      size_bytes: blob.length,
      dry_run: true,
    };
  }

  // Real upload via Arweave HTTP API
  // For MVP, we use irys.xyz (formerly Bundlr) which has a free tier for small uploads
  try {
    const resp = await fetch("https://uploader.irys.xyz/upload", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "x-network": "arweave",
      },
      body: blob,
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Arweave upload failed (${resp.status}): ${text}`);
    }

    const result = await resp.json();
    return {
      arweave_tx: result.id,
      arweave_url: `${ARWEAVE_GATEWAY}/${result.id}`,
      size_bytes: blob.length,
      dry_run: false,
    };
  } catch (err) {
    console.warn(`Arweave upload failed: ${err.message}. Falling back to dry-run.`);
    const hash = sha3_256(blob);
    return {
      arweave_tx: `fallback-${hash.slice(0, 32)}`,
      arweave_url: null,
      size_bytes: blob.length,
      dry_run: true,
      error: err.message,
    };
  }
}

// ---------------------------------------------------------------------------
// Solana commitment (write hash as memo on devnet)
// ---------------------------------------------------------------------------

async function commitToSolana(contentHash, arweaveTx, metadata, dryRun = false, keypairPath = null, rpcUrl = null) {
  // Build the memo payload
  const memoObj = {
    protocol: "mnemonic-v1",
    content_hash: contentHash,
    arweave_tx: arweaveTx,
    embedding_model: metadata.embedding_model || "unknown",
    quant_bits: metadata.quant_bits || 8,
    num_memories: metadata.num_memories || 0,
    timestamp: new Date().toISOString(),
  };
  if (metadata.encrypted) {
    memoObj.encrypted = true;
  }
  const memo = JSON.stringify(memoObj);

  if (dryRun) {
    return {
      solana_tx: `dry-run-${contentHash.slice(0, 16)}`,
      solana_url: null,
      memo: memo,
      dry_run: true,
    };
  }

  try {
    const endpoint = rpcUrl || SOLANA_RPC;
    const connection = new Connection(endpoint, "confirmed");
    let payer;

    if (keypairPath) {
      // Load pre-funded keypair from JSON file
      const keyData = JSON.parse(readFileSync(keypairPath, "utf-8"));
      payer = Keypair.fromSecretKey(Uint8Array.from(keyData));
      console.log(`Loaded keypair: ${payer.publicKey.toBase58()}`);
    } else {
      // Generate new keypair and request airdrop
      payer = Keypair.generate();
      console.log(`Generated keypair: ${payer.publicKey.toBase58()}`);
      console.log("Requesting SOL airdrop on devnet...");

      const airdropSig = await connection.requestAirdrop(
        payer.publicKey,
        100_000_000 // 0.1 SOL (enough for a memo)
      );
      const latestBlockhash = await connection.getLatestBlockhash();
      await connection.confirmTransaction(
        { signature: airdropSig, ...latestBlockhash },
        "confirmed"
      );
      console.log("Airdrop confirmed.");
    }

    const balance = await connection.getBalance(payer.publicKey);
    console.log(`Balance: ${balance / 1e9} SOL`);

    // Create memo instruction
    const memoInstruction = new TransactionInstruction({
      keys: [{ pubkey: payer.publicKey, isSigner: true, isWritable: true }],
      programId: new PublicKey(MEMO_PROGRAM_ID),
      data: Buffer.from(memo, "utf-8"),
    });

    const transaction = new Transaction().add(memoInstruction);

    console.log("Sending commitment transaction...");
    const txSig = await sendAndConfirmTransaction(connection, transaction, [payer], {
      commitment: "confirmed",
    });

    console.log(`Commitment confirmed: ${txSig}`);
    return {
      solana_tx: txSig,
      solana_url: endpoint.includes("localhost") || endpoint.includes("127.0.0.1")
        ? `https://explorer.solana.com/tx/${txSig}?cluster=custom&customUrl=${encodeURIComponent(endpoint)}`
        : `https://explorer.solana.com/tx/${txSig}?cluster=devnet`,
      payer: payer.publicKey.toBase58(),
      memo: memo,
      dry_run: false,
    };
  } catch (err) {
    console.warn(`Solana commitment failed: ${err.message}. Falling back to dry-run.`);
    return {
      solana_tx: `fallback-${contentHash.slice(0, 16)}`,
      solana_url: null,
      memo: memo,
      dry_run: true,
      error: err.message,
    };
  }
}

// ---------------------------------------------------------------------------
// Decrypt-and-verify flow
// ---------------------------------------------------------------------------

async function decryptAndVerify(commitmentPath, keypairPath) {
  console.log(`\n${"=".repeat(60)}`);
  console.log("MNEMONIC — Decrypt & Verify");
  console.log(`${"=".repeat(60)}\n`);

  // 1. Load commitment JSON
  if (!existsSync(commitmentPath)) {
    console.error(`Commitment file not found: ${commitmentPath}`);
    process.exit(1);
  }
  const commitment = JSON.parse(readFileSync(commitmentPath, "utf-8"));
  console.log(`[1/4] COMMITMENT: loaded from ${commitmentPath}`);
  console.log(`       hash: ${commitment.content_hash}`);

  if (!commitment.encrypted) {
    console.error("Commitment is not marked as encrypted.");
    process.exit(1);
  }

  // 2. Load the encrypted blob (from local path or fetch from Arweave)
  let encryptedBlob;
  const blobPath = commitment.blob_path;
  if (blobPath && existsSync(blobPath)) {
    encryptedBlob = readFileSync(blobPath);
    console.log(`[2/4] BLOB: loaded ${encryptedBlob.length.toLocaleString()} bytes from ${blobPath}`);
  } else if (commitment.arweave && commitment.arweave.arweave_url && !commitment.arweave.dry_run) {
    console.log(`[2/4] BLOB: fetching from Arweave ${commitment.arweave.arweave_url}...`);
    const resp = await fetch(commitment.arweave.arweave_url);
    if (!resp.ok) throw new Error(`Arweave fetch failed: ${resp.status}`);
    encryptedBlob = Buffer.from(await resp.arrayBuffer());
    console.log(`       fetched ${encryptedBlob.length.toLocaleString()} bytes`);
  } else {
    console.error("Cannot locate encrypted blob (no local file or Arweave URL).");
    process.exit(1);
  }

  // 3. Verify hash of encrypted blob matches commitment
  const encryptedHash = sha3_256(encryptedBlob);
  const hashMatch = encryptedHash === commitment.content_hash;
  console.log(`[3/4] HASH VERIFY: ${hashMatch ? "PASS" : "FAIL"}`);
  console.log(`       on-chain:  ${commitment.content_hash}`);
  console.log(`       computed:  ${encryptedHash}`);

  if (!hashMatch) {
    console.error("Hash mismatch! Blob has been tampered with or is not the correct file.");
    process.exit(1);
  }

  // 4. Decrypt
  if (!keypairPath) {
    console.error("--keypair required for decryption (need the same key used for encryption)");
    process.exit(1);
  }
  const keyData = JSON.parse(readFileSync(keypairPath, "utf-8"));
  const keyMaterial = Buffer.from(Uint8Array.from(keyData).slice(0, 32));

  console.log(`[4/4] DECRYPT: decrypting with keypair...`);
  const plaintext = decryptBlob(encryptedBlob, keyMaterial);

  // Verify the decrypted blob is a valid MNEM blob
  const magic = plaintext.slice(0, 4).toString("ascii");
  if (magic !== "MNEM") {
    console.error(`Decrypted blob has invalid magic: "${magic}" (expected "MNEM")`);
    process.exit(1);
  }

  const version = plaintext.readUInt16LE(4);
  const embeddingModel = plaintext.slice(6, 38).toString("utf-8").replace(/\0+$/, "");
  const dim = plaintext.readUInt16LE(38);
  const quantBits = plaintext.readUInt8(40);
  const numMemories = plaintext.readUInt32LE(42);

  console.log(`       Decrypted MNEM blob: version=${version} model=${embeddingModel} dim=${dim} bits=${quantBits} memories=${numMemories}`);
  console.log(`       Plaintext size: ${plaintext.length.toLocaleString()} bytes`);
  console.log(`       Plaintext hash: ${sha3_256(plaintext)}`);

  console.log(`\n${"=".repeat(60)}`);
  console.log("DECRYPT & VERIFY COMPLETE");
  console.log(`${"=".repeat(60)}\n`);

  return { plaintext, commitment };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);
  const blobPath = args.find((a) => !a.startsWith("--"));
  const dryRun = args.includes("--dry-run");
  const doEncrypt = args.includes("--encrypt");
  const doDecrypt = args.includes("--decrypt");
  const keypairIdx = args.indexOf("--keypair");
  const keypairPath = keypairIdx >= 0 ? args[keypairIdx + 1] : null;
  const rpcIdx = args.indexOf("--rpc");
  const rpcUrl = rpcIdx >= 0 ? args[rpcIdx + 1] : null;

  // --- Decrypt flow ---
  if (doDecrypt) {
    const commitmentPath = blobPath; // in decrypt mode, positional arg is the .commitment.json
    if (!commitmentPath) {
      console.error("Usage: node commit.mjs <commitment.json> --decrypt --keypair <keypair.json>");
      process.exit(1);
    }
    await decryptAndVerify(commitmentPath, keypairPath);
    return;
  }

  // --- Commit flow ---
  if (!blobPath) {
    console.error("Usage: node commit.mjs <blob_path> [--dry-run] [--encrypt] [--keypair <path>] [--rpc <url>]");
    process.exit(1);
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log("MNEMONIC — On-Chain Commitment");
  console.log(`${"=".repeat(60)}\n`);

  // 1. Read blob
  let blob = readFileSync(blobPath);
  console.log(`[1/5] BLOB: ${blob.length.toLocaleString()} bytes from ${blobPath}`);

  // 2. Verify it's a valid Mnemonic blob
  const magic = blob.slice(0, 4).toString("ascii");
  if (magic !== "MNEM") {
    console.error(`Invalid blob: expected MNEM magic, got "${magic}"`);
    process.exit(1);
  }

  // Extract metadata from header
  const version = blob.readUInt16LE(4);
  const embeddingModel = blob.slice(6, 38).toString("utf-8").replace(/\0+$/, "");
  const dim = blob.readUInt16LE(38);
  const quantBits = blob.readUInt8(40);
  const numMemories = blob.readUInt32LE(42);

  console.log(`       version=${version} model=${embeddingModel} dim=${dim} bits=${quantBits} memories=${numMemories}`);

  // 2b. Encrypt if requested
  let encrypted = false;
  if (doEncrypt) {
    if (!keypairPath) {
      console.error("--encrypt requires --keypair <path> to derive encryption key");
      process.exit(1);
    }
    const keyData = JSON.parse(readFileSync(keypairPath, "utf-8"));
    const keyMaterial = Buffer.from(Uint8Array.from(keyData).slice(0, 32));

    console.log(`[2/5] ENCRYPT: encrypting blob with AES-256-GCM...`);
    const encResult = encryptBlob(blob, keyMaterial);
    console.log(`       plaintext:  ${blob.length.toLocaleString()} bytes`);
    console.log(`       ciphertext: ${encResult.packed.length.toLocaleString()} bytes (+${encResult.packed.length - blob.length} overhead)`);
    blob = encResult.packed;
    encrypted = true;
  } else {
    console.log(`[2/5] ENCRYPT: skipped (use --encrypt to enable)`);
  }

  // 3. Hash — computed on the blob that will be stored (encrypted if --encrypt)
  const contentHash = sha3_256(blob);
  console.log(`[3/5] HASH: SHA3-256 = ${contentHash}`);

  // 4. Upload to Arweave
  console.log(`[4/5] ARWEAVE: uploading${dryRun ? " (dry-run)" : ""}...`);
  const arweaveResult = await uploadToArweave(blob, dryRun);
  console.log(`       tx: ${arweaveResult.arweave_tx}`);
  if (arweaveResult.arweave_url) {
    console.log(`       url: ${arweaveResult.arweave_url}`);
  }

  // 5. Commit to Solana
  console.log(`[5/5] SOLANA: committing${dryRun ? " (dry-run)" : ""}...`);
  const solanaResult = await commitToSolana(
    contentHash,
    arweaveResult.arweave_tx,
    { embedding_model: embeddingModel, quant_bits: quantBits, num_memories: numMemories, encrypted },
    dryRun,
    keypairPath,
    rpcUrl
  );
  console.log(`       tx: ${solanaResult.solana_tx}`);
  if (solanaResult.solana_url) {
    console.log(`       url: ${solanaResult.solana_url}`);
  }

  // 6. Output
  const result = {
    blob_path: blobPath,
    blob_size_bytes: blob.length,
    content_hash: contentHash,
    encrypted,
    metadata: {
      version,
      embedding_model: embeddingModel,
      embedding_dim: dim,
      quant_bits: quantBits,
      num_memories: numMemories,
    },
    arweave: arweaveResult,
    solana: solanaResult,
    timestamp: new Date().toISOString(),
  };

  const outPath = blobPath.replace(/\.bin$/, "") + ".commitment.json";
  writeFileSync(outPath, JSON.stringify(result, null, 2));

  console.log(`\n${"=".repeat(60)}`);
  console.log(`COMMITMENT COMPLETE${dryRun ? " (dry-run)" : ""}${encrypted ? " (encrypted)" : ""}`);
  console.log(`  Hash:      ${contentHash.slice(0, 16)}...${contentHash.slice(-16)}`);
  console.log(`  Encrypted: ${encrypted}`);
  console.log(`  Arweave:   ${arweaveResult.dry_run ? "simulated" : arweaveResult.arweave_tx}`);
  console.log(`  Solana:    ${solanaResult.dry_run ? "simulated" : solanaResult.solana_tx}`);
  console.log(`  Output:    ${outPath}`);
  console.log(`${"=".repeat(60)}\n`);

  return result;
}

export { sha3_256, uploadToArweave, commitToSolana, decryptAndVerify };

// Run as CLI if invoked directly
const isMain = process.argv[1] && (
  process.argv[1].endsWith("commit.mjs") ||
  process.argv[1].endsWith("commit.js")
);
if (isMain) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
