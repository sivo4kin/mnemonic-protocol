"""Workspace stats route."""
from __future__ import annotations

import json
from fastapi import APIRouter

from ..db import get_db
from ..schemas import ApiResponse

router = APIRouter(prefix="/workspaces/{workspace_id}/stats", tags=["stats"])


@router.get("")
async def workspace_stats(workspace_id: str):
    db = await get_db()
    try:
        mem_count = (await (await db.execute(
            "SELECT COUNT(*) as c FROM memory_items WHERE workspace_id = ?", (workspace_id,)
        )).fetchone())["c"]

        sess_count = (await (await db.execute(
            "SELECT COUNT(*) as c FROM sessions WHERE workspace_id = ?", (workspace_id,)
        )).fetchone())["c"]

        msg_count = (await (await db.execute(
            "SELECT COUNT(*) as c FROM messages WHERE workspace_id = ?", (workspace_id,)
        )).fetchone())["c"]

        src_count = (await (await db.execute(
            "SELECT COUNT(*) as c FROM source_contexts WHERE workspace_id = ?", (workspace_id,)
        )).fetchone())["c"]

        # Recent memories (last 5)
        cursor = await db.execute(
            "SELECT * FROM memory_items WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 5",
            (workspace_id,),
        )
        recent = [_mem(r) for r in await cursor.fetchall()]

        # Open questions
        cursor = await db.execute(
            "SELECT * FROM memory_items WHERE workspace_id = ? AND memory_type = 'question' ORDER BY created_at DESC LIMIT 10",
            (workspace_id,),
        )
        questions = [_mem(r) for r in await cursor.fetchall()]

        return ApiResponse(data={
            "memory_count": mem_count,
            "session_count": sess_count,
            "message_count": msg_count,
            "source_count": src_count,
            "recent_memories": recent,
            "open_questions": questions,
        })
    finally:
        await db.close()


def _mem(row) -> dict:
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
