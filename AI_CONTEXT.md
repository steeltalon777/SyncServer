# AI_CONTEXT

## Product Truth
- SyncServer is the source of truth for warehouse domain state.
- Domain rules belong on server side, not in clients.

## Current Auth Model
- Primary user auth: `X-User-Token`.
- Device auth: `X-Device-Token` (sync/device context).
- Legacy `Authorization + X-Acting-*` paths are compatibility-only.

## Current Access Model
- Root authority: `User.is_root`.
- Scoped authority: `UserAccessScope` by site.
- Scope flags:
  - `can_view`
  - `can_operate`
  - `can_manage_catalog`

## Domain Rules
- Supported operation types in runtime: `RECEIVE`, `WRITE_OFF`, `MOVE`.
- Operation lifecycle: `draft -> submitted -> cancelled`.
- Submit applies balance deltas.
- Cancel on submitted operation rolls deltas back.

## Integration Orientation
- Use `docs/API_REFERENCE.md` for endpoint contracts.
- Use `docs/ENDPOINT_INVENTORY.md` for full test/wiring list.
