# V1_DELIVERABLES.md

## Purpose

This document answers the practical question:

> What do we actually ship in V1?

## V1 deliverable

Mnemonic V1 should ship exactly **one core product surface**:

- a **minimal web app** that proves provider-independent persistent memory for a human user

## What the V1 web app must prove

### 1. Persistent workspace memory
- one workspace survives multiple sessions
- saved findings remain available later

### 2. Provider portability
- the same workspace can continue across provider/model switches
- memory survives the switch

### 3. Visible memory state
- user can see what has been saved
- user can search or inspect prior memory

## Minimum capability

- create/open workspace
- chat in workspace
- save memory items
- inspect/search memory
- switch provider/model
- add pasted notes as context

## What V1 is intentionally not shipping

Moved to **V1.1**:
- MCP server
- file upload / blob storage
- checkpoints as first-class UX
- public verify page
- Solana anchoring / on-chain verification surface

## Why this is the right V1 cut

V1 should prove the **usable memory product** before proving the full protocol/integration stack.

That means:
- first prove users want the workspace + memory + portability experience
- then add protocol/trust/integration surfaces in V1.1

## Definition of success

V1 is successful if:

1. a human can try Mnemonic in the web app and understand the value
2. memory clearly persists across sessions
3. provider switching works without losing project memory
4. the app already feels like more than a stateless chat UI

## V1.1 follow-on

V1.1 adds:
- MCP server
- file/blob storage
- checkpoints / verification
- Solana anchoring

## Bottom line

V1 should ship as:

- **a minimal web app people can try**
- proving **provider-independent persistent memory**

V1.1 will make it feel more like the full protocol surface.
