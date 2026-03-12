# INDEX

## Project overview
SyncServer is an async FastAPI backend for event synchronization and catalog management over PostgreSQL.

## Architecture overview
`Clients → API layer → Service layer → Repository layer → PostgreSQL`

## Deployment overview
- Typically deployed inside shared Docker network `backend`
- Usually accessed through nginx reverse proxy
- Common public route: `/api/` → SyncServer
- Warehouse_web web client calls SyncServer internally by `http://syncserver:8000`

## Tech stack
Python 3.11, FastAPI, SQLAlchemy Async, Pydantic v2, PostgreSQL, Pytest, Docker.

## Application structure
- API: `app/api/`
- Services: `app/services/`
- Repositories: `app/repos/`
- Models: `app/models/`
- Schemas: `app/schemas/`
- Infrastructure: `app/core/`, `db/init/`

## Main modules
- Sync module (`/ping`, `/push`, `/pull`)
- Catalog read module (`/catalog/*`)
- Catalog admin module (`/catalog/admin/*`)
- Health module (`/health`, `/ready`, `/db_check`)

## Entry points
- Runtime: `main.py`
- Router registration: `main.py` + `app/api/routes_*.py`

## Important models
`Event`, `Device`, `Site`, `Category`, `Unit`, `Item`, `Balance`, `UserSiteRole`.

## Important services
`SyncService`, `EventIngestService`, `CatalogAdminService`, `UnitOfWork`.

## Future modules
- Distributed rate limiter.
- DB migration tooling.
- Reconciliation/conflict workflows for offline clients.

## Architecture decisions
- [ADR-0001 Layered architecture](./docs/adr/0001-layered-architecture-fastapi-service-repository-uow.md)
- [ADR-0002 Idempotent event ingest](./docs/adr/0002-idempotent-event-ingest-event-uuid-payload-hash.md)
- [ADR-0003 Catalog hierarchy model](./docs/adr/0003-catalog-hierarchy-adjacency-list-and-cycle-checks.md)
- [ADR-0004 Soft deactivation](./docs/adr/0004-soft-deactivation-via-is-active.md)
