# V1_TECH_STACK.md

## Decision summary

Mnemonic V1 should be implemented as a **minimal local-first web application** with:

- **Frontend:** React + TypeScript + Vite
- **UI styling:** Tailwind CSS + lightweight component primitives
- **Backend:** FastAPI (Python)
- **Primary persistence:** SQLite
- **Core memory engine:** existing Python `mnemonic/` package
- **Source context in V1:** pasted notes and optional URL-to-text ingestion only

V1.1 adds:
- MCP server
- file/blob storage
- checkpointing / verification surface
- Solana anchoring / on-chain commitment path

## Why this stack

### React + TypeScript + Vite
- fast front-end iteration
- simple local development
- no unnecessary full-stack framework complexity for V1

### FastAPI
- aligns with the current Python-heavy prototype
- easiest way to call the `mnemonic/` core directly
- straightforward request/response JSON API
- easy local-first development

### SQLite
- lowest-friction durable operational store for V1
- perfectly aligned with a minimal local-first product proof
- enough for workspaces, sessions, messages, memory metadata, and provider state
- easy migration path later if hosted multi-user mode becomes necessary

## Explicit V1 engineering stance

### Minimal product first
V1 should prove the usable memory product before protocol surfaces and integrations.

### No premature distributed infrastructure
Do not add in V1:
- Postgres unless SQLite becomes a blocker
- Redis / job queues
- websocket complexity unless clearly needed
- microservices
- object/blob storage systems for attachments
- Solana anchoring pipeline inside the V1 critical path

## Frontend stack details

### Framework
- React 18+
- TypeScript
- Vite for local dev/build

### Styling
- Tailwind CSS
- small reusable component layer

### State management
- React Query / TanStack Query for server state
- local component state or minimal client store for UI state

### Routing
- React Router or equivalent lightweight client routing

## Backend stack details

### API framework
- FastAPI

### Core runtime
- Python 3.11+

### Core responsibilities
- workspace CRUD
- chat/session orchestration
- memory search and persistence
- provider switch orchestration
- minimal source-context ingestion

### Background work
- FastAPI background tasks only where needed
- no separate queue infrastructure in V1

## Persistence

### Primary DB
- SQLite

### Stored domains
- workspaces
- sessions/messages
- memory items
- provider bindings / current provider state
- lightweight source-context metadata

### Not in V1 storage scope
- file uploads
- object/blob storage
- public checkpoint artifacts
- on-chain anchoring state

## Core integration strategy

### Memory/search path
- FastAPI calls the existing Python `mnemonic/` implementation directly
- do not duplicate retrieval logic in the frontend

### Provider switching
- provider/model switching is orchestrated server-side
- the browser only requests the switch and refreshes workspace state

### Source-context path
- prefer pasted notes in V1
- optional URL ingestion is acceptable only if normalized into text and stored without a separate file subsystem

## Auth stance for V1

### Default
- simple local/single-user mode first

### Implication
- do not force OAuth into the first implementation pass
- auth can be minimal or stubbed for local-first V1

## API stance

- REST/JSON over `/api/v1`
- request/response model first
- no websocket dependency required for V1

## Elegant production path

### Near-term
- keep SQLite in V1
- if needed, productionize with SQLite replication / backup or a remote SQLite-compatible layer

### Later
- move to Postgres only if multi-user hosted mode or concurrency truly demands it

## Deferred to V1.1

- MCP over stdio/http
- file/blob storage
- checkpoints / verification
- Solana anchoring / on-chain commitment

## Bottom-line rule

V1 should be built with the **simplest stack that proves provider-independent persistent memory in a usable web app**.
