# SyncServer

SyncServer is a FastAPI backend for warehouse management system, serving as the single source of truth for inventory domain.

## Project overview
- Central backend for warehouse operations and catalog management
- Supports both online (Django web client) and offline (device sync) clients
- PostgreSQL as the single source of truth
- Dual authentication modes: device-based for sync, service-based for web clients

## Architecture overview
`Clients → FastAPI API layer → Services → Repositories → PostgreSQL`

More details: [ARCHITECTURE.md](./ARCHITECTURE.md)

## Tech stack
- Python 3.11
- FastAPI
- Pydantic v2 + pydantic-settings
- SQLAlchemy 2.x (async)
- PostgreSQL
- Pytest + httpx
- Docker / Docker Compose

## Project structure
- `main.py` — application entrypoint with exception handlers
- `app/api/` — HTTP routes + dependencies
- `app/services/` — business logic + unit of work
- `app/repos/` — data access layer
- `app/models/` — SQLAlchemy ORM entities
- `app/schemas/` — request/response contracts
- `app/core/` — settings + DB session factory
- `db/init/` — SQL bootstrap schema
- `docs/adr/` — architecture decisions
- `tests/` — API and service/repository tests

## Installation / Setup
