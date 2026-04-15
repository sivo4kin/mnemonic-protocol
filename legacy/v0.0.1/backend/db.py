"""SQLite database initialization and helpers."""
from __future__ import annotations

import aiosqlite
from pathlib import Path

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    current_provider TEXT NOT NULL DEFAULT '',
    current_model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    provider_used TEXT,
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS memory_items (
    memory_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_session_id TEXT,
    source_message_id TEXT,
    memory_type TEXT NOT NULL DEFAULT 'finding',
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    is_pinned INTEGER NOT NULL DEFAULT 0,
    importance_score REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memory_items(memory_id)
);

CREATE TABLE IF NOT EXISTS provider_bindings (
    binding_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    switched_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE TABLE IF NOT EXISTS source_contexts (
    source_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    display_name TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_items_workspace ON memory_items(workspace_id);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_workspace ON memory_embeddings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_source_contexts_workspace ON source_contexts(workspace_id);
"""


def _db_path() -> str:
    return str(Path(settings.BASE_DIR) / settings.DATABASE_PATH)


async def init_db() -> None:
    async with aiosqlite.connect(_db_path()) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_db_path())
    db.row_factory = aiosqlite.Row
    return db
