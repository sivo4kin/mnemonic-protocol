"""Implementation of the 5 Mnemonic MCP tools."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from solders.keypair import Keypair

from . import db, embed
from .identity import (
    pubkey_base58, did_sol, did_key, sign_message, load_or_create_keypair,
)
from .solana_client import SolanaClient
from .arweave_client import ArweaveClient
from .config import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Tool 1: mnemonic_whoami
# ---------------------------------------------------------------------------

async def whoami(keypair: Keypair) -> dict:
    """Return the agent's cryptographic identity."""
    pubkey = pubkey_base58(keypair)
    count = db.count_attestations(pubkey)
    return {
        "public_key": pubkey,
        "did_sol": did_sol(keypair),
        "did_key": did_key(keypair),
        "attestation_count": count,
        "keypair_path": config.MNEMONIC_KEYPAIR_PATH,
    }


# ---------------------------------------------------------------------------
# Tool 2: mnemonic_sign_memory
# ---------------------------------------------------------------------------

async def sign_memory(
    keypair: Keypair,
    content: str,
    tags: list[str] | None = None,
) -> dict:
    """Create a verifiable memory attestation.

    Pipeline: embed → hash → arweave → solana SPL Memo → local index.
    """
    tags = tags or []
    pubkey = pubkey_base58(keypair)
    attestation_id = str(uuid.uuid4())
    now = _now()

    # 1. Embed content
    embedding = embed.embed_text(content)

    # 2. Canonical SHA-256 hash of content
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # 3. Write to Arweave
    arweave = ArweaveClient()
    payload = json.dumps({
        "content": content,
        "content_hash": content_hash,
        "tags": tags,
        "signer": pubkey,
        "timestamp": now,
    })
    arweave_tx = await arweave.write(payload)
    await arweave.mine()  # no-op on production

    # 4. Anchor on Solana via SPL Memo
    memo_json = json.dumps({"h": content_hash, "a": arweave_tx, "v": 1})
    solana = SolanaClient()
    solana_tx = await solana.write_memo(keypair, memo_json)

    # 5. Save to local index
    db.save_attestation(
        attestation_id=attestation_id,
        content=content,
        content_hash=content_hash,
        tags=tags,
        solana_tx=solana_tx,
        arweave_tx=arweave_tx,
        signer_pubkey=pubkey,
        created_at=now,
        embedding=embedding,
        embedding_model=config.EMBED_MODEL,
    )

    return {
        "attestation_id": attestation_id,
        "content_hash": content_hash,
        "solana_tx": solana_tx,
        "arweave_tx": arweave_tx,
        "signer": pubkey,
        "did_sol": did_sol(keypair),
        "timestamp": now,
    }


# ---------------------------------------------------------------------------
# Tool 3: mnemonic_verify
# ---------------------------------------------------------------------------

async def verify(
    keypair: Keypair,
    solana_tx: str | None = None,
    arweave_tx: str | None = None,
) -> dict:
    """Verify a memory attestation by recomputing the hash."""
    if not solana_tx and not arweave_tx:
        return {"status": "error", "message": "Provide solana_tx or arweave_tx"}

    solana = SolanaClient()
    arweave = ArweaveClient()

    # Step 1: Get the anchor from Solana
    expected_hash = None
    expected_arweave_tx = None

    if solana_tx:
        memo = await solana.read_memo(solana_tx)
        if not memo:
            return {"status": "anchor_not_found", "solana_tx": solana_tx}
        expected_hash = memo.get("h")
        expected_arweave_tx = memo.get("a")
        if not arweave_tx:
            arweave_tx = expected_arweave_tx

    # Step 2: Fetch content from Arweave
    try:
        raw_bytes = await arweave.read(arweave_tx)
    except FileNotFoundError:
        return {"status": "arweave_not_found", "arweave_tx": arweave_tx}

    # Step 3: Parse and recompute hash
    try:
        payload = json.loads(raw_bytes)
        content = payload.get("content", "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        content = raw_bytes.decode("utf-8", errors="replace")

    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Step 4: Compare
    if expected_hash and actual_hash == expected_hash:
        return {
            "status": "verified",
            "content_hash": actual_hash,
            "solana_tx": solana_tx or "",
            "arweave_tx": arweave_tx,
            "signer": payload.get("signer", ""),
            "timestamp": payload.get("timestamp", ""),
            "content_preview": content[:200],
        }
    elif expected_hash:
        return {
            "status": "tampered",
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "solana_tx": solana_tx or "",
            "arweave_tx": arweave_tx,
        }
    else:
        # No Solana anchor to compare — return hash only
        return {
            "status": "hash_computed",
            "content_hash": actual_hash,
            "arweave_tx": arweave_tx,
            "content_preview": content[:200],
        }


# ---------------------------------------------------------------------------
# Tool 4: mnemonic_prove_identity
# ---------------------------------------------------------------------------

async def prove_identity(keypair: Keypair, challenge: str) -> dict:
    """Sign a challenge to prove control of the identity."""
    challenge_bytes = challenge.encode("utf-8")
    signature = sign_message(keypair, challenge_bytes)

    return {
        "public_key": pubkey_base58(keypair),
        "did_sol": did_sol(keypair),
        "challenge": challenge,
        "signature": signature.hex(),
        "algorithm": "Ed25519",
    }


# ---------------------------------------------------------------------------
# Tool 5: mnemonic_recall
# ---------------------------------------------------------------------------

async def recall(keypair: Keypair, query: str, limit: int = 5) -> dict:
    """Semantic search over the agent's attested memory history."""
    pubkey = pubkey_base58(keypair)
    query_embedding = embed.embed_text(query)
    results = db.search_attestations(query_embedding, pubkey, limit=limit)

    return {
        "query": query,
        "results": results,
        "total_attestations": db.count_attestations(pubkey),
    }
