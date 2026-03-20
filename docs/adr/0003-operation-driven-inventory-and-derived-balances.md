# ADR-0003: Operation-Driven Inventory And Derived Balances

## Status
Accepted

## Context
Warehouse inventory changes come from user operations such as receive, write-off, and move. The system also exposes balances for read scenarios.

## Decision
Treat operations as the primary write model for inventory. Balances are a derived projection of current stock state, updated from valid operation submission and rollback behavior rather than edited as an independent source of truth.

Explicit domain rules:
- `operations` are the source of truth for inventory movement.
- `balances` are a derived read/write projection of the latest stock state.
- `balances` are updated only on valid `submit` / `cancel` transitions.
- `ADJUSTMENT` is a delta operation, not an absolute set of stock to a target value.
- UI clients must read balances from SyncServer and must not recompute stock independently from the operation journal.

## Consequences

Pros:
- Traceable inventory history
- Clear lifecycle for state mutation
- Supports rollback semantics on cancellation
- Keeps all clients aligned on one stock state contract

Cons:
- Balance correctness depends on operation workflow integrity
- More logic is needed around submit/cancel transitions

## Alternatives Considered

### Option 1
Edit balances directly as the primary write model.

Why not chosen:
- Would weaken auditability and rollback safety.

### Option 2
Keep operations only as a reporting layer.

Why not chosen:
- Conflicts with current services and balance update design.
