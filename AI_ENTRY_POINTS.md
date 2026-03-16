# AI_ENTRY_POINTS

## Application boot
- `main.py` - FastAPI app, middleware, exception handler, router registration.

## API layer
- `app/api/routes_admin.py`
- `app/api/routes_catalog_admin.py`
- `app/api/routes_operations.py`
- `app/api/routes_balances.py`
- `app/api/deps.py`

## Service layer
- `app/services/operations_service.py`
- `app/services/catalog_admin_service.py`
- `app/services/access_service.py`
- `app/services/uow.py`

## Repository layer
- `app/repos/operations_repo.py`
- `app/repos/balances_repo.py`
- `app/repos/catalog_repo.py`
- `app/repos/sites_repo.py`
- `app/repos/users_repo.py`
- `app/repos/user_site_roles_repo.py`

## Domain models
- `app/models/operation.py`
- `app/models/balance.py`
- `app/models/item.py`
- `app/models/site.py`
- `app/models/user.py`

## Config
- `app/core/config.py`
- `app/core/db.py`
- `.env.example`
