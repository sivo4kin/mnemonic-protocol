"""Memory routes — save, search, inspect, update."""
from __future__ import annotations

from fastapi import APIRouter

from ..db import get_db
from ..schemas import ApiResponse, CreateMemory, UpdateMemory
from ..services import memory as memory_svc

router = APIRouter(prefix="/workspaces/{workspace_id}/memories", tags=["memories"])


@router.get("")
async def list_or_search_memories(
    workspace_id: str,
    q: str = "",
    type: str = "",
    pinned: str = "",
    k: int = 20,
    limit: int = 20,
    offset: int = 0,
):
    db = await get_db()
    try:
        if q:
            results = await memory_svc.search_memories(db, workspace_id, q, top_k=k)
            return ApiResponse(data=results)
        else:
            pinned_val = None
            if pinned == "true":
                pinned_val = True
            elif pinned == "false":
                pinned_val = False
            results = await memory_svc.list_memories(
                db, workspace_id, memory_type=type or None,
                pinned=pinned_val, limit=limit, offset=offset,
            )
            return ApiResponse(data=results)
    finally:
        await db.close()


@router.post("")
async def create_memory(workspace_id: str, body: CreateMemory):
    db = await get_db()
    try:
        result = await memory_svc.save_memory(
            db, workspace_id,
            content=body.content,
            memory_type=body.memory_type,
            title=body.title,
            tags=body.tags,
            source_session_id=body.source_session_id,
            source_message_id=body.source_message_id,
        )
        return ApiResponse(data=result)
    finally:
        await db.close()


@router.get("/{memory_id}")
async def get_memory(workspace_id: str, memory_id: str):
    db = await get_db()
    try:
        result = await memory_svc.get_memory(db, memory_id)
        if not result:
            return ApiResponse(ok=False, error={"code": "NOT_FOUND", "message": "Memory not found"})
        return ApiResponse(data=result)
    finally:
        await db.close()


@router.patch("/{memory_id}")
async def update_memory(workspace_id: str, memory_id: str, body: UpdateMemory):
    db = await get_db()
    try:
        updates = body.model_dump(exclude_none=True)
        result = await memory_svc.update_memory(db, memory_id, updates)
        if not result:
            return ApiResponse(ok=False, error={"code": "NOT_FOUND", "message": "Memory not found"})
        return ApiResponse(data=result)
    finally:
        await db.close()
