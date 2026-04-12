"""Memory service — save, search, embed workspace memories."""
from __future__ import annotations

import json
import struct
import uuid
from datetime import datetime, timezone

import aiosqlite
import numpy as np

from . import embed as embed_svc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _floats_to_blob(values: list[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def _blob_to_floats(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


async def save_memory(
    db: aiosqlite.Connection,
    workspace_id: str,
    content: str,
    memory_type: str = "finding",
    title: str | None = None,
    tags: list[str] | None = None,
    source_session_id: str | None = None,
    source_message_id: str | None = None,
) -> dict:
    """Save a memory item and its embedding."""
    memory_id = str(uuid.uuid4())
    now = _now()
    tags_json = json.dumps(tags or [])

    await db.execute(
        """INSERT INTO memory_items
           (memory_id, workspace_id, source_session_id, source_message_id,
            memory_type, title, content, tags, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (memory_id, workspace_id, source_session_id, source_message_id,
         memory_type, title, content, tags_json, now, now),
    )

    # Embed and store
    embedding = embed_svc.embed_text(content)
    dim = len(embedding)
    await db.execute(
        """INSERT INTO memory_embeddings
           (memory_id, workspace_id, embedding_model, embedding_dim, embedding)
           VALUES (?, ?, ?, ?, ?)""",
        (memory_id, workspace_id, embed_svc.settings.EMBED_MODEL, dim,
         _floats_to_blob(embedding)),
    )
    await db.commit()

    return {
        "memory_id": memory_id,
        "workspace_id": workspace_id,
        "source_session_id": source_session_id,
        "source_message_id": source_message_id,
        "memory_type": memory_type,
        "title": title,
        "content": content,
        "tags": tags or [],
        "is_pinned": False,
        "created_at": now,
        "updated_at": now,
    }


async def search_memories(
    db: aiosqlite.Connection,
    workspace_id: str,
    query: str,
    top_k: int = 10,
) -> list[dict]:
    """Semantic search over workspace memories using cosine similarity."""
    query_vec = embed_svc.embed_text(query)
    query_np = np.array(query_vec, dtype=np.float32)
    query_norm = np.linalg.norm(query_np)
    if query_norm > 0:
        query_np = query_np / query_norm

    # Load all embeddings for this workspace
    cursor = await db.execute(
        """SELECT me.memory_id, me.embedding, mi.memory_type, mi.title, mi.content
           FROM memory_embeddings me
           JOIN memory_items mi ON me.memory_id = mi.memory_id
           WHERE me.workspace_id = ?""",
        (workspace_id,),
    )
    rows = await cursor.fetchall()

    scored = []
    for row in rows:
        emb = np.array(_blob_to_floats(bytes(row["embedding"])), dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        score = float(np.dot(query_np, emb))
        scored.append({
            "memory_id": row["memory_id"],
            "memory_type": row["memory_type"],
            "title": row["title"],
            "content": row["content"],
            "relevance_score": round(score, 4),
        })

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:top_k]


async def list_memories(
    db: aiosqlite.Connection,
    workspace_id: str,
    memory_type: str | None = None,
    pinned: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List memories with optional filters."""
    sql = "SELECT * FROM memory_items WHERE workspace_id = ?"
    params: list = [workspace_id]

    if memory_type:
        sql += " AND memory_type = ?"
        params.append(memory_type)
    if pinned is not None:
        sql += " AND is_pinned = ?"
        params.append(1 if pinned else 0)

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [_row_to_memory(r) for r in rows]


async def get_memory(db: aiosqlite.Connection, memory_id: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM memory_items WHERE memory_id = ?", (memory_id,))
    row = await cursor.fetchone()
    return _row_to_memory(row) if row else None


async def update_memory(db: aiosqlite.Connection, memory_id: str, updates: dict) -> dict | None:
    sets = []
    params = []
    for key in ("title", "content", "memory_type", "is_pinned"):
        if key in updates and updates[key] is not None:
            sets.append(f"{key} = ?")
            params.append(updates[key])
    if "tags" in updates and updates["tags"] is not None:
        sets.append("tags = ?")
        params.append(json.dumps(updates["tags"]))
    if not sets:
        return await get_memory(db, memory_id)

    sets.append("updated_at = ?")
    params.append(_now())
    params.append(memory_id)

    await db.execute(f"UPDATE memory_items SET {', '.join(sets)} WHERE memory_id = ?", params)

    # Re-embed if content changed
    if "content" in updates and updates["content"]:
        embedding = embed_svc.embed_text(updates["content"])
        await db.execute(
            "UPDATE memory_embeddings SET embedding = ?, embedding_dim = ? WHERE memory_id = ?",
            (_floats_to_blob(embedding), len(embedding), memory_id),
        )

    await db.commit()
    return await get_memory(db, memory_id)


def _row_to_memory(row) -> dict:
    return {
        "memory_id": row["memory_id"],
        "workspace_id": row["workspace_id"],
        "source_session_id": row["source_session_id"],
        "source_message_id": row["source_message_id"],
        "memory_type": row["memory_type"],
        "title": row["title"],
        "content": row["content"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "is_pinned": bool(row["is_pinned"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
