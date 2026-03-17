# API_CONTRACT

Canonical client contract is maintained in:
- `docs/API_REFERENCE.md`
- `docs/ENDPOINT_INVENTORY.md`

## Current Contract Principles
- Primary auth is token-based:
  - `X-User-Token`
  - `X-Device-Token` (device/sync context)
- Access is evaluated server-side via `User.is_root` + `UserAccessScope`.
- Business logic remains server-side.

## Compatibility Note
Legacy service/acting-user flows are compatibility-only and not the primary integration model.
Use the token-based API paths for all new clients.
