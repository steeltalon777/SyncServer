# ADR-0003: Operation-Driven Inventory And Derived Balances

## Status
Accepted

## Context
Warehouse inventory changes come from user operations such as receive, write-off, and move. The system also exposes balances for read scenarios.

## Decision
Treat operations as the primary write model for inventory. Balances are derived state, updated from operation submission and rollback behavior rather than edited as an independent source of truth.

## Consequences

Pros:
- Traceable inventory history
- Clear lifecycle for state mutation
- Supports rollback semantics on cancellation

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
