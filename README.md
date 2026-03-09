# Server Sync API

Backend service for sync domain in FastAPI:
- SQLAlchemy ORM models and explicit PostgreSQL bootstrap schema (`db/init/001_init_schema.sql`).
- Pydantic DTO layer for sync and catalog contracts.
- Async repositories and transaction-oriented services (Unit of Work + idempotent ingest).
- Integration tests for event idempotency and pull ordering.

## Scope of this repository

Implemented in this stage:
- Data model and persistence layer.
- DTO contracts.
- Repository contracts.
- Transaction and idempotency workflow.
- HTTP API layer: `/ping`, `/push`, `/pull`, `/catalog/items`, `/catalog/categories`.
- Device auth via `X-Device-Token` + site/device binding.
- Health/readiness endpoints and request correlation ID header.
- Integration tests for repository and HTTP behavior.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x (async)
- asyncpg
- Pydantic v2
- pytest + pytest-asyncio

## Project structure

```text
app/
  core/
    config.py
    db.py
  models/
    base.py
    site.py
    device.py
    category.py
    item.py
    event.py
    balance.py
    user_site_role.py
  schemas/
    common.py
    sync.py
    catalog.py
  repos/
    sites_repo.py
    devices_repo.py
    events_repo.py
    balances_repo.py
    catalog_repo.py
  services/
    uow.py
    event_ingest.py
    sync_service.py
main.py
tests/
  conftest.py
  test_events_repo.py
docs/
  code-documentation.md
  tz-gap-analysis.md
```

## Environment

Create `.env` from `.env.example`:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname
DATABASE_URL_TEST=postgresql+asyncpg://user:password@localhost:5432/dbname_test
APP_ENV=dev
LOG_LEVEL=INFO
```

Notes:
- `DATABASE_URL_TEST` is used by tests. If missing, tests fallback to `DATABASE_URL`.
- For local Docker startup, PostgreSQL schema is initialized from `db/init/001_init_schema.sql`.


## API audit snapshot

Implemented and wired routes:
- Sync: `POST /ping`, `POST /push`, `POST /pull`
- Catalog: `POST /catalog/items`, `POST /catalog/categories`
- Service checks: `GET /`, `GET /health`, `GET /ready`, `GET /db_check`

Auth expectations:
- `/ping`, `/push`, `/pull`: `X-Device-Token`
- `/catalog/*`: `X-Site-Id`, `X-Device-Id`, `X-Device-Token`

## Run

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Available technical endpoints:
- `GET /`
- `GET /db_check`
- `GET /health`
- `GET /ready`

## Test strategy

Tests in `tests/test_events_repo.py` verify:
- DB smoke check.
- Event insert returns `server_seq` after `flush`.
- Duplicate detection (`same event_uuid + same payload`).
- UUID collision detection (`same event_uuid + different payload`).
- Pull ordering and filtering by `(site_id, since_seq)`.
- Batch classification using `SyncService`.

Tests in `tests/test_http_sync.py` verify:
- `POST /ping` auth success.
- `POST /push` accepted/duplicate/collision classification.
- `POST /pull` ordering by `server_seq`.
- Incremental catalog sync.
- Auth failure on bad token.

Run tests:

```bash
pytest -q
```

## Docker (dev)

```bash
docker compose up --build
```

## Key design decisions

1. No schema creation on app startup.
2. `events.server_seq` comes from DB identity/sequence behavior.
3. Idempotency rule:
   - missing `event_uuid` -> insert
   - existing with same payload hash -> duplicate
   - existing with different payload hash -> uuid_collision
4. Repositories only encapsulate data access; orchestration is in services.
5. `UnitOfWork` controls transaction boundaries.

## Additional docs

- Detailed module reference: `docs/code-documentation.md`
- Client development specification (TZ): `docs/client-development-tz.md`
- TZ compliance report: `docs/tz-gap-analysis.md`
