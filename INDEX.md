# Index

## Project Overview
SyncServer is an async backend for warehouse data, inventory operations, site access control, and device synchronization.

## Architecture Overview
- Layered backend: API -> Services -> Repositories -> PostgreSQL
- Token-based auth for users and devices
- Server-side source of truth for warehouse state

## Tech Stack
- Python, FastAPI, Pydantic, SQLAlchemy async, asyncpg, PostgreSQL
- pytest, pytest-asyncio, httpx
- Docker / docker-compose

## Application Structure
- `main.py`
- `app/api/`
- `app/services/`
- `app/repos/`
- `app/models/`
- `app/schemas/`
- `app/core/`
- `docs/`
- `tests/`

## Main Modules
- Auth
- Admin
- Catalog
- Catalog Admin
- Operations
- Balances
- Sync
- Health
- Legacy Business Compatibility

## Entry Points
- `main.py`
- `app/api/routes_*.py`
- `app/services/uow.py`

## Important Models
- `User`
- `UserAccessScope`
- `Site`
- `Device`
- `Category`
- `Item`
- `Unit`
- `Operation`
- `Balance`
- `Event`

## Important Services
- `identity_service`
- `access_service`
- `catalog_admin_service`
- `operations_service`
- `sync_service`

## Future Modules
- More explicit client-specific integration docs
- Stronger separation of legacy compatibility flows
- Broader end-to-end testing around admin and sync integration

## Architecture Decisions
- [0001 SyncServer Source Of Truth](docs/adr/0001-syncserver-source-of-truth.md)
- [0002 Layered Architecture With Unit Of Work](docs/adr/0002-layered-architecture-with-unit-of-work.md)
- [0003 Operation-Driven Inventory And Derived Balances](docs/adr/0003-operation-driven-inventory-and-derived-balances.md)
- [0004 Token Auth And Site-Scoped Access](docs/adr/0004-token-auth-and-site-scoped-access.md)
- [0005 Catalog Hierarchy Via Adjacency List](docs/adr/0005-catalog-hierarchy-via-adjacency-list.md)
- [0006 Idempotent Event Ingest For Device Sync](docs/adr/0006-idempotent-event-ingest-for-device-sync.md)
