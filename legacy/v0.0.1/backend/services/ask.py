"""Ask flow orchestration — memory-aware response generation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from . import chat, memory as memory_svc


SYSTEM_PROMPT_TEMPLATE = """You are a research assistant working in a persistent workspace called "{workspace_name}".

The user has saved the following memories from prior sessions. Use them to provide informed, continuity-aware responses. Reference prior findings when relevant.

{memory_context}

If no saved memories are relevant to the current question, respond based on your own knowledge. Always be concise and useful."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_memory_context(memories: list[dict]) -> str:
    if not memories:
        return "(No saved memories yet.)"
    lines = []
    for m in memories:
        title = f" — {m['title']}" if m.get("title") else ""
        lines.append(f"- [{m['memory_type']}]{title}: {m['content'][:500]}")
    return "\n".join(lines)


async def ask(
    db: aiosqlite.Connection,
    workspace_id: str,
    session_id: str,
    user_content: str,
    top_k_memories: int = 10,
) -> dict:
    """Full ask flow: save user msg → retrieve memories → call provider → save assistant msg."""

    # Get workspace info
    cursor = await db.execute(
        "SELECT name, current_provider, current_model FROM workspaces WHERE workspace_id = ?",
        (workspace_id,),
    )
    ws = await cursor.fetchone()
    if not ws:
        raise ValueError(f"Workspace {workspace_id} not found")

    provider = ws["current_provider"]
    model = ws["current_model"]
    workspace_name = ws["name"]

    if not provider or not model:
        raise ValueError("No provider/model configured for this workspace. Set one in workspace settings.")

    # 1. Save user message
    user_msg_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO messages (message_id, workspace_id, session_id, role, content, created_at)
           VALUES (?, ?, ?, 'user', ?, ?)""",
        (user_msg_id, workspace_id, session_id, user_content, now),
    )

    # 2. Retrieve relevant memories
    memory_context = await memory_svc.search_memories(db, workspace_id, user_content, top_k=top_k_memories)

    # 3. Build system prompt with memory context
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        workspace_name=workspace_name,
        memory_context=_format_memory_context(memory_context),
    )

    # 4. Get recent conversation history for this session (last 20 messages)
    cursor = await db.execute(
        """SELECT role, content FROM messages
           WHERE session_id = ? ORDER BY created_at DESC LIMIT 20""",
        (session_id,),
    )
    history_rows = await cursor.fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]

    # 5. Call chat provider
    try:
        assistant_text = await chat.generate_response(provider, model, system_prompt, history)
    except Exception as e:
        assistant_text = f"[Error calling {provider}/{model}: {e}]"

    # 6. Save assistant message
    asst_msg_id = str(uuid.uuid4())
    asst_now = _now()
    await db.execute(
        """INSERT INTO messages
           (message_id, workspace_id, session_id, role, content, provider_used, model_used, created_at)
           VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?)""",
        (asst_msg_id, workspace_id, session_id, assistant_text, provider, model, asst_now),
    )
    await db.commit()

    user_message = {
        "message_id": user_msg_id, "workspace_id": workspace_id,
        "session_id": session_id, "role": "user", "content": user_content,
        "provider_used": None, "model_used": None, "created_at": now,
    }
    assistant_message = {
        "message_id": asst_msg_id, "workspace_id": workspace_id,
        "session_id": session_id, "role": "assistant", "content": assistant_text,
        "provider_used": provider, "model_used": model, "created_at": asst_now,
    }

    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "memory_context": memory_context,
    }
