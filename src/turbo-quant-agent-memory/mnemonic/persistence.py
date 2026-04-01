from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .embedders import OpenAIEmbeddingProvider
from .indexer import MemoryIndexer
from .math_utils import normalize
from .models import EmbeddingRecord, MemoryItem, QuantizedRecord
from .quantizer import CalibratedScalarQuantizer
from .store import MemoryStore


def load_jsonl(path: Path) -> List[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def ingest_memory_jsonl(indexer: MemoryIndexer, path: Path) -> None:
    rows = load_jsonl(path)
    # Use batch embedding when available (OpenAI provider) to avoid per-item API calls
    if isinstance(indexer.embedder, OpenAIEmbeddingProvider) and rows:
        texts = [r["content"] for r in rows]
        print(f"[ingest] batch-embedding {len(texts)} items ...")
        embeddings = indexer.embedder.embed_batch(texts)
        for row, embedding in zip(rows, embeddings):
            memory_id = row["memory_id"]
            content = row["content"]
            memory_type = row.get("memory_type", "episodic")
            importance_score = float(row.get("importance_score", 0.0))
            tags = row.get("tags", [])
            item = MemoryItem(memory_id, content, memory_type, importance_score, tags)
            indexer.store.put_item(item)
            normalized, norm = normalize(embedding)
            indexer.store.put_embedding(EmbeddingRecord(
                memory_id=memory_id,
                embedding_model=indexer.embedder.model_name,
                embedding_dim=len(embedding),
                embedding_f32=embedding,
                embedding_norm=norm,
                normalized_f32=normalized,
            ))
    else:
        for row in rows:
            memory_id = row["memory_id"]
            content = row["content"]
            memory_type = row.get("memory_type", "episodic")
            importance_score = float(row.get("importance_score", 0.0))
            tags = row.get("tags", [])
            indexer.ingest_memory(memory_id, content, memory_type=memory_type, importance_score=importance_score, tags=tags)
    indexer.rebuild_quantized_index()


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    memory_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    importance_score REAL NOT NULL,
    tags TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
    memory_id TEXT PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    embedding_f32 BLOB NOT NULL,
    embedding_norm REAL NOT NULL,
    normalized_f32 BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS quantized (
    memory_id TEXT PRIMARY KEY,
    quant_bits INTEGER NOT NULL,
    quant_scheme TEXT NOT NULL,
    packed_codes BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    saturation_rate REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quantizer_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bits INTEGER NOT NULL,
    alphas BLOB NOT NULL,
    steps BLOB NOT NULL
);
"""


def save_to_sqlite(store: MemoryStore, quantizer: CalibratedScalarQuantizer, path: Path) -> None:
    """Persist the full memory store and quantizer state to a SQLite database.

    Stores raw text, full-precision embeddings, quantized codes, and the
    calibrated quantizer parameters (alphas + steps). A subsequent
    load_from_sqlite call restores an identical in-memory state without
    re-embedding anything.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SQLITE_SCHEMA)
        cur = conn.cursor()
        for mid, item in store.items.items():
            cur.execute(
                "INSERT OR REPLACE INTO memory_items VALUES (?, ?, ?, ?, ?)",
                (item.memory_id, item.content, item.memory_type, item.importance_score, json.dumps(item.tags)),
            )
        for mid, emb in store.embeddings.items():
            cur.execute(
                "INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?, ?, ?, ?)",
                (
                    emb.memory_id,
                    emb.embedding_model,
                    emb.embedding_dim,
                    _floats_to_blob(emb.embedding_f32),
                    emb.embedding_norm,
                    _floats_to_blob(emb.normalized_f32),
                ),
            )
        for mid, qrec in store.quantized.items():
            cur.execute(
                "INSERT OR REPLACE INTO quantized VALUES (?, ?, ?, ?, ?, ?)",
                (qrec.memory_id, qrec.quant_bits, qrec.quant_scheme, qrec.packed_codes, qrec.embedding_dim, qrec.saturation_rate),
            )
        if quantizer.is_fit():
            assert quantizer.alphas is not None and quantizer.steps is not None
            cur.execute(
                "INSERT OR REPLACE INTO quantizer_state VALUES (1, ?, ?, ?)",
                (quantizer.bits, _floats_to_blob(quantizer.alphas), _floats_to_blob(quantizer.steps)),
            )
        conn.commit()
    finally:
        conn.close()


def load_from_sqlite(path: Path) -> Tuple[MemoryStore, CalibratedScalarQuantizer]:
    """Restore a MemoryStore and CalibratedScalarQuantizer from a SQLite database.

    No re-embedding required — all embeddings and quantized codes are stored.
    The restored state is identical to what was saved.
    """
    conn = sqlite3.connect(str(path))
    store = MemoryStore()
    quantizer: Optional[CalibratedScalarQuantizer] = None
    try:
        for row in conn.execute("SELECT memory_id, content, memory_type, importance_score, tags FROM memory_items"):
            store.put_item(MemoryItem(row[0], row[1], row[2], row[3], json.loads(row[4])))
        for row in conn.execute("SELECT memory_id, embedding_model, embedding_dim, embedding_f32, embedding_norm, normalized_f32 FROM embeddings"):
            store.put_embedding(EmbeddingRecord(
                memory_id=row[0],
                embedding_model=row[1],
                embedding_dim=row[2],
                embedding_f32=_blob_to_floats(row[3]),
                embedding_norm=row[4],
                normalized_f32=_blob_to_floats(row[5]),
            ))
        for row in conn.execute("SELECT memory_id, quant_bits, quant_scheme, packed_codes, embedding_dim, saturation_rate FROM quantized"):
            store.put_quantized(QuantizedRecord(
                memory_id=row[0], quant_bits=row[1], quant_scheme=row[2],
                packed_codes=bytes(row[3]), embedding_dim=row[4], saturation_rate=row[5],
            ))
        row = conn.execute("SELECT bits, alphas, steps FROM quantizer_state WHERE id=1").fetchone()
        if row:
            q = CalibratedScalarQuantizer(bits=row[0])
            q.alphas = _blob_to_floats(row[1])
            q.steps = _blob_to_floats(row[2])
            quantizer = q
    finally:
        conn.close()
    if quantizer is None:
        quantizer = CalibratedScalarQuantizer(bits=8)
    return store, quantizer


def _floats_to_blob(values: List[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def _blob_to_floats(blob: bytes) -> List[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def snapshot_items(store: MemoryStore, path: Path) -> None:
    """Serialize raw memory items to JSONL — no embeddings, no quantized data.

    The snapshot is provider-agnostic: it contains only the original text
    payloads and metadata. Any embedding provider can restore from it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for mid in store.memory_ids():
        item = store.items[mid]
        lines.append(json.dumps({
            "memory_id": item.memory_id,
            "content": item.content,
            "memory_type": item.memory_type,
            "importance_score": item.importance_score,
            "tags": item.tags,
        }))
    path.write_text("\n".join(lines) + "\n")


def restore_from_snapshot(path: Path, indexer: MemoryIndexer) -> None:
    """Re-embed all items from a snapshot using the indexer's current embedder.

    This is the mechanism for provider switches: the snapshot holds raw text;
    calling this with a different embedder rebuilds the entire index in the new
    embedding space without losing any memory content.
    """
    ingest_memory_jsonl(indexer, path)
