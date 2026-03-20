# ADR-0001: SyncServer Source Of Truth

## Status
Accepted

## Context
The repository stores warehouse state, catalog data, access scopes, operations, balances, and sync events in one backend. Multiple clients integrate with this backend and need a single authoritative domain source.

## Decision
SyncServer is the source of truth for warehouse domain state. Clients send commands and read server-owned data; they do not own business invariants.

## Consequences

Pros:
- Centralized business logic
- Consistent state across clients
- Easier auditing of inventory behavior

Cons:
- Clients depend on API availability
- Server-side changes must be documented carefully

## Alternatives Considered

### Option 1
Let each client own part of the domain state.

Why not chosen:
- Would fragment business rules and create reconciliation complexity.

### Option 2
Use SyncServer only as a pass-through integration layer.

Why not chosen:
- Conflicts with current repository structure and operation-driven inventory logic.
