"""Workspace CRUD routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from ..db import get_db
from ..schemas import ApiResponse, CreateWorkspace, UpdateWorkspace

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_workspaces(q: str = "", limit: int = 20, offset: int = 0):
    db = await get_db()
    try:
        if q:
            cursor = await db.execute(
                """SELECT * FROM workspaces WHERE status != 'deleted'
                   AND (name LIKE ? OR description LIKE ?)
                   ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                (f"%{q}%", f"%{q}%", limit, offset),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM workspaces WHERE status != 'deleted' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        await db.close()


@router.post("")
async def create_workspace(body: CreateWorkspace):
    db = await get_db()
    try:
        workspace_id = str(uuid.uuid4())
        now = _now()
        await db.execute(
            """INSERT INTO workspaces
               (workspace_id, owner_user_id, name, description, status,
                current_provider, current_model, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (workspace_id, "local-user", body.name, body.description,
             body.provider, body.model, now, now),
        )

        # Create initial provider binding
        if body.provider and body.model:
            await db.execute(
                """INSERT INTO provider_bindings
                   (binding_id, workspace_id, provider, model, status, switched_at)
                   VALUES (?, ?, ?, ?, 'active', ?)""",
                (str(uuid.uuid4()), workspace_id, body.provider, body.model, now),
            )

        await db.commit()

        cursor = await db.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        row = await cursor.fetchone()
        return ApiResponse(data=dict(row))
    finally:
        await db.close()


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        row = await cursor.fetchone()
        if not row:
            return ApiResponse(ok=False, error={"code": "NOT_FOUND", "message": "Workspace not found"})
        return ApiResponse(data=dict(row))
    finally:
        await db.close()


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: str, body: UpdateWorkspace):
    db = await get_db()
    try:
        sets, params = [], []
        for field in ("name", "description", "status"):
            val = getattr(body, field)
            if val is not None:
                sets.append(f"{field} = ?")
                params.append(val)
        if not sets:
            return await get_workspace(workspace_id)

        sets.append("updated_at = ?")
        params.append(_now())
        params.append(workspace_id)
        await db.execute(f"UPDATE workspaces SET {', '.join(sets)} WHERE workspace_id = ?", params)
        await db.commit()

        cursor = await db.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        row = await cursor.fetchone()
        return ApiResponse(data=dict(row))
    finally:
        await db.close()
