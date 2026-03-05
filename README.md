# Server Sync API

Backend skeleton for sync domain in FastAPI:
- SQLAlchemy ORM models for existing PostgreSQL tables managed by Django migrations.
- Pydantic DTO layer for sync and catalog contracts.
- Async repositories and transaction-oriented services (Unit of Work + idempotent ingest).
- Integration tests for event idempotency and pull ordering.

## Scope of this repository

Implemented in this stage:
- Data model and persistence layer.
- DTO contracts.
- Repository contracts.
- Transaction and idempotency workflow.
- Test coverage for model-level behavior.

Not implemented in this stage:
- Production business endpoints (`/push`, `/pull`, `/catalog`, `/ping`) and auth.

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
- Database schema is expected to be migrated by Django in production.

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

## Test strategy

Tests in `tests/test_events_repo.py` verify:
- DB smoke check.
- Event insert returns `server_seq` after `flush`.
- Duplicate detection (`same event_uuid + same payload`).
- UUID collision detection (`same event_uuid + different payload`).
- Pull ordering and filtering by `(site_id, since_seq)`.
- Batch classification using `SyncService`.

Run tests:

```bash
pytest -q
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
- TZ compliance report: `docs/tz-gap-analysis.md`
