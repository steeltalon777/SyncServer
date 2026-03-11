# ARCHITECTURE

## System Overview
SyncServer is a standalone backend service that synchronizes device events and serves catalog data. The service persists all operational state in PostgreSQL.

## High-Level Architecture
```text
Clients
  ↓
API / Application Layer (FastAPI)
  ↓
Service Layer
  ↓
Repository / Data Layer
  ↓
Database (PostgreSQL)
```

## Application Layers
### API layer
- `main.py` boots FastAPI, middleware, and routers.
- `app/api/routes_*.py` define HTTP endpoints.
- `app/api/deps.py` handles auth checks, request context, rate limit, UoW wiring.

### Service layer
- `SyncService` orchestrates push processing.
- `EventIngestService` enforces idempotency and collision rules.
- `CatalogAdminService` enforces catalog business validations.
- `UnitOfWork` controls transaction boundaries.

### Repository layer
- `EventsRepo`, `CatalogRepo`, `DevicesRepo`, `SitesRepo`, `BalancesRepo` encapsulate SQLAlchemy queries.

### Models / entities
- Core ORM models: `Site`, `Device`, `Event`, `Category`, `Unit`, `Item`, `Balance`, `UserSiteRole`.

## Data Model
- Event log model: `events` with `event_uuid` PK, `server_seq` monotonic cursor, `payload_hash` for idempotency.
- Catalog model: `categories` (adjacency list via `parent_id`), `items`, `units`.
- Access model: `sites`, `devices`, `user_site_roles`.
- Operational aggregate: `balances` by `(site_id, item_id)`.

## Data Flow
### Sync flow
Client → `POST /push` → auth + rate-limit → `SyncService` → `EventIngestService` → `EventsRepo` → DB commit.

### Pull flow
Client → `POST /pull` → auth → `EventsRepo.pull(site_id, since_seq, limit)` → ordered events by `server_seq`.

### Catalog admin flow
Client → `/catalog/admin/*` → `CatalogAdminService` validations → `CatalogRepo` write.

## Architectural Principles
- Layered separation (API/service/repository/model).
- Single transactional boundary per request through `UnitOfWork`.
- Idempotent ingest with explicit collision classification.
- Soft deactivation (`is_active`) for catalog entities.

## External Integrations
- PostgreSQL via async SQLAlchemy engine.
- No outbound third-party APIs in runtime code.

## Future Architecture
- Replace in-memory rate limiter with distributed/shared limiter for multi-instance deployments.
- Add managed DB migrations (e.g., Alembic).
- Resolve schema drift between SQL bootstrap and ORM for `user_site_roles`.
