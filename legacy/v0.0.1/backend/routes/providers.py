"""Provider binding and switch routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from ..config import settings
from ..db import get_db
from ..schemas import ApiResponse, SwitchProvider

router = APIRouter(prefix="/workspaces/{workspace_id}/provider-binding", tags=["providers"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def get_provider_binding(workspace_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT current_provider, current_model FROM workspaces WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return ApiResponse(ok=False, error={"code": "NOT_FOUND", "message": "Workspace not found"})

        return ApiResponse(data={
            "provider": row["current_provider"],
            "model": row["current_model"],
            "status": "active",
            "available_providers": settings.available_providers(),
        })
    finally:
        await db.close()


@router.post("/switch")
async def switch_provider(workspace_id: str, body: SwitchProvider):
    db = await get_db()
    try:
        now = _now()
        await db.execute(
            "UPDATE workspaces SET current_provider = ?, current_model = ?, updated_at = ? WHERE workspace_id = ?",
            (body.provider, body.model, now, workspace_id),
        )
        await db.execute(
            """INSERT INTO provider_bindings
               (binding_id, workspace_id, provider, model, status, switched_at)
               VALUES (?, ?, ?, ?, 'active', ?)""",
            (str(uuid.uuid4()), workspace_id, body.provider, body.model, now),
        )
        await db.commit()

        return ApiResponse(data={
            "provider": body.provider,
            "model": body.model,
            "status": "active",
            "message": "Provider switched. Workspace memory preserved.",
        })
    finally:
        await db.close()


@router.get("/status")
async def provider_status(workspace_id: str):
    return await get_provider_binding(workspace_id)
