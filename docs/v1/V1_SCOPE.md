# V1_SCOPE.md

## Product shape

Mnemonic V1 is a **minimal persistent research workspace** for a solo researcher / founder / analyst.

The point of V1 is to prove:

> A user can work in one workspace, save durable memory, come back later, switch providers, and continue without rebuilding context manually.

V1 is the **usable memory product**.

It is **not yet** the full protocol/trust/integration surface.

## Primary user

- solo researcher
- technical founder
- analyst
- investigative / deep-research user

## Core user case

A user creates a project workspace, works across multiple sessions, saves findings into memory, comes back later, and continues the same project with memory intact across provider/model switches.

## In scope

### Workspace lifecycle
- create workspace
- list workspaces
- open / resume workspace
- edit workspace name / description

### Workspace interaction
- chat inside a workspace
- continue prior sessions
- add pasted notes as project context
- optionally ingest URL text without introducing a full file/blob subsystem

### Persistent memory
- save structured memory items
- memory item types:
  - findings
  - decisions
  - open questions
  - sources / references
- browse and search workspace memory
- inspect individual memory items

### Project state visibility
- project summary
- unresolved questions
- recent saved memories
- current provider/model

### Provider portability
- switch provider/model inside the same workspace
- preserve workspace memory across the switch

## Explicitly deferred to V1.1

- MCP server
- file upload / blob storage
- checkpoints as first-class product surface
- public verify page
- Solana anchoring / on-chain commitment UX
- protocol-heavy trust surfaces

## Explicitly out of scope

### Collaboration
- shared workspaces
- invites / roles / permissions
- collaborative memory pools

### Multi-agent behavior
- autonomous background agents
- agent swarms
- workflow builders

### Advanced versioning
- branching memory trees
- merge flows
- git-like history semantics

### KV-cache continuity UX
- KV-cache persistence UI
- runtime-state portability flows
- architecture-specific cache restore experiences

### Consumer/platform expansion
- mobile app
- browser extension
- IDE plugin
- full SDK platformization

## Scope guardrails

### Rule 1
If a feature does not strengthen the **persistent research workspace** experience, it is out of V1.

### Rule 2
If a feature does not improve one of these, it is out of V1:
- memory persistence
- provider portability
- user-visible memory clarity

### Rule 3
If a feature is mainly technically interesting but not required for the minimal user story, it moves to V1.1 or later.

### Rule 4
V1 should feel like a **useful memory product**, not a protocol console.

## Required V1 flows

1. create workspace
2. start a research session
3. save useful memory items
4. resume later with memory intact
5. switch provider/model
6. inspect/search prior memory

If these flows do not work end-to-end, V1 is not done.

## Success criteria

V1 is successful if a target user can:

- create a workspace in under 2 minutes
- start useful research in the first session
- save meaningful memory items
- resume a project later without rebuilding context manually
- switch provider without losing project memory
- understand what the workspace currently knows

## One-sentence anti-scope statement

Anything that turns V1 away from **provider-independent persistent project memory** toward protocol surface area should be deferred to V1.1.
