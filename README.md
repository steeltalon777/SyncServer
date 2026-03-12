# SyncServer

SyncServer is a FastAPI backend for offline/online data synchronization and catalog management in a distributed inventory domain.

## Project overview
- Receives device events (`/push`) and stores them as an ordered server log.
- Returns events by cursor (`/pull`) so clients can catch up.
- Exposes catalog read endpoints and catalog admin endpoints.
- Uses PostgreSQL as the single source of truth.

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
- `main.py` — application entrypoint.
- `app/api/` — HTTP routes + dependencies.
- `app/services/` — business logic + unit of work.
- `app/repos/` — data access layer.
- `app/models/` — SQLAlchemy ORM entities.
- `app/schemas/` — request/response contracts.
- `app/core/` — settings + DB session factory.
- `db/init/` — SQL bootstrap schema.
- `docs/adr/` — architecture decisions.
- `tests/` — API and service/repository tests.

## Installation / Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set at least `DATABASE_URL` in `.env`.

## Running the project
```bash
uvicorn main:app --reload
```
## Container deployment (current production-style setup)

SyncServer is deployed inside a shared external Docker network and is usually accessed
through an nginx reverse proxy, not directly from the Internet.

### Network model

Services connected to the shared Docker network:

- `syncserver`
- `warehouse_web`
- `nginx_gateway`

External Docker network name:

backend
backend
Internal service address

Other containers must connect to SyncServer by service name:

http://syncserver:8000

Do not use 127.0.0.1 from other containers, because inside Docker that points to the container itself.

Reverse proxy model

Typical ingress flow:

Browser
  ↓
nginx gateway
  ↓
/api/ → SyncServer

In this deployment model SyncServer does not need a public host port exposed.
or

```bash
docker compose up --build
```

## Main modules
- Sync: `/ping`, `/push`, `/pull`
- Catalog read: `/catalog/items`, `/catalog/categories`, `/catalog/units`, `/catalog/categories/tree`
- Catalog admin: `/catalog/admin/*` for unit/category/item create/update
- Health: `/health`, `/ready`, `/db_check`

## API overview
See [API_CONTRACT.md](./API_CONTRACT.md).
