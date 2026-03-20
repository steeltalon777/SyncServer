# Memory

## System Architecture
- Async FastAPI backend over PostgreSQL
- Layered structure: API, services, repositories, models
- `UnitOfWork` is the transaction boundary for request workflows

## Core Entities
- `User`
- `UserAccessScope`
- `Site`
- `Device`
- `Category`
- `Item`
- `Unit`
- `Operation` / `OperationLine`
- `Balance`
- `Event`

## Data Model Decisions
- Users authenticate by token, not by session in this service
- Root authority is global; non-root authority is per site
- Catalog entities are global
- Balances are derived from operation history
- Devices participate in sync through event ingestion and pull/push flows

## API Design
- Base prefix is `/api/v1`
- Primary auth is `X-User-Token` and `X-Device-Token`
- Admin and auth endpoints support Django/admin integration flows
- Compatibility APIs remain available but are not the preferred path

## Business Rules
- Operation types: `RECEIVE`, `WRITE_OFF`, `MOVE`
- Operation statuses: `draft`, `submitted`, `cancelled`
- Submit applies balance deltas
- Cancel of a submitted operation rolls back deltas
- Category hierarchy prevents cycles
- Scope flags drive non-root permissions:
  - `can_view`
  - `can_operate`
  - `can_manage_catalog`

## Known Pitfalls
- Legacy compatibility routes can obscure the primary architecture
- Some catalog read endpoints accept `site_id` only as access context, not as true data partitioning
- Tests require a working PostgreSQL test database configuration
- Documentation inventories may drift if routes change without doc updates

## Future Architecture
- Further isolate or retire legacy compatibility flows
- Expand end-to-end test coverage for admin integration
- Keep ADRs current as auth, access, and sync design evolve
