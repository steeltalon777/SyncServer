# INDEX

## Project overview
SyncServer — source of truth backend для распределённой складской системы.

## Architecture overview
Clients → HTTP API → SyncServer (FastAPI) → PostgreSQL.

## Tech stack
Python 3.11, FastAPI, SQLAlchemy Async, PostgreSQL.

## Application structure
- `main.py`
- `app/api`
- `app/services`
- `app/repos`
- `app/models`
- `app/schemas`
- `db/init`
- `tests`

## Main modules
- Sync module (`/ping`, `/push`, `/pull`)
- Catalog read/sync module (`/catalog/*`)
- Catalog admin write module (`/catalog/admin/*`)

## Entry points
- `main.py`
- `app/api/routes_sync.py`
- `app/api/routes_catalog.py`
- `app/api/routes_catalog_admin.py`

## Important models
- `Category`
- `Unit`
- `Item`
- `Event`

## Important services
- `SyncService`
- `CatalogAdminService`
- `UnitOfWork`

## Future modules
- WPF sync client workflows
- Mobile sync workflows
- Offline reconciliation workflows
