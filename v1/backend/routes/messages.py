"""Message routes — includes the ask flow."""
from __future__ import annotations

from fastapi import APIRouter

from ..db import get_db
from ..schemas import ApiResponse, SendMessage
from ..services import ask as ask_svc

router = APIRouter(
    prefix="/workspaces/{workspace_id}/sessions/{session_id}/messages",
    tags=["messages"],
)


@router.get("")
async def list_messages(workspace_id: str, session_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM messages WHERE session_id = ?
               ORDER BY created_at ASC""",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        await db.close()


@router.post("")
async def send_message(workspace_id: str, session_id: str, body: SendMessage):
    db = await get_db()
    try:
        result = await ask_svc.ask(
            db, workspace_id, session_id, body.content, body.top_k_memories,
        )
        return ApiResponse(data=result)
    except ValueError as e:
        return ApiResponse(ok=False, error={"code": "VALIDATION_ERROR", "message": str(e)})
    except Exception as e:
        return ApiResponse(ok=False, error={"code": "INTERNAL_ERROR", "message": str(e)})
    finally:
        await db.close()
