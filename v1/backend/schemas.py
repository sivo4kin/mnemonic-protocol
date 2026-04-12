"""Pydantic request/response models for the V1 API."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


# --- Envelope ---

class ApiResponse(BaseModel):
    ok: bool = True
    data: Any = None
    error: Optional[dict] = None


# --- Auth ---

class AuthUser(BaseModel):
    user_id: str
    display_name: str


# --- Workspace ---

class CreateWorkspace(BaseModel):
    name: str
    description: str = ""
    provider: str = ""
    model: str = ""


class UpdateWorkspace(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class WorkspaceOut(BaseModel):
    workspace_id: str
    name: str
    description: str
    status: str
    current_provider: str
    current_model: str
    created_at: str
    updated_at: str


# --- Session ---

class CreateSession(BaseModel):
    title: Optional[str] = None


class UpdateSession(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


class SessionOut(BaseModel):
    session_id: str
    workspace_id: str
    title: Optional[str]
    status: str
    started_at: str
    ended_at: Optional[str]
    created_at: str
    updated_at: str


# --- Message ---

class SendMessage(BaseModel):
    content: str
    top_k_memories: int = 10


class MessageOut(BaseModel):
    message_id: str
    workspace_id: str
    session_id: str
    role: str
    content: str
    provider_used: Optional[str]
    model_used: Optional[str]
    created_at: str


class MemoryContextItem(BaseModel):
    memory_id: str
    memory_type: str
    title: Optional[str]
    content: str
    relevance_score: float


class AskResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    memory_context: list[MemoryContextItem]


# --- Memory ---

class CreateMemory(BaseModel):
    memory_type: str = "finding"
    title: Optional[str] = None
    content: str
    tags: list[str] = []
    source_session_id: Optional[str] = None
    source_message_id: Optional[str] = None


class UpdateMemory(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    memory_type: Optional[str] = None
    tags: Optional[list[str]] = None
    is_pinned: Optional[bool] = None


class MemoryOut(BaseModel):
    memory_id: str
    workspace_id: str
    source_session_id: Optional[str]
    source_message_id: Optional[str]
    memory_type: str
    title: Optional[str]
    content: str
    tags: list[str]
    is_pinned: bool
    created_at: str
    updated_at: str


# --- Provider ---

class SwitchProvider(BaseModel):
    provider: str
    model: str


class ProviderBindingOut(BaseModel):
    provider: str
    model: str
    status: str
    available_providers: list[dict]


# --- Source context ---

class CreateNote(BaseModel):
    display_name: Optional[str] = None
    content: str


class CreateUrlSource(BaseModel):
    url: str
    display_name: Optional[str] = None
    content: Optional[str] = None


class SourceOut(BaseModel):
    source_id: str
    workspace_id: str
    source_type: str
    display_name: Optional[str]
    content: str
    created_at: str


# --- Stats ---

class WorkspaceStats(BaseModel):
    memory_count: int
    session_count: int
    message_count: int
    source_count: int
    recent_memories: list[MemoryOut]
    open_questions: list[MemoryOut]
