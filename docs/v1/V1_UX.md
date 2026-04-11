# V1_UX.md

## V1 product shape

Mnemonic V1 should be a **minimal persistent research workspace** for a solo researcher / founder / analyst working on one long-running topic across multiple sessions and model providers.

The core user promise is:

> One persistent project memory across sessions and providers, visible and usable in a simple web app.

## Exact V1 user case

### User

A solo researcher or founder working on a multi-day or multi-week project such as:

- AI infrastructure market research
- protocol design
- startup thesis formation
- technical architecture analysis

### Core user story

> As a solo researcher working on a multi-session project, I want one AI workspace that preserves my project memory across sessions and model switches, so I can continue where I left off without re-explaining everything.

For the current V1 cut, the emphasis is on **usable memory + provider portability**. Verification/protocol surfaces are deferred to V1.1.

## Client surface

### Primary surface

V1 should have **one primary client surface**:

- a single **web app**

Do not add native mobile, browser extension, IDE plugin, or multi-surface complexity in V1.

### Secondary surface

No secondary client surface is required in V1.

MCP, verify page, and protocol-facing trust surfaces move to **V1.1**.

## Minimum screen set

V1 should ship with exactly these user-facing surfaces:

1. **Workspace list**
   - create workspace
   - resume workspace
   - see recent activity / last updated / current provider

2. **Workspace view**
   - main assistant interaction surface
   - pasted note ingestion
   - optional URL text ingestion
   - provider switch control
   - persistent memory-aware chat

3. **Memory explorer**
   - search saved findings, decisions, questions, and sources
   - inspect memory items directly
   - jump from memory items back to source context

4. **Provider switch flow**
   - switch provider/model
   - continue in the same workspace with memory intact

Deferred to **V1.1**:
- checkpoint / restore flow
- verify view
- MCP server

## Workspace layout

The primary workspace view should have **three visible regions**:

### A. Main work canvas
- assistant chat / composition area
- pasted notes, links, and conversation
- familiar chat-like interaction model

### B. Memory rail / memory panel
- saved findings
- decisions
- open questions
- pinned facts
- recent memories added

### C. Project state panel
- current project summary
- active hypotheses
- unresolved questions
- current provider/model

## Core interactions

The UI must make these interactions trivial:

1. **Ask** — query the assistant about the active project
2. **Save** — persist a result as a memory item / finding / decision / question
3. **Recall** — search prior memory directly
4. **Switch** — continue the same workspace with another provider/model

## First-time aha moments

The UX should create these three reactions in order:

1. **"This is not just another chat thread — it's a persistent project workspace."**
2. **"I can switch models and my project memory survives."**
3. **"I can actually see and reuse what this workspace knows."**

## What V1 must not become

Avoid adding these into the main V1 client surface:

- multi-agent workflow builders
- collaboration / shared workspaces
- complex version trees / branching UI
- blockchain admin dashboards
- protocol jargon on the main screen
- KV-cache persistence UX
- checkpoint / verify protocol surfaces

V1 should feel like a **research workspace with persistent memory**, not like a protocol console.

## Product framing

The UI should make memory **visible**, not hidden.

Most chat apps hide memory behind vague assistant behavior. Mnemonic should expose:

- what the workspace knows
- what has been saved
- what is unresolved

## V1 summary

If reduced to one sentence:

> Mnemonic V1 is a persistent research workspace where chat, memory, and provider switching live in one place.

Trust/integration surfaces are deferred to V1.1.

## Page-by-page user journey

This is the canonical V1 journey from first entry to the core product loop.

### Page 0 — Entry / Sign In

**Purpose**
- get the user into the product with minimal friction

**User sees**
- product name and one-line value proposition
- sign in / continue
- optional provider setup

**Primary CTA**
- Enter Mnemonic

### Page 1 — Workspace Home

**Purpose**
- frame Mnemonic around projects, not isolated chats

**User sees**
- list of workspaces
- create workspace CTA
- recent activity and current provider

**Primary CTA**
- Create Workspace

### Page 2 — Create Workspace

**Purpose**
- define the persistent project memory container

**User enters**
- workspace name
- short description
- optional starter context / notes / URLs
- optional initial provider selection

**Primary CTA**
- Create Workspace

### Page 3 — Empty Workspace / First-Run State

**Purpose**
- get the user from zero to first useful project interaction

**User sees**
- workspace header
- empty chat canvas with guided prompts
- empty memory panel
- empty project state panel

**Primary CTA**
- Start Researching

### Page 4 — Active Workspace

**Purpose**
- this is the main product page where the user does ongoing work

**Layout**
- center: work canvas / assistant conversation
- right rail: memory panel + project state panel
- left sidebar: workspace navigation

**Primary CTA**
- continue working in the project

### Page 5 — Provider Switch Flow

**Purpose**
- expose the core portability promise

**User sees**
- current provider/model
- target provider/model
- reassurance that workspace memory persists across the switch

**Primary CTA**
- Switch Provider

### Page 6 — Memory Explorer

**Purpose**
- let the user inspect, search, and trust the memory layer directly

**User sees**
- memory search
- filters for findings / decisions / questions / sources
- memory list and detail view

**Primary CTA**
- Search Memory

### Page 7 — Checkpoint / Restore (deferred to V1.1)

**Purpose**
- turn persistent memory into versioned, recoverable state

**User sees**
- checkpoint list
- create checkpoint
- restore prior checkpoint
- checkpoint metadata and status

**Primary CTA**
- Create Checkpoint

### Page 8 — Verify View (deferred to V1.1)

**Purpose**
- expose the trust / verification layer simply

**User sees**
- checkpoint id / hash
- storage reference
- verification control and result state

**Primary CTA**
- Verify Checkpoint

## Canonical first-session flow

1. User signs in
2. User lands on Workspace Home
3. User creates a workspace
4. User enters the first-run workspace state
5. User chats / adds notes / adds sources
6. Assistant generates findings
7. User saves key findings into memory
8. User returns later
9. User resumes workspace
10. User switches provider
11. User confirms project memory survives
12. Deferred to V1.1: checkpoints / verification

## Page hierarchy in plain language

- **Home** — where projects live
- **Workspace** — where work happens
- **Memory Explorer** — where memory becomes inspectable
- **Checkpoint / Verify** — deferred to V1.1

## UX priority ranking

### Tier 1 — Must feel excellent
- Workspace Home
- Active Workspace
- Provider Switch

### Tier 2 — Must feel solid
- Memory Explorer

### Tier 3 — Can stay simple in V1
- Entry / Sign In
- Create Workspace

## Exact components by page

This section defines the concrete UI components required for each V1 page.

### Page 0 — Entry / Sign In

**Components**
- hero block
- primary auth card
- optional provider setup card
- footer links

**Key rule**
- keep this page minimal; no protocol or blockchain complexity

### Page 1 — Workspace Home

**Components**
- top navigation bar
- page header
- workspace search bar
- workspace filter chips
- workspace card grid / list
- empty state module

**Each workspace card should show**
- workspace title
- short summary
- last updated
- current provider/model
- open workspace CTA

### Page 2 — Create Workspace

**Components**
- page header
- workspace name input
- workspace description textarea
- starter context module (notes / URLs)
- initial provider selector
- optional starter prompt suggestions
- primary CTA bar

### Page 3 — Empty Workspace / First-Run State

**Components**
- workspace top bar
- first-run helper card
- prompt starter cards
- empty main chat canvas
- context input tray
- empty memory panel
- empty project state panel

### Page 4 — Active Workspace

**Global top bar**
- workspace title
- provider/model selector
- settings / workspace menu

**Left sidebar**
- workspace switcher
- navigation items
- recent workspaces
- collapse control

**Main work canvas**
- conversation timeline
- message composer
- add note / add URL controls
- quick-save actions under assistant outputs
- inline source cards

**Right rail — Memory panel**
- panel header
- quick search
- findings section
- decisions section
- open questions section
- pinned memories section
- recent memories section

**Right rail — Project state panel**
- project summary card
- active hypotheses card
- unresolved questions card
- current provider/model card

**Optional sticky action strip**
- save summary
- switch provider
- search memory

### Page 5 — Provider Switch Flow

**Components**
- modal / slide-over header
- current provider block
- target provider selector
- memory continuity note
- compatibility / warning note
- confirm switch CTA
- cancel CTA

### Page 6 — Memory Explorer

**Components**
- page header
- search bar
- filter row
- memory results list
- memory detail drawer / side panel
- jump-to-context action
- pin / unpin control

**Memory detail should show**
- memory type
- full content
- source context
- created time
- tags

### Page 7 — Checkpoint / Restore (deferred to V1.1)

**Components**
- page header
- checkpoint timeline / list
- create checkpoint button
- create checkpoint modal
- checkpoint detail panel
- restore button
- restore confirmation modal

**Each checkpoint item should show**
- checkpoint label
- timestamp
- provider/model at time of checkpoint
- verification status

### Page 8 — Verify View (deferred to V1.1)

**Components**
- page header
- checkpoint id / hash input module
- verify CTA
- verification result card
- technical detail accordion
- copy / share controls

## Cross-page component rules

- memory must stay visible, not hidden behind assistant behavior
- the interface must reinforce workspace continuity over isolated chats
- provider switching must feel safe and explicit
- verification must feel simple, not like a blockchain dashboard
- save / recall actions must remain first-class throughout the UX

## Minimal V1 component set

If the interface must be reduced to the smallest viable set, keep:

- workspace list
- workspace chat canvas
- memory rail
- provider switch modal
- checkpoint list
- verify result card
