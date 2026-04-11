# V1_DOMAIN_MODEL.md

## Purpose

This document defines the **product/domain objects** required to implement Mnemonic V1 as a persistent research workspace.

It sits above the low-level vector/index schema in `SCHEMA.md`.

## Current V1 scope note

As of the current V1 cut:

- core V1 objects are: `Workspace`, `Session`, `Message`, `MemoryItem`, `ProviderBinding`
- lightweight source context is still allowed
- `Checkpoint` and `VerificationResult` are deferred to **V1.1**

## Domain overview

Mnemonic V1 has one primary top-level object:

- **Workspace**

Everything else exists inside or alongside a workspace:

- Session
- Message
- MemoryItem
- SourceDocument
- ProviderBinding

Deferred to V1.1:

- Checkpoint
- VerificationResult

## 1. User

### Meaning
The human operating one or more workspaces.

### Fields
- `user_id`
- `display_name`
- `email` (optional in local-first mode)
- `created_at`

### Notes
- V1 is effectively single-user/single-operator oriented.
- Multi-user roles are out of scope.

## 2. Workspace

### Meaning
The primary project container.

### Fields
- `workspace_id`
- `owner_user_id`
- `name`
- `description`
- `status` (`active | archived`)
- `current_provider`
- `current_model`
- `created_at`
- `updated_at`

### Responsibilities
- owns sessions/messages
- owns memory items
- defines provider/model context for active work

### State transitions
- create → active
- active → archived
- archived → active (optional)

## 3. Session

### Meaning
A single working conversation segment inside a workspace.

### Fields
- `session_id`
- `workspace_id`
- `title` (optional)
- `status` (`active | closed`)
- `started_at`
- `ended_at` (nullable)
- `created_at`
- `updated_at`

### Notes
- a workspace can have multiple sessions over time
- sessions give provenance for messages and memory extraction

## 4. Message

### Meaning
One user or assistant message within a session.

### Fields
- `message_id`
- `workspace_id`
- `session_id`
- `role` (`user | assistant | system`)
- `content`
- `provider_used` (nullable for user messages)
- `model_used` (nullable for user messages)
- `created_at`

### Notes
- messages are chronological
- messages may reference source docs and saved memories

## 5. MemoryItem

### Meaning
A durable unit of workspace memory.

### Types
- `finding`
- `decision`
- `question`
- `source`

### Fields
- `memory_id`
- `workspace_id`
- `source_session_id` (nullable)
- `source_message_id` (nullable)
- `memory_type`
- `title` (optional but recommended)
- `content`
- `tags` (optional)
- `is_pinned`
- `importance_score` (optional)
- `created_at`
- `updated_at`

### Notes
- `MemoryItem` is the user-visible durable memory layer
- memory items are searchable and inspectable
- memory items may later be linked to checkpoints

## 6. SourceDocument

### Meaning
An uploaded or linked source used in workspace research.

### Fields
- `source_id`
- `workspace_id`
- `source_type` (`pasted_note | url_text`)
- `display_name`
- `mime_type` (nullable)
- `storage_path_or_url`
- `ingestion_status` (`pending | ready | failed`)
- `created_at`

### Notes
- source docs are not the same as memory items
- source docs may produce memory items during use

## 7. ProviderBinding

### Meaning
The current model/provider configuration for a workspace.

### Fields
- `provider_binding_id`
- `workspace_id`
- `provider`
- `model`
- `status` (`active | switching | failed`)
- `switched_at`

### Notes
- only one active provider binding per workspace in V1
- provider switching updates workspace state and creates a new binding record or history entry

## 8. Checkpoint

> Deferred to V1.1

### Meaning
A versioned snapshot of workspace state.

### Fields
- `checkpoint_id`
- `workspace_id`
- `label` (optional)
- `status` (`pending | committing | committed | failed`)
- `content_hash`
- `storage_ref` (nullable)
- `chain_ref` (nullable)
- `memory_count`
- `created_at`
- `committed_at` (nullable)

### Notes
- a checkpoint captures the durable workspace state at a moment in time
- verification is performed against `content_hash` + backing refs

## 9. VerificationResult

> Deferred to V1.1

### Meaning
Ephemeral result of verifying a checkpoint.

### Fields
- `checkpoint_id`
- `status` (`verified | mismatch | unavailable`)
- `verified_at`
- `details` (optional)

### Notes
- this may be computed on demand rather than stored permanently

## Relationship map

- one **User** owns many **Workspaces**
- one **Workspace** has many **Sessions**
- one **Session** has many **Messages**
- one **Workspace** has many **MemoryItems**
- one **Workspace** has many **SourceDocuments**
- one **Workspace** may later have many **Checkpoints** (V1.1)
- one **Workspace** has one active **ProviderBinding**

## Required V1 invariants

### Workspace invariants
- every session belongs to exactly one workspace
- every memory item belongs to exactly one workspace
- checkpoint ownership rules are deferred to V1.1

### Provider invariants
- one workspace has only one active provider/model at a time
- switching provider must not destroy workspace memory

### Checkpoint invariants
Deferred to V1.1.

### Memory invariants
- memory items remain durable across sessions
- memory items must remain accessible after provider switching

## Boundary with low-level schema

This document defines the **product objects**.

`SCHEMA.md` remains the lower-level storage/index design for:
- memory payload persistence
- full embeddings
- compressed index structures

In practice:
- `MemoryItem` maps to product memory rows
- vector/index tables remain internal implementation detail

## Design rule

The V1 domain model should stay understandable to both product and engineering.

If a concept is not user-visible or not required for feature delivery, keep it out of the domain model and inside internal implementation details.
