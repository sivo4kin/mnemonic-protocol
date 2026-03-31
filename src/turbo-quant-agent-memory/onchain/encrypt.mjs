/**
 * Mnemonic — Encryption Module
 *
 * AES-256-GCM encryption for memory blobs, using only Node.js built-in crypto.
 * Key derivation via HKDF (from Solana keypair bytes) or PBKDF2 (from passphrase).
 *
 * Encrypted blob format (self-contained):
 *   "MENC" (4 bytes magic)
 *   version (1 byte, currently 0x01)
 *   iv      (12 bytes)
 *   salt    (16 bytes)
 *   tag     (16 bytes, AES-GCM auth tag)
 *   ciphertext (remaining bytes)
 *
 * Total overhead: 4 + 1 + 12 + 16 + 16 = 49 bytes
 */

import { createCipheriv, createDecipheriv, randomBytes, hkdfSync, pbkdf2Sync } from "crypto";

const MAGIC = Buffer.from("MENC", "ascii");
const VERSION = 0x01;
const IV_LEN = 12;
const SALT_LEN = 16;
const TAG_LEN = 16;
const HEADER_LEN = MAGIC.length + 1 + IV_LEN + SALT_LEN + TAG_LEN; // 49

// ---------------------------------------------------------------------------
// Key derivation
// ---------------------------------------------------------------------------

/**
 * Derive a 256-bit encryption key from raw key material (e.g. Solana secret key bytes).
 * Uses HKDF with SHA-256.
 */
function deriveKey(keyMaterial, salt) {
  // keyMaterial: Buffer (e.g. first 32 bytes of Solana secret key)
  // salt: Buffer (16 bytes, random per encryption)
  const info = Buffer.from("mnemonic-v1-blob-encryption", "utf-8");
  const derived = hkdfSync("sha256", keyMaterial, salt, info, 32);
  return Buffer.from(derived);
}

/**
 * Derive a 256-bit encryption key from a passphrase string.
 * Uses PBKDF2 with SHA-256, 100k iterations.
 */
function deriveKeyFromPassphrase(passphrase, salt) {
  return pbkdf2Sync(passphrase, salt, 100_000, 32, "sha256");
}

// ---------------------------------------------------------------------------
// Encrypt / Decrypt
// ---------------------------------------------------------------------------

/**
 * Encrypt a plaintext blob with AES-256-GCM.
 *
 * @param {Buffer} blob - The plaintext blob to encrypt
 * @param {Buffer} keyMaterial - Raw key material (32 bytes from Solana keypair, or arbitrary bytes)
 * @returns {{ ciphertext: Buffer, iv: Buffer, salt: Buffer, tag: Buffer, packed: Buffer }}
 */
function encryptBlob(blob, keyMaterial) {
  const salt = randomBytes(SALT_LEN);
  const key = deriveKey(keyMaterial, salt);
  const iv = randomBytes(IV_LEN);

  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([cipher.update(blob), cipher.final()]);
  const tag = cipher.getAuthTag();

  // Pack into self-contained format
  const packed = Buffer.concat([
    MAGIC,
    Buffer.from([VERSION]),
    iv,
    salt,
    tag,
    encrypted,
  ]);

  return { ciphertext: encrypted, iv, salt, tag, packed };
}

/**
 * Decrypt an encrypted blob produced by encryptBlob.
 *
 * @param {Buffer} packed - The self-contained encrypted blob (with MENC header)
 * @param {Buffer} keyMaterial - Same key material used for encryption
 * @returns {Buffer} The decrypted plaintext
 */
function decryptBlob(packed, keyMaterial) {
  if (packed.length < HEADER_LEN) {
    throw new Error(`Encrypted blob too short: ${packed.length} bytes (minimum ${HEADER_LEN})`);
  }

  // Parse header
  const magic = packed.slice(0, 4);
  if (!magic.equals(MAGIC)) {
    throw new Error(`Bad magic: expected "MENC", got "${magic.toString("ascii")}"`);
  }

  const version = packed[4];
  if (version !== VERSION) {
    throw new Error(`Unsupported encryption version: ${version}`);
  }

  let offset = 5;
  const iv = packed.slice(offset, offset + IV_LEN);
  offset += IV_LEN;
  const salt = packed.slice(offset, offset + SALT_LEN);
  offset += SALT_LEN;
  const tag = packed.slice(offset, offset + TAG_LEN);
  offset += TAG_LEN;
  const ciphertext = packed.slice(offset);

  // Derive same key
  const key = deriveKey(keyMaterial, salt);

  // Decrypt
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);

  try {
    const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    return decrypted;
  } catch (err) {
    throw new Error(`Decryption failed (wrong key or corrupted data): ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Utility: check if a buffer is an encrypted Mnemonic blob
// ---------------------------------------------------------------------------

function isEncryptedBlob(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < HEADER_LEN) return false;
  return buf.slice(0, 4).equals(MAGIC) && buf[4] === VERSION;
}

export {
  encryptBlob,
  decryptBlob,
  isEncryptedBlob,
  deriveKey,
  deriveKeyFromPassphrase,
  HEADER_LEN,
  MAGIC,
  VERSION,
};
