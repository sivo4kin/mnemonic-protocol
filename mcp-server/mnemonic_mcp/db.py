"""SQLite database for local attestation index."""
from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

from .config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attestations (
    attestation_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    solana_tx TEXT NOT NULL,
    arweave_tx TEXT NOT NULL,
    signer_pubkey TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attestation_embeddings (
    attestation_id TEXT PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY (attestation_id) REFERENCES attestations(attestation_id)
);

CREATE INDEX IF NOT EXISTS idx_attestations_signer ON attestations(signer_pubkey);
CREATE INDEX IF NOT EXISTS idx_attestations_hash ON attestations(content_hash);
"""


def _db_path() -> str:
    p = Path(config.DATABASE_PATH).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(_db_path())
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    db = get_db()
    db.executescript(_SCHEMA)
    db.commit()
    db.close()


def save_attestation(
    attestation_id: str,
    content: str,
    content_hash: str,
    tags: list[str],
    solana_tx: str,
    arweave_tx: str,
    signer_pubkey: str,
    created_at: str,
    embedding: list[float],
    embedding_model: str,
) -> None:
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO attestations
           (attestation_id, content, content_hash, tags, solana_tx, arweave_tx, signer_pubkey, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (attestation_id, content, content_hash, json.dumps(tags),
         solana_tx, arweave_tx, signer_pubkey, created_at),
    )
    emb_blob = struct.pack(f"{len(embedding)}f", *embedding)
    db.execute(
        """INSERT OR REPLACE INTO attestation_embeddings
           (attestation_id, embedding_model, embedding_dim, embedding)
           VALUES (?, ?, ?, ?)""",
        (attestation_id, embedding_model, len(embedding), emb_blob),
    )
    db.commit()
    db.close()


def search_attestations(query_embedding: list[float], signer_pubkey: str, limit: int = 5) -> list[dict]:
    """Cosine similarity search over attested memories."""
    import numpy as np
    query_np = np.array(query_embedding, dtype=np.float32)
    qnorm = np.linalg.norm(query_np)
    if qnorm > 0:
        query_np = query_np / qnorm

    db = get_db()
    cursor = db.execute(
        """SELECT a.*, ae.embedding FROM attestations a
           JOIN attestation_embeddings ae ON a.attestation_id = ae.attestation_id
           WHERE a.signer_pubkey = ?""",
        (signer_pubkey,),
    )
    rows = cursor.fetchall()
    db.close()

    scored = []
    for row in rows:
        emb_blob = bytes(row["embedding"])
        n = len(emb_blob) // 4
        emb = np.array(struct.unpack(f"{n}f", emb_blob), dtype=np.float32)
        enorm = np.linalg.norm(emb)
        if enorm > 0:
            emb = emb / enorm
        score = float(np.dot(query_np, emb))
        scored.append({
            "attestation_id": row["attestation_id"],
            "content": row["content"],
            "content_hash": row["content_hash"],
            "tags": json.loads(row["tags"]),
            "solana_tx": row["solana_tx"],
            "arweave_tx": row["arweave_tx"],
            "created_at": row["created_at"],
            "relevance_score": round(score, 4),
        })

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:limit]


def count_attestations(signer_pubkey: str) -> int:
    db = get_db()
    cursor = db.execute(
        "SELECT COUNT(*) as c FROM attestations WHERE signer_pubkey = ?",
        (signer_pubkey,),
    )
    count = cursor.fetchone()["c"]
    db.close()
    return count
