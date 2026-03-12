# AI_ENTRY_POINTS

## Server entrypoints
- `main.py` — FastAPI app creation, middleware, router inclusion.

## API layer
- `app/api/routes_sync.py` — sync endpoints (device auth only).
- `app/api/routes_catalog.py` — catalog read endpoints (dual auth).
- `app/api/routes_business.py` — business API endpoints (service auth only).
- `app/api/routes_catalog_admin.py` — catalog admin endpoints.
- `app/api/routes_health.py` — health/readiness endpoints.
- `app/api/deps.py` — dependencies (UoW, auth, rate limit, request metadata).

## Authentication entrypoints
### Device Authentication
- `require_device_auth()` — validates device token, site-device binding, device activity.
- `auth_catalog_headers()` — collects device auth headers for catalog endpoints.
- Used by: `/sync/*`, `/catalog/*` (legacy mode).

### Service Authentication
- `require_service_auth()` — validates service token (`SYNC_SERVER_SERVICE_TOKEN`).
- `require_acting_user()` — validates acting user context and site access.
- `auth_service_headers()` — collects service auth headers.
- Used by: `/business/*`, `/catalog/*` (service mode).

## Service layer
- `app/services/sync_service.py`
- `app/services/event_ingest.py`
- `app/services/catalog_admin_service.py`
- `app/services/uow.py` — includes `user_site_roles` repository.
## Repository / Data layer
- `app/repos/events_repo.py`
- `app/repos/catalog_repo.py`
- `app/repos/devices_repo.py`
- `app/repos/sites_repo.py`
- `app/repos/balances_repo.py`
- `app/repos/user_site_roles_repo.py` — new repository for user-site access control.

## Models / Entities
- `app/models/site.py`
- `app/models/device.py`
- `app/models/event.py`
- `app/models/category.py`
- `app/models/unit.py`
- `app/models/item.py`
- `app/models/balance.py`
- `app/models/user_site_role.py` — user-site-role mapping for access control.
## Configuration
- `app/core/config.py` — includes `SYNC_SERVER_SERVICE_TOKEN` setting.
- `app/core/db.py`
- `.env.example` — environment template (do not edit directly).
- `docker-compose.yml`
- `db/init/001_init_schema.sql`

## Deployment entrypoints
- `docker-compose.yml` — container deployment descriptor
- `db/init/001_init_schema.sql` — schema bootstrap
- `.env` / `.env.example` — runtime configuration
- nginx gateway (external repo/folder in deployment) routes `/api/` to this service

## Authentication Configuration
- Device auth: Configured via device registration in database.
- Service auth: Set `SYNC_SERVER_SERVICE_TOKEN` environment variable.
- User access: Managed via `user_site_roles` table entries.
