# V1_PACKET_A_PROMPT.md

Use this prompt for **Claude Code** to execute **Packet A** from `V1_IMPLEMENTATION_TASKS.md`.

---

You are implementing **Mnemonic V1 — Packet A**.

## Read first
Before making changes, read these files and follow them strictly:
- `src/turbo-quant-agent-memory/V1_SCOPE.md`
- `src/turbo-quant-agent-memory/V1_DELIVERABLES.md`
- `src/turbo-quant-agent-memory/ARCHITECTURE_V1.md`
- `src/turbo-quant-agent-memory/V1_TECH_STACK.md`
- `src/turbo-quant-agent-memory/V1_API.md`
- `src/turbo-quant-agent-memory/V1_ACCEPTANCE_CRITERIA.md`
- `src/turbo-quant-agent-memory/V1_IMPLEMENTATION_TASKS.md`

## Packet A scope
Implement:
- **Task 1 — Backend foundation and SQLite schema**
- **Task 2 — Workspace home and create-workspace flow**

## Goal
Create the first working vertical slice of Mnemonic V1:
- backend starts cleanly
- SQLite schema initializes from scratch
- local auth/session stub exists
- user can load the app
- user can create a workspace
- user can see the workspace persist after reload
- user can open the workspace shell

## Hard constraints
Do **not** build any V1.1 features.

Specifically do **not** add:
- MCP
- file upload / blob storage
- checkpoints / verify
- Solana
- multi-agent flows
- protocol-heavy UI

Keep architecture aligned to `ARCHITECTURE_V1.md`:
- one web app
- one FastAPI backend
- one SQLite DB
- one operational persistence boundary

## Required backend work
Implement the minimal backend foundation needed for Packet A:

### Objects
- Workspace
- Session
- Message
- MemoryItem
- ProviderBinding
- SourceContext

### Required behavior
- backend app boots locally
- SQLite DB initializes on empty environment
- schema/migrations/bootstrap exist
- local session/auth stub works well enough for a single-user local-first flow

### Required endpoints
- `POST /auth/session`
- `GET /auth/me`
- `POST /auth/logout`
- `GET /workspaces`
- `POST /workspaces`
- `GET /workspaces/{workspace_id}`
- `PATCH /workspaces/{workspace_id}`

## Required frontend work
Implement the first usable UI path:

### Workspace Home
- list workspaces
- create workspace CTA
- show current provider/model on workspace cards
- empty state if no workspaces exist

### Create Workspace flow
- workspace name input
- workspace description input
- initial provider/model selection if the current app structure already supports it simply
- create action
- redirect/open workspace after creation

### Workspace shell
After creation/open:
- route into the workspace shell
- shell can still be minimal
- does not need the full active conversation loop yet

## Files likely touched
You do not have to use these exact paths if the repo structure differs, but keep the boundaries clear:
- backend app entrypoint / router registration
- DB bootstrap/migration files
- repository/data access layer
- workspace service layer
- auth/session stub
- workspace home frontend page/components
- create-workspace frontend page/components
- workspace shell route/page
- API client/hooks for auth/workspaces

## Definition of done
Packet A is done only if all of these are true:
- backend starts cleanly
- SQLite schema can be created from scratch
- local auth/session flow works for local-first single-user mode
- user can create a workspace from the UI
- workspace persists in SQLite
- page reload keeps the workspace visible
- opening a workspace lands in the correct workspace shell
- no V1.1 features were introduced

## Non-goals for this packet
Do not implement:
- session/message ask loop
- save-memory flow
- memory explorer
- provider switching runtime logic
- source context ingestion
- instrumentation/demo seeding

Those belong to later packets.

## Implementation guidance
- prefer simple, boring solutions
- avoid premature abstraction beyond what the architecture already requires
- keep frontend thin
- keep backend as the single source of business logic
- keep persistence inside SQLite only

## Validation steps
Before finishing, validate at least:
1. fresh install / fresh DB boot
2. backend starts without errors
3. frontend loads
4. create workspace works
5. reload still shows created workspace
6. open workspace shell works

## Final output format
When done, report back with:
- summary of what was implemented
- files changed
- commands used to run/test
- any gaps or follow-up items

If you hit a structural blocker, stop and explain it clearly instead of inventing extra scope.
