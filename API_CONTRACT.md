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
- Use the documented token-based API paths for all clients.
