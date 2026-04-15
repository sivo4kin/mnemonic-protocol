"""Session routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from ..db import get_db
from ..schemas import ApiResponse, CreateSession, UpdateSession

router = APIRouter(prefix="/workspaces/{workspace_id}/sessions", tags=["sessions"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_sessions(workspace_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        await db.close()


@router.post("")
async def create_session(workspace_id: str, body: CreateSession):
    db = await get_db()
    try:
        session_id = str(uuid.uuid4())
        now = _now()
        await db.execute(
            """INSERT INTO sessions
               (session_id, workspace_id, title, status, started_at, created_at, updated_at)
               VALUES (?, ?, ?, 'active', ?, ?, ?)""",
            (session_id, workspace_id, body.title, now, now, now),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        return ApiResponse(data=dict(row))
    finally:
        await db.close()


@router.get("/{session_id}")
async def get_session(workspace_id: str, session_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            return ApiResponse(ok=False, error={"code": "NOT_FOUND", "message": "Session not found"})
        return ApiResponse(data=dict(row))
    finally:
        await db.close()


@router.patch("/{session_id}")
async def update_session(workspace_id: str, session_id: str, body: UpdateSession):
    db = await get_db()
    try:
        sets, params = [], []
        if body.title is not None:
            sets.append("title = ?")
            params.append(body.title)
        if body.status is not None:
            sets.append("status = ?")
            params.append(body.status)
            if body.status == "closed":
                sets.append("ended_at = ?")
                params.append(_now())
        if not sets:
            return await get_session(workspace_id, session_id)

        sets.append("updated_at = ?")
        params.append(_now())
        params.append(session_id)
        await db.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = ?", params)
        await db.commit()

        cursor = await db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        return ApiResponse(data=dict(row))
    finally:
        await db.close()
