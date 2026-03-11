# INDEX

## Project overview
SyncServer — backend синхронизации складских данных, который централизует запись событий и каталог в PostgreSQL.

## Architecture overview
Классическая layered architecture:
**Clients → API (FastAPI) → Services → Repositories → PostgreSQL**.

## Tech stack
Python 3.11, FastAPI, SQLAlchemy Async, PostgreSQL, Pydantic, Pytest, Docker.

## Application structure
- `main.py`
- `app/core/`
- `app/api/`
- `app/services/`
- `app/repos/`
- `app/models/`
- `app/schemas/`
- `db/init/`
- `tests/`
- `docs/adr/`

## Main modules
- Sync API (`/ping`, `/push`, `/pull`)
- Catalog read API (`/catalog/*`)
- Catalog admin API (`/catalog/admin/*`)
- Health/readiness endpoints

## Entry points
- `main.py`
- `app/api/routes_sync.py`
- `app/api/routes_catalog.py`
- `app/api/routes_catalog_admin.py`
- `app/api/routes_health.py`

## Important models
- `Event`
- `Device`
- `Site`
- `Category`
- `Unit`
- `Item`
- `Balance`

## Important services
- `SyncService`
- `EventIngestService`
- `CatalogAdminService`
- `UnitOfWork`

## Future modules
- Масштабируемый distributed rate limiting.
- Отдельные bounded contexts при росте системы.
- Расширение модулей reconciliation/offline conflict resolution.

## Architecture decisions
- [ADR-0001: Layered architecture with FastAPI + Service + Repository + UoW](docs/adr/0001-layered-architecture-fastapi-service-repository-uow.md)
- [ADR-0002: Event log with idempotent ingest by event_uuid + payload_hash](docs/adr/0002-idempotent-event-ingest-event-uuid-payload-hash.md)
- [ADR-0003: Catalog hierarchy via adjacency list and application-level cycle checks](docs/adr/0003-catalog-hierarchy-adjacency-list-and-cycle-checks.md)
- [ADR-0004: Soft deactivation for catalog entities via is_active](docs/adr/0004-soft-deactivation-via-is-active.md)
