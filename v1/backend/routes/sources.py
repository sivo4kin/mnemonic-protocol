"""Source context routes — pasted notes and optional URL text."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from ..db import get_db
from ..schemas import ApiResponse, CreateNote, CreateUrlSource

router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_sources(workspace_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM source_contexts WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        await db.close()


@router.post("/note")
async def add_note(workspace_id: str, body: CreateNote):
    db = await get_db()
    try:
        source_id = str(uuid.uuid4())
        now = _now()
        display_name = body.display_name or f"Note ({now[:10]})"
        await db.execute(
            """INSERT INTO source_contexts
               (source_id, workspace_id, source_type, display_name, content, created_at)
               VALUES (?, ?, 'pasted_note', ?, ?, ?)""",
            (source_id, workspace_id, display_name, body.content, now),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM source_contexts WHERE source_id = ?", (source_id,))
        row = await cursor.fetchone()
        return ApiResponse(data=dict(row))
    finally:
        await db.close()


@router.post("/url")
async def add_url_source(workspace_id: str, body: CreateUrlSource):
    db = await get_db()
    try:
        source_id = str(uuid.uuid4())
        now = _now()
        display_name = body.display_name or body.url
        content = body.content or f"[URL source: {body.url}]"
        await db.execute(
            """INSERT INTO source_contexts
               (source_id, workspace_id, source_type, display_name, content, created_at)
               VALUES (?, ?, 'url_text', ?, ?, ?)""",
            (source_id, workspace_id, display_name, content, now),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM source_contexts WHERE source_id = ?", (source_id,))
        row = await cursor.fetchone()
        return ApiResponse(data=dict(row))
    finally:
        await db.close()
