# AI Entry Points

## Server Entrypoints
- `main.py` - FastAPI app, middleware, router mounting, global handlers

## API Layer
- `app/api/routes_auth.py`
- `app/api/routes_admin.py`
- `app/api/routes_catalog.py`
- `app/api/routes_catalog_admin.py`
- `app/api/routes_operations.py`
- `app/api/routes_balances.py`
- `app/api/routes_sync.py`
- `app/api/routes_health.py`
- `app/api/routes_business.py` - legacy compatibility
- `app/api/deps.py` - auth and request dependency wiring

## Service Layer
- `app/services/uow.py`
- `app/services/identity_service.py`
- `app/services/access_service.py`
- `app/services/access_guard.py`
- `app/services/catalog_admin_service.py`
- `app/services/operations_service.py`
- `app/services/sync_service.py`
- `app/services/event_ingest.py`

## Repository / Data Layer
- `app/repos/users_repo.py`
- `app/repos/user_access_scopes_repo.py`
- `app/repos/sites_repo.py`
- `app/repos/catalog_repo.py`
- `app/repos/operations_repo.py`
- `app/repos/balances_repo.py`
- `app/repos/events_repo.py`
- `app/repos/devices_repo.py`

## Models / Entities
- `app/models/user.py`
- `app/models/user_access_scope.py`
- `app/models/site.py`
- `app/models/device.py`
- `app/models/category.py`
- `app/models/item.py`
- `app/models/unit.py`
- `app/models/operation.py`
- `app/models/balance.py`
- `app/models/event.py`

## Configuration
- `app/core/config.py`
- `app/core/db.py`
- `.env.example`
- `docker-compose.yml`
- `Dockerfile`
