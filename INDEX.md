# INDEX

## Project overview
SyncServer is an async FastAPI backend for event synchronization and catalog management over PostgreSQL.

## Architecture overview
`Clients → API layer → Service layer → Repository layer → PostgreSQL`

## Authentication Overview
### Device Authentication (Sync Clients)
- **Purpose**: Authenticate WPF offline clients, sync devices
- **Headers**: `X-Device-Token`, `X-Site-Id`, `X-Device-Id`
- **Endpoints**: `/sync/*` exclusively

### Service Authentication (Django Web Client)
- **Purpose**: Authenticate trusted internal services
- **Headers**: `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>` + `X-Acting-User-Id`, `X-Acting-Site-Id`
- **Endpoints**: `/business/*`, `/catalog/*` (dual-mode)

## Deployment overview
- Typically deployed inside shared Docker network `backend`
- Usually accessed through nginx reverse proxy
- Common public route: `/api/` → SyncServer
- Warehouse_web (Django) calls SyncServer internally by `http://syncserver:8000`

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
- Sync module (`/ping`, `/push`, `/pull`) - device auth only
- Catalog read module (`/catalog/*`) - dual authentication
- Business API module (`/business/catalog/*`) - service auth only
- Catalog admin module (`/catalog/admin/*`)
- Health module (`/health`, `/ready`, `/db_check`)

## Authentication Modules
### Device Authentication (`app/api/deps.py`)
- `require_device_auth()` - validates device registration
- `auth_catalog_headers()` - collects device headers

### Service Authentication (`app/api/deps.py`)
- `require_service_auth()` - validates service token
- `require_acting_user()` - validates user context
- `auth_service_headers()` - collects service headers

### Repositories
- `user_site_roles_repo.py` - user-site access control (new)
- `devices_repo.py` - device management

## Entry points
- Runtime: `main.py`
- Router registration: `main.py` + `app/api/routes_*.py`
- New router: `app/api/routes_business.py`

## Important models
`Event`, `Device`, `Site`, `Category`, `Unit`, `Item`, `Balance`, `UserSiteRole`.

## Important services
`SyncService`, `EventIngestService`, `CatalogAdminService`, `UnitOfWork`.

## Configuration
- `SYNC_SERVER_SERVICE_TOKEN` in `app/core/config.py`
- Set in `.env` for Django integration

## Future modules
- Distributed rate limiter.
- DB migration tooling.
- Reconciliation/conflict workflows for offline clients.
- Audit logging for service authentication.

## Architecture decisions
- [ADR-0001 Layered architecture](./docs/adr/0001-layered-architecture-fastapi-service-repository-uow.md)
- [ADR-0002 Idempotent event ingest](./docs/adr/0002-idempotent-event-ingest-event-uuid-payload-hash.md)
- [ADR-0003 Catalog hierarchy model](./docs/adr/0003-catalog-hierarchy-adjacency-list-and-cycle-checks.md)
- [ADR-0004 Soft deactivation](./docs/adr/0004-soft-deactivation-via-is-active.md)
- **New**: Dual authentication modes (device + service)
