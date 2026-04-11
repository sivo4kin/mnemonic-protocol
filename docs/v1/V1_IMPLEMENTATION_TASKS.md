# V1_IMPLEMENTATION_TASKS.md

## Purpose

This document turns the current V1 architecture/spec stack into **execution-ready implementation task packets**.

These tasks are designed to be handed to a coding agent such as **Claude Code**.

## Global rules for every task

- follow `V1_SCOPE.md`
- follow `ARCHITECTURE_V1.md`
- follow `V1_API.md`
- do not add V1.1 features
- do not add file/blob storage
- do not add MCP
- do not add checkpoints/verify/Solana
- keep one backend, one SQLite DB, one web app
- keep V1 memory writes **explicit-save first**
- keep one fixed canonical embedder
- only switch chat/model provider binding in V1

## Canonical V1 data objects

These are the objects V1 must support directly:
- Workspace
- Session
- Message
- MemoryItem
- ProviderBinding
- SourceContext

## Recommended task order

1. backend foundation + schema
2. workspace home/create flow
3. ask/session backend path
4. active workspace UI
5. explicit save-memory flow
6. memory explorer + search
7. provider switch flow
8. source context (notes-first)
9. workspace polish + instrumentation + demo readiness

---

## Task 1 — Backend foundation and SQLite schema

### Goal
Create the minimal backend/runtime foundation for V1.

### Build
- FastAPI app bootstrapping
- SQLite initialization/migration path
- repository layer for V1 objects
- local auth/session stub
- settings/config bootstrap

### Required objects
- Workspace
- Session
- Message
- MemoryItem
- ProviderBinding
- SourceContext

### Files likely touched
- backend app entrypoint
- DB bootstrap/migration files
- repository/data-access layer
- settings/config files
- local auth/session helper files

### Definition of done
- backend starts cleanly
- schema can be created from scratch on empty environment
- local session flow exists
- repositories can create/read/update core V1 objects
- one SQLite operational DB is used

### Do not build
- provider switching UI
- checkpoints
- verify
- Solana
- file upload subsystem
- MCP server

---

## Task 2 — Workspace home and create-workspace flow

### Goal
Implement the first usable product path: enter app, see workspaces, create a workspace, open it.

### Build
- Workspace Home page
- Create Workspace page/modal/flow
- backend endpoints for list/create/get/update workspace

### Required endpoints
- `GET /workspaces`
- `POST /workspaces`
- `GET /workspaces/{workspace_id}`
- `PATCH /workspaces/{workspace_id}`

### Files likely touched
- workspace routes/controllers
- workspace service layer
- workspace repository
- workspace home frontend page/components
- create-workspace frontend page/components

### Definition of done
- user can create a workspace from the UI
- new workspace persists in SQLite
- page reload keeps the workspace visible
- opening a workspace lands in the correct workspace view shell
- current provider/model is visible on workspace cards

### Do not build
- checkpoint status
- verify links
- file upload widgets
- active message loop

---

## Task 3 — Ask/session backend path

### Goal
Implement the backend path for live sessions, provider calls, and memory-aware response generation.

### Build
- sessions API
- messages API
- provider adapter interface
- fixed canonical embedder configuration
- ask flow orchestration
- retrieval integration from Mnemonic core

### Required endpoints
- `GET /workspaces/{workspace_id}/sessions`
- `POST /workspaces/{workspace_id}/sessions`
- `GET /workspaces/{workspace_id}/sessions/{session_id}`
- `GET /workspaces/{workspace_id}/sessions/{session_id}/messages`
- `POST /workspaces/{workspace_id}/sessions/{session_id}/messages`

### Files likely touched
- session/message routes/controllers
- session/message services
- provider abstraction/adapters
- Mnemonic core integration layer
- message persistence repositories

### Definition of done
- backend can create sessions
- backend can persist user/assistant messages
- backend can call the active chat/model provider
- backend retrieves relevant memories from the Mnemonic core before answer generation
- active provider binding is respected

### Important implementation rule
- use one fixed canonical embedder for V1 memory/retrieval logic
- do not tie memory identity to the active chat provider

### Do not build
- final polished workspace UI
- provider switch UI
- auto-memory extraction by default

---

## Task 4 — Active workspace UI

### Goal
Make the workspace actually usable for live conversation.

### Build
- Active Workspace page
- session list/selector
- conversation timeline
- message composer
- response rendering
- basic right-rail shell for memory/project state

### Depends on
- Task 3 backend path

### Files likely touched
- active workspace frontend page
- session list/timeline/composer components
- API client hooks for sessions/messages
- memory panel shell components

### Definition of done
- user can start a session and exchange messages from the UI
- page reload preserves visible session history
- the workspace page feels like a usable product, not a stub

### Do not build
- explicit save-memory action yet
- provider switch flow yet
- source context ingestion yet

---

## Task 5 — Explicit save-memory flow

### Goal
Implement the core V1 differentiator: explicit durable memory.

### Build
- save-memory action from assistant outputs or selected content
- MemoryItem persistence
- memory rail/panel in active workspace
- memory type selection (finding/decision/question/source)

### Required endpoints
- `POST /workspaces/{workspace_id}/memories`
- `GET /workspaces/{workspace_id}/memories`
- `GET /workspaces/{workspace_id}/memories/{memory_id}`
- `PATCH /workspaces/{workspace_id}/memories/{memory_id}`

### Files likely touched
- memory routes/controllers
- memory service layer
- memory repository
- save-memory UI components/actions
- active workspace memory panel components

### Definition of done
- user can explicitly save a finding/decision/question/source
- saved memory appears in the workspace memory panel
- saved memory survives reload/restart
- later ask-flow retrieval can surface saved items

### Important implementation rule
- V1 memory write policy is **explicit save**, not auto-extraction-by-default

---

## Task 6 — Memory explorer and search

### Goal
Make memory inspectable and searchable as a first-class part of the product.

### Build
- Memory Explorer page
- search bar
- type filters
- memory detail panel/drawer
- jump-to-context action where available

### Required endpoints
- `GET /workspaces/{workspace_id}/memories`
- `GET /workspaces/{workspace_id}/memories/{memory_id}`
- `PATCH /workspaces/{workspace_id}/memories/{memory_id}`

### Files likely touched
- memory explorer frontend page
- search/filter components
- memory detail components
- API client hooks for memory search/detail

### Definition of done
- user can search memory
- user can filter memory by type
- user can inspect full memory content
- user can tell what the workspace currently knows

---

## Task 7 — Provider binding and provider switch

### Goal
Prove the V1 product hypothesis that memory survives provider/model switching.

### Build
- provider binding UI
- provider switch modal/flow
- backend provider-binding endpoints
- switch status handling

### Required endpoints
- `GET /workspaces/{workspace_id}/provider-binding`
- `POST /workspaces/{workspace_id}/provider-binding/switch`
- `GET /workspaces/{workspace_id}/provider-binding/status`

### Files likely touched
- provider-binding routes/controllers
- provider service layer
- provider switch frontend components
- workspace top-bar/provider selector UI

### Definition of done
- user selects a different chat/model provider
- switch completes or fails visibly
- workspace memories still exist after switch
- future messages use the new provider binding
- user can continue the same project after switch

### Important implementation rule
- do not migrate or recreate workspace memory identity during provider switch

---

## Task 8 — Source context (notes-first)

### Goal
Let the user add lightweight non-file context into the workspace without expanding V1 scope too far.

### Build
- pasted-note input flow
- source context listing in workspace
- optional URL-to-text flow only if it stays lightweight

### Required endpoints
- `GET /workspaces/{workspace_id}/sources`
- `POST /workspaces/{workspace_id}/sources/note`
- optional `POST /workspaces/{workspace_id}/sources/url`

### Files likely touched
- source-context routes/controllers
- source-context service layer
- source-context repository
- note input/listing frontend components

### Definition of done
- user can add a pasted note as context
- source context persists in SQLite
- source context is visible in the workspace

### Strong recommendation
If URL ingestion adds material complexity, cut it and keep pasted notes only.

### Do not build
- file upload
- blob/object storage

---

## Task 9 — Workspace polish, instrumentation, and demo readiness

### Goal
Make V1 legible, measurable, and demo-ready so it can actually prove the hypothesis.

### Build
- workspace summary panel
- unresolved questions panel
- recent memories panel
- polished empty states
- event logging / lightweight instrumentation
- seeded demo workspace and sample memories

### Metrics/events to capture
- `workspace_created`
- `memory_saved`
- `session_resumed`
- `provider_switch_started`
- `provider_switch_completed`
- `post_switch_message_sent`

### Files likely touched
- workspace state panel frontend components
- backend event logging/analytics helper
- demo seed script or fixture files
- sample/demo data files

### Definition of done
- a seeded demo workspace exists
- key product-hypothesis events are capturable
- the canonical V1 demo can run start-to-finish
- the app no longer feels like a plain stateless chat wrapper

---

## Suggested task packet boundaries for Claude Code

### Packet A
- Task 1
- Task 2

### Packet B
- Task 3

### Packet C
- Task 4
- Task 5

### Packet D
- Task 6
- Task 7

### Packet E
- Task 8
- Task 9

## Bottom line

These tasks are the minimum execution-ready path for proving that Mnemonic V1 is a real provider-independent persistent memory product.
