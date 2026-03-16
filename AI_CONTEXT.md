# AI_CONTEXT

## SyncServer invariants
- SyncServer is the single source of truth for warehouse domain data.
- Clients must not implement business logic.
- Warehouse state is derived from operations.

## Layering rules
- API layer: validation, request parsing, auth checks, HTTP mapping.
- Services: business logic and orchestration.
- Repositories: database access only.
- Models: ORM mapping and constraints.

## Operations rules
- Types: `RECEIVE`, `WRITE_OFF`, `MOVE`.
- Workflow: `draft -> submitted -> cancelled`.
- Only submission changes balances.
- Cancelling submitted operations must rollback deltas.

## Balance validation
- WRITE_OFF requires sufficient stock at operation site.
- MOVE requires sufficient stock at source site.
- MOVE target site must exist.
- RECEIVE is always allowed.
