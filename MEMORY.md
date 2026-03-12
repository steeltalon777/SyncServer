# MEMORY

## System architecture
- Async FastAPI service with strict API → service → repository separation.
- Per-request transaction boundary through `UnitOfWork`.
- PostgreSQL stores both sync event log and catalog domain data.
- Dual authentication modes: device auth for sync, service auth for web clients.

## Core entities
- `Site`: tenant-like warehouse/site context.
- `Device`: authenticated sync client bound to site.
- `Event`: append-only sync log with monotonic `server_seq`.
- `Category`, `Unit`, `Item`: catalog entities.
- `Balance`: quantity snapshot by `(site_id, item_id)`.
- `UserSiteRole`: user-site-role mapping for access control.

## Data model decisions
- UUID-based keys across domain entities.
- Event idempotency: `event_uuid` + `payload_hash`.
- Category hierarchy: adjacency list (`parent_id`) with service-level cycle checks.
- Catalog records use `is_active` for soft deactivation.
- User access: `user_site_roles` table with `(user_id, site_id, role)` unique constraint.

## Authentication Architecture
### Device Authentication
- Purpose: Authenticate sync devices (WPF clients, offline devices).
- Headers: `X-Device-Token`, `X-Site-Id`, `X-Device-Id`.
- Validation: Checks device registration, site binding, device activity.
- Endpoints: `/sync/*` exclusively, `/catalog/*` (legacy support).

### Service Authentication
- Purpose: Authenticate trusted internal services (Django web client).
- Header: `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>`.
- Acting user context: `X-Acting-User-Id`, `X-Acting-Site-Id`.
- Validation: Service token + user-site access verification.
- Endpoints: `/business/*`, `/catalog/*` (dual-mode).

## API design
- Sync API: `/ping`, `/push`, `/pull` (device auth only).
- Catalog read API: `/catalog/items|categories|units`, `/catalog/categories/tree` (dual auth).
- Business API: `/business/catalog/*` (service auth only).
- Catalog admin API: `/catalog/admin/*` create/update only.

## Business rules
- `/push` classifies incoming events as accepted / duplicate / uuid collision.
- Device token and site-device match are mandatory for sync endpoints.
- Service token validation is required for business endpoints.
- User must have `user_site_roles` entry to access a site.
- Unit name/symbol and item SKU are uniqueness-constrained.
- Category names are unique within the same parent.

## Known pitfalls
- In-memory rate limiter is not distributed.
- SQL bootstrap and ORM differ for `user_site_roles` shape.
- No migration framework configured in repository.
- Service token (`SYNC_SERVER_SERVICE_TOKEN`) must be configured for Django integration.

## Future architecture
- Introduce distributed rate-limit storage.
- Adopt migration tooling for schema evolution.
- Add reconciliation workflows for long-offline clients.
- Add audit logging for service authentication requests.

## Deployment notes
- In Docker deployment, `127.0.0.1` from another container does not reach SyncServer.
- Cross-container access must use `http://syncserver:8000`.
- Reverse proxy deployments should route `/api/` to SyncServer instead of exposing SyncServer as the main public entrypoint.
- Database bootstrap is required before first use:
  - apply `db/init/001_init_schema.sql`
  - create `site`
  - create `device`
  - create `registration_token`
  - create `user_site_roles` entries for web users
- Device/site IDs and registration token must match real bootstrap data, not placeholder strings.
- Service token must be shared between SyncServer and Django web client.
