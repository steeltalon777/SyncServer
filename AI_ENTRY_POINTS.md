# AI_ENTRY_POINTS

## Boot
- `main.py` — routers, middleware, global handlers.

## Core API Routes
- `app/api/routes_auth.py`
- `app/api/routes_admin.py`
- `app/api/routes_catalog.py`
- `app/api/routes_catalog_admin.py`
- `app/api/routes_operations.py`
- `app/api/routes_balances.py`
- `app/api/routes_sync.py`
- `app/api/routes_business.py` (legacy compatibility)

## Auth/Deps
- `app/api/deps.py`
- `app/core/identity.py`
- `app/services/identity_service.py`

## Services
- `app/services/access_service.py`
- `app/services/access_guard.py`
- `app/services/catalog_admin_service.py`
- `app/services/operations_service.py`
- `app/services/sync_service.py`

## Repositories
- `app/repos/user_access_scopes_repo.py`
- `app/repos/users_repo.py`
- `app/repos/sites_repo.py`
- `app/repos/catalog_repo.py`
- `app/repos/operations_repo.py`
- `app/repos/balances_repo.py`
- `app/repos/devices_repo.py`

## Models
- `app/models/user.py`
- `app/models/user_access_scope.py`
- `app/models/site.py`
- `app/models/device.py`
- `app/models/operation.py`
- `app/models/balance.py`
