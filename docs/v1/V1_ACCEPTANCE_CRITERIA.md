# V1_ACCEPTANCE_CRITERIA.md

## Purpose

This document defines **done means done** for Mnemonic V1.

The goal is to let programming agents implement features with clear stop conditions.

## Global product acceptance

V1 is only acceptable if all of these are true:

1. A user can create and reopen a workspace.
2. A user can conduct research in that workspace across multiple sessions.
3. A user can save durable memory items and retrieve them later.
4. A user can switch provider/model without losing workspace memory.
5. A user can clearly see what the workspace currently knows.

If any of the above fails, V1 is not complete.

## Feature acceptance criteria

### 1. Workspace Home

Done when:
- the user can see a list of workspaces
- each workspace shows title, summary/description, last updated, and current provider/model
- a new workspace can be created from this page
- a workspace can be opened from this page

### 2. Create Workspace

Done when:
- user can create a workspace with name and description
- new workspace is persisted and visible on Workspace Home
- user is redirected into the new workspace after creation

### 3. Session / chat loop

Done when:
- a session can be created inside a workspace
- user messages are persisted
- assistant messages are persisted
- reopening the workspace shows prior session history
- the assistant can answer using workspace memory context

### 4. Source context ingestion

Done when:
- a user can add at least one pasted note as workspace context
- optional URL text ingestion works if included in the build
- the source/context record is persisted in the workspace
- source context can later be tied back to saved memories or session context

### 5. Save memory

Done when:
- a user can save a finding, decision, question, or source as a memory item
- saved memory appears in the workspace memory panel
- memory item persists after page reload / app restart
- saved memory is associated with the workspace and optional source session/message provenance

### 6. Memory search / explorer

Done when:
- a user can search memory within a workspace
- results can be filtered by memory type
- a user can open a memory detail view
- a user can jump from a memory item back to relevant source context where available

### 7. Project state panel

Done when:
- workspace summary is visible
- unresolved questions are visible
- recent saved memories are visible
- current provider/model is visible

### 8. Provider switch

Done when:
- a user can select another provider/model
- the switch completes successfully or fails with a visible error state
- workspace memories remain present after the switch
- previously saved findings can still be retrieved after the switch

## Deferred acceptance for V1.1

These are intentionally not blocking V1:
- MCP server
- file upload / blob storage
- checkpoints / restore
- public verify page
- Solana anchoring / verification

## UX acceptance criteria

### Continuity test
Passes when:
- user creates workspace on day 1
- saves memories
- returns on day 2
- can continue the project without manually rebuilding core context

### Portability test
Passes when:
- user saves several meaningful memories
- switches provider/model
- can still retrieve those memories and continue work

### Visible-memory test
Passes when:
- user can tell what the workspace knows
- user can inspect previously saved findings directly

## Performance / usability thresholds

These are V1 targets, not theoretical maxima.

### Workspace creation
- should complete in under 2 minutes from user arrival to first active workspace

### Memory save
- should feel immediate or near-immediate in the UI

### Memory search
- should return useful results without requiring the user to understand ranking internals

### Provider switch
- long-running is acceptable
- visible progress or status is required

## Failure-state acceptance

V1 is not complete unless these failures are handled visibly:

- provider switch failure
- source/context ingestion failure
- empty memory search results

In all failure cases, the user must receive a clear message and the workspace state must remain safe.

## Anti-acceptance criteria

These are not valid reasons to declare V1 done:

- the UI looks good but persistence is unreliable
- provider switch works only by wiping prior memory
- memory exists but is not user-visible / inspectable
- feature-complete implementation exists without the canonical V1 flows working end-to-end

## Final definition of done

Mnemonic V1 is done when a solo researcher can:

1. create a workspace
2. do meaningful work inside it
3. save durable memory
4. return later and resume
5. switch providers without losing project memory
6. inspect/search prior memory confidently

That is the V1 product proof.
