# MEMORY

## Stable Decisions
- SyncServer is the single source of truth.
- Access model is `User.is_root` + `UserAccessScope`.
- Primary request auth is token-based (`X-User-Token`, `X-Device-Token`).

## Access Semantics
- `root`: global access.
- non-root access is site-scoped and flag-driven:
  - `can_view`
  - `can_operate`
  - `can_manage_catalog`

## Operations Semantics
- Supported types: `RECEIVE`, `WRITE_OFF`, `MOVE`.
- Statuses: `draft`, `submitted`, `cancelled`.
- Submit mutates balances.
- Cancel of submitted operation performs rollback.

## API Posture
- Primary routes are token-based.
- Legacy compatibility routes still exist for transitional clients.
- Endpoint inventory lives in `docs/ENDPOINT_INVENTORY.md`.
