"""Agent identity — Ed25519 keypair, did:sol, did:key derivation."""
from __future__ import annotations

import json
from pathlib import Path

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from .config import config

# Multicodec prefix for Ed25519 public key (0xed01)
_ED25519_MULTICODEC = b"\xed\x01"

# Base58btc multibase prefix
_MULTIBASE_BASE58BTC = "z"


def load_or_create_keypair() -> Keypair:
    """Load keypair from file, or generate and save a new one."""
    path = Path(config.MNEMONIC_KEYPAIR_PATH).expanduser()
    if path.exists():
        data = json.loads(path.read_text())
        return Keypair.from_bytes(bytes(data))
    # Generate new keypair
    kp = Keypair()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(bytes(kp))))
    return kp


def pubkey_base58(kp: Keypair) -> str:
    """Return base58-encoded public key."""
    return str(kp.pubkey())


def did_sol(kp: Keypair) -> str:
    """Derive did:sol identifier from keypair."""
    return f"did:sol:{kp.pubkey()}"


def did_key(kp: Keypair) -> str:
    """Derive did:key identifier from Ed25519 public key.

    Format: did:key:z<base58btc(multicodec_ed25519 + raw_pubkey)>
    """
    raw_pubkey = bytes(kp.pubkey())
    multicodec_bytes = _ED25519_MULTICODEC + raw_pubkey
    # Base58btc encode (reuse solders' Pubkey for base58, but we need raw encoding)
    import base64
    import hashlib
    encoded = _base58_encode(multicodec_bytes)
    return f"did:key:{_MULTIBASE_BASE58BTC}{encoded}"


def sign_message(kp: Keypair, message: bytes) -> bytes:
    """Sign arbitrary bytes with the agent's Ed25519 key."""
    from solders.signature import Signature
    sig = kp.sign_message(message)
    return bytes(sig)


def verify_signature(pubkey: Pubkey, message: bytes, signature: bytes) -> bool:
    """Verify an Ed25519 signature."""
    from solders.signature import Signature
    sig = Signature.from_bytes(signature)
    return sig.verify(pubkey, message)


def _base58_encode(data: bytes) -> str:
    """Base58 encode (Bitcoin alphabet)."""
    ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(data, "big")
    result = bytearray()
    while n > 0:
        n, r = divmod(n, 58)
        result.append(ALPHABET[r])
    # Leading zeros
    for byte in data:
        if byte == 0:
            result.append(ALPHABET[0])
        else:
            break
    return bytes(reversed(result)).decode("ascii")
