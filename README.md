# SyncServer

SyncServer is the backend source of truth for warehouse data: users, site access, catalog, operations, balances, and device sync events.

## Project Overview
- Backend API for warehouse workflows and synchronization.
- Stores authoritative business state in PostgreSQL.
- Exposes token-based HTTP APIs for user clients, admin clients, and device sync clients.

## Architecture Overview
Clients call FastAPI routes, routes validate/authenticate requests, services enforce business rules, repositories load/store state, and PostgreSQL remains the authoritative datastore.

Core flow:

`Client -> API routes -> Services -> Repositories -> PostgreSQL`

## Tech Stack
- Python
- FastAPI / Starlette
- Pydantic v2
- SQLAlchemy 2 async
- asyncpg
- PostgreSQL
- httpx + pytest + pytest-asyncio
- Docker / docker-compose

## Project Structure
```text
main.py                  FastAPI app composition and router mounting
app/api/                 HTTP routes, dependencies, exception mapping
app/services/            Business logic and orchestration
app/repos/               Database access layer
app/models/              SQLAlchemy ORM models
app/schemas/             Request / response DTOs
app/core/                Settings, DB wiring, identity helpers
db/init/                 Initial SQL schema
docs/                    API docs, ADRs, inventories
tests/                   Async integration and repository tests
scripts/                 Bootstrap and migration helpers
```

## Installation / Setup
1. Copy `.env.example` to `.env` and fill database / token settings.
2. Install dependencies: `pip install -r requirements.txt`
3. Ensure PostgreSQL is available.

Alternative container setup:
1. Configure `.env`
2. Run `docker compose up --build`

## Running The Project
- Local dev: `uvicorn main:app --reload`
- Docker: `docker compose up --build`
- OpenAPI docs: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`
- Existing databases: after expanding supported operation types, run `python scripts/migrate_operation_constraints.py` once to refresh operation check constraints.

## Database Migrations
- Fresh database: `python -m alembic upgrade head`
- Existing database that already matches the current schema baseline: `python -m alembic stamp head`
- Alembic reads the connection string from `.env` through `app.core.config`, so `DATABASE_URL` remains the single source of truth.

## Main Modules
- `auth` - user bootstrap, session context, available sites
- `admin` - users, sites, scopes, devices, roles
- `catalog` - read APIs for items, categories, units, sites
- `catalog/admin` - catalog mutations
- `operations` - warehouse operation lifecycle
- `balances` - read-only inventory balances
- `sync` - device event synchronization
- `health` - health and readiness

## API Overview
Base prefix: `/api/v1`

Primary auth:
- `X-User-Token`
- `X-Device-Token`

Primary documentation:
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- [docs/ENDPOINT_INVENTORY.md](docs/ENDPOINT_INVENTORY.md)

## Canonical Architecture Docs
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [INDEX.md](INDEX.md)
- [AI_CONTEXT.md](AI_CONTEXT.md)
- [AI_ENTRY_POINTS.md](AI_ENTRY_POINTS.md)
- [MEMORY.md](MEMORY.md)
