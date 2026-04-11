# V1_API.md — Mnemonic Frontend ↔ Backend API Contract

**Date:** 2026-04-10
**Status:** Draft — V1 (minimal UI)
**Scope:** API required to implement the minimal V1 persistent research workspace

---

## 1. Contract intent

This API exists to support one product shape:

> a minimal local-first research workspace where a user can work across sessions, save memory, inspect prior memory, and switch providers without losing project context.

V1 intentionally does **not** include:
- MCP server
- file/blob upload subsystem
- checkpoint / verification UX
- Solana anchoring

Those are deferred to **V1.1**.

---

## 2. API style

### Base URL
```text
/api/v1
```

### Content type
- `application/json` for all V1 endpoints

### Response envelope

**Success**
```json
{ "ok": true, "data": { } }
```

**Error**
```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message"
  }
}
```

### Common error codes
- `UNAUTHORIZED`
- `FORBIDDEN`
- `NOT_FOUND`
- `VALIDATION_ERROR`
- `CONFLICT`
- `INTERNAL_ERROR`

---

## 3. Auth stance for V1

### Default mode
V1 should support **local/single-user session mode**.

### Minimal auth endpoints

#### POST /auth/session
Create or resume the local session.

#### GET /auth/me
Return current session user.

#### POST /auth/logout
Invalidate local session.

---

## 4. Core resource types

### Workspace
```json
{
  "workspace_id": "uuid",
  "name": "string",
  "description": "string",
  "status": "active | archived",
  "current_provider": "string",
  "current_model": "string",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

### Session
```json
{
  "session_id": "uuid",
  "workspace_id": "uuid",
  "title": "string | null",
  "status": "active | closed",
  "started_at": "ISO 8601",
  "ended_at": "ISO 8601 | null",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

### Message
```json
{
  "message_id": "uuid",
  "workspace_id": "uuid",
  "session_id": "uuid",
  "role": "user | assistant | system",
  "content": "string",
  "provider_used": "string | null",
  "model_used": "string | null",
  "created_at": "ISO 8601"
}
```

### MemoryItem
```json
{
  "memory_id": "uuid",
  "workspace_id": "uuid",
  "source_session_id": "uuid | null",
  "source_message_id": "uuid | null",
  "memory_type": "finding | decision | question | source",
  "title": "string | null",
  "content": "string",
  "tags": ["string"],
  "is_pinned": false,
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

### SourceContext
```json
{
  "source_id": "uuid",
  "workspace_id": "uuid",
  "source_type": "pasted_note | url_text",
  "display_name": "string",
  "content": "string",
  "created_at": "ISO 8601"
}
```

---

## 5. Workspaces

### GET /workspaces
List workspaces for the current user.

**Query params**
- `q` — optional search query
- `limit` — default `20`
- `offset` — default `0`

### POST /workspaces
Create a workspace.

**Request**
```json
{
  "name": "string",
  "description": "string",
  "provider": "string",
  "model": "string"
}
```

### GET /workspaces/{workspace_id}
Return workspace detail.

### PATCH /workspaces/{workspace_id}
Update workspace metadata.

---

## 6. Sessions

### GET /workspaces/{workspace_id}/sessions
List sessions in a workspace.

### POST /workspaces/{workspace_id}/sessions
Create a new session.

### GET /workspaces/{workspace_id}/sessions/{session_id}
Return session detail.

### PATCH /workspaces/{workspace_id}/sessions/{session_id}
Update session title or status.

---

## 7. Messages / Ask flow

### GET /workspaces/{workspace_id}/sessions/{session_id}/messages
Return conversation history for a session.

### POST /workspaces/{workspace_id}/sessions/{session_id}/messages
Send a user message and get assistant output plus memory context used.

**Request**
```json
{
  "content": "string",
  "top_k_memories": 10
}
```

**Response**
```json
{
  "ok": true,
  "data": {
    "user_message": { },
    "assistant_message": { },
    "memory_context": [
      {
        "memory_id": "uuid",
        "memory_type": "finding",
        "title": "string | null",
        "content": "string",
        "relevance_score": 0.0
      }
    ]
  }
}
```

Streaming is optional for V1.

---

## 8. Source context ingestion

V1 intentionally supports only lightweight source-context ingestion.

### GET /workspaces/{workspace_id}/sources
List source context items for a workspace.

### POST /workspaces/{workspace_id}/sources/note
Register pasted notes as source context.

**Request**
```json
{
  "display_name": "string | optional",
  "content": "string"
}
```

### POST /workspaces/{workspace_id}/sources/url
Register URL-derived text as source context.

**Request**
```json
{
  "url": "https://example.com",
  "display_name": "string | optional",
  "content": "string | optional"
}
```

### Deferred to V1.1
- `POST /sources/file`
- file/blob upload handling

---

## 9. Memories

### GET /workspaces/{workspace_id}/memories
Search or list memories.

**Query params**
- `q` — optional semantic search query
- `type` — optional filter
- `pinned` — optional boolean
- `k` — default `20`
- `limit` — default `20`
- `offset` — default `0`

### POST /workspaces/{workspace_id}/memories
Create/save a memory item.

### GET /workspaces/{workspace_id}/memories/{memory_id}
Return memory detail.

### PATCH /workspaces/{workspace_id}/memories/{memory_id}
Update memory metadata.

---

## 10. Provider binding / switch

### GET /workspaces/{workspace_id}/provider-binding
Return current provider/model and available switch targets.

### POST /workspaces/{workspace_id}/provider-binding/switch
Switch the active workspace provider/model.

Because this may take time, it may return `202 Accepted` with status `switching`.

### GET /workspaces/{workspace_id}/provider-binding/status
Return switch progress/status.

---

## 11. Workspace stats

### GET /workspaces/{workspace_id}/stats
Return lightweight workspace sidebar stats.

---

## 12. Deferred to V1.1

These are intentionally out of the V1 API contract:
- MCP server tools/surface
- checkpoints
- restore flows
- public verify endpoint
- Solana/on-chain commitment operations
- file/blob upload endpoints

---

## 13. Routing map — V1 pages to endpoints

### Page 0 — Entry / Sign In
- `POST /auth/session`
- `GET /auth/me`

### Page 1 — Workspace Home
- `GET /workspaces`

### Page 2 — Create Workspace
- `POST /workspaces`

### Page 3 — Empty Workspace / First-Run
- `GET /workspaces/{workspace_id}`
- `GET /workspaces/{workspace_id}/stats`
- `POST /workspaces/{workspace_id}/sources/note`
- optional `POST /workspaces/{workspace_id}/sources/url`

### Page 4 — Active Workspace
- `GET /workspaces/{workspace_id}/sessions`
- `POST /workspaces/{workspace_id}/sessions`
- `GET /workspaces/{workspace_id}/sessions/{session_id}/messages`
- `POST /workspaces/{workspace_id}/sessions/{session_id}/messages`
- `POST /workspaces/{workspace_id}/memories`
- `GET /workspaces/{workspace_id}/stats`

### Page 5 — Provider Switch
- `GET /workspaces/{workspace_id}/provider-binding`
- `POST /workspaces/{workspace_id}/provider-binding/switch`
- `GET /workspaces/{workspace_id}/provider-binding/status`

### Page 6 — Memory Explorer
- `GET /workspaces/{workspace_id}/memories`
- `GET /workspaces/{workspace_id}/memories/{memory_id}`
- `PATCH /workspaces/{workspace_id}/memories/{memory_id}`

### Deferred pages/features — V1.1
- checkpoint / restore
- verify view
- MCP tool surface

---

## 14. Bottom-line rule

If an endpoint is not required by the minimal V1 memory-product story, it should move to V1.1.
