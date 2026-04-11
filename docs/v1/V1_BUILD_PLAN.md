# V1_BUILD_PLAN.md

## Purpose

This document defines the implementation sequence for Mnemonic V1 so programming agents can be tasked in a controlled order.

## Build philosophy

Build the smallest thing that proves the product thesis.

Order matters:
- app shell first
- core workspace loop second
- memory operations third
- provider portability fourth
- polish/demo readiness fifth

Protocol surfaces and integrations are intentionally deferred to V1.1.

## Milestone 1 — App shell

### Goal
Stand up the runnable product shell.

### Deliverables
- frontend app bootstrapped
- backend app bootstrapped
- local session / auth stub working
- workspace list page scaffolded
- create workspace flow scaffolded
- shared layout/nav shell in place

### Exit condition
User can open the app, create a workspace, and land inside it.

## Milestone 2 — Core workspace loop

### Goal
Make the workspace usable as a research environment.

### Deliverables
- session creation/listing
- workspace chat canvas
- message persistence
- pasted-note ingestion
- optional URL-to-text ingestion without file/blob storage
- right-rail project state shell
- empty-state UX for first-run workspace

### Exit condition
User can do one real research session inside a workspace and revisit the session history.

## Milestone 3 — Memory operations

### Goal
Turn workspace activity into durable, inspectable memory.

### Deliverables
- save memory item action
- memory types: finding / decision / question / source
- memory panel in workspace
- memory explorer page
- memory search/filter/detail view
- jump-to-context where available

### Exit condition
User can save useful project memories and retrieve them later.

## Milestone 4 — Provider portability

### Goal
Prove the killer feature: same workspace memory survives provider/model switching.

### Deliverables
- provider binding view
- provider switch flow
- switch status handling
- memory preservation through switch
- clear error state for failed switch

### Exit condition
User can switch provider/model and continue the same project with prior memory still intact.

## Milestone 5 — Demo readiness / polish

### Goal
Make V1 demonstrable and usable for the canonical story.

### Deliverables
- seeded canonical demo workspace
- realistic sample memory items
- polished empty states and helper text
- core failure states handled
- end-to-end test of canonical V1 flows

### Exit condition
Canonical demo story can be run start-to-finish without manual patching.

## Deferred to V1.1

- MCP server
- file upload / blob storage
- checkpoints / restore
- verify page
- Solana anchoring / on-chain commitment

## Recommended task groupings for programming agents

### Agent group A — Frontend shell and layout
- workspace home
- create workspace page
- nav/layout
- empty workspace state

### Agent group B — Workspace interaction
- sessions/messages UI
- chat canvas
- pasted-note / URL text ingestion UI

### Agent group C — Memory layer
- save memory actions
- memory panel
- memory explorer/search/detail

### Agent group D — Provider portability
- provider switch UI
- provider state handling

### Agent group E — Backend/API integration
- workspace/session/message APIs
- memory APIs
- provider binding APIs

## Dependency order

### Cannot start meaningfully without
- V1 scope
- tech stack
- domain model
- API contract

### Parallelizable after those exist
- frontend shell
- workspace APIs
- memory APIs
- memory UI

### Should come after memory layer is stable
- provider switching
- polish/demo hardening

## Definition of implementation readiness

The project is ready for detailed programming-agent tasks when:

- `V1_SCOPE.md` exists
- `V1_TECH_STACK.md` exists
- `V1_DOMAIN_MODEL.md` exists
- `V1_API.md` is aligned and stable enough
- `V1_ACCEPTANCE_CRITERIA.md` exists
- this build plan exists

## Bottom-line rule

Do not task agents by page names alone.

Task them by:
- milestone
- owned files/components
- required endpoints
- explicit acceptance criteria

That is how V1 gets built without drift.
