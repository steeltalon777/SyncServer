# ARCHITECTURE

## Layers
Clients -> FastAPI routes -> Services -> Repositories -> PostgreSQL

## Responsibilities
- API: HTTP contracts, auth, access checks, validation mapping.
- Services: domain behavior, invariants, workflows.
- Repositories: persistence and query composition only.

## Identity and Access
- User identity: `X-User-Token`
- Device identity: `X-Device-Token`
- Root model: `User.is_root` (global)
- Scoped model: `UserAccessScope` per site
  - `can_view`
  - `can_operate`
  - `can_manage_catalog`

## Domain Invariants
- SyncServer is the only source of truth for warehouse state.
- Clients do not own business logic.
- Balances are derived from operations.
- Operation statuses: `draft -> submitted -> cancelled`.
- Submitting applies deltas; cancelling submitted operations rolls back.

## Operation Types (current runtime)
- `RECEIVE`
- `WRITE_OFF`
- `MOVE`

## Legacy Notes
- `UserSiteRole` artifacts are retained only as deprecated compatibility code.
- Compatibility APIs exist under `/business/*` and legacy POST catalog reads.
- New integrations should use token-based APIs from `docs/API_REFERENCE.md`.
