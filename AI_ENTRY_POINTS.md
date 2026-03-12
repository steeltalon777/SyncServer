# AI_ENTRY_POINTS

## Server entrypoints
- `main.py` — FastAPI app creation, middleware, router inclusion.

## API layer
- `app/api/routes_sync.py` — sync endpoints.
- `app/api/routes_catalog.py` — catalog read endpoints.
- `app/api/routes_catalog_admin.py` — catalog admin endpoints.
- `app/api/routes_health.py` — health/readiness endpoints.
- `app/api/deps.py` — dependencies (UoW, auth, rate limit, request metadata).

## Service layer
- `app/services/sync_service.py`
- `app/services/event_ingest.py`
- `app/services/catalog_admin_service.py`
- `app/services/uow.py`

## Repository / Data layer
- `app/repos/events_repo.py`
- `app/repos/catalog_repo.py`
- `app/repos/devices_repo.py`
- `app/repos/sites_repo.py`
- `app/repos/balances_repo.py`

## Models / Entities
- `app/models/site.py`
- `app/models/device.py`
- `app/models/event.py`
- `app/models/category.py`
- `app/models/unit.py`
- `app/models/item.py`
- `app/models/balance.py`
- `app/models/user_site_role.py`

## Configuration
- `app/core/config.py`
- `app/core/db.py`
- `.env.example`
- `docker-compose.yml`
- `db/init/001_init_schema.sql`

## Deployment entrypoints

- `docker-compose.yml` — container deployment descriptor
- `db/init/001_init_schema.sql` — schema bootstrap
- `.env` / `.env.example` — runtime configuration
- nginx gateway (external repo/folder in deployment) routes `/api/` to this service