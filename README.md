# SyncServer

Quartermaster — система складского учёта. Этот компонент: authoritative backend.

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
2. Build image: `docker compose build`
3. Run migrations in a separate container: `docker compose run --rm migrate`
4. Start web service: `docker compose up -d syncserver`

## Running The Project
- Local dev: `uvicorn main:app --reload`
- Docker: first `docker compose run --rm migrate`, then `docker compose up -d syncserver`
- OpenAPI docs: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`
- SyncServer no longer runs Alembic inside the web process; apply migrations as a separate step before starting the API container.
- Existing databases: after expanding supported operation types, run `python scripts/migrate_operation_constraints.py` once to refresh operation check constraints.

## Database Migrations
- `scripts/bootstrap_root.py` now runs migrations before seeding bootstrap data
- `scripts/bootstrap_root.py` still returns the bootstrap root token and bootstrap Django device token
- Fresh database manual path: `python -m alembic upgrade head`
- Existing database that already matches the current schema baseline: `python -m alembic stamp head`
- Alembic reads the connection string from `.env` through `app.core.config`, so `DATABASE_URL` remains the single source of truth.
- Container deployment flow is documented in [docs/CONTAINER_DEPLOY.md](docs/CONTAINER_DEPLOY.md).

## Main Modules
- `auth` - user bootstrap, session context, available sites, audit endpoint
- `admin` - users, sites, scopes, devices, roles, audit log viewer
- `catalog` - read APIs for items, categories, units, sites
- `catalog/admin` - catalog mutations
- `operations` - warehouse operation lifecycle
- `balances` - read-only inventory balances
- `sync` - device event synchronization
- `health` - health and readiness

## Utility Scripts

### `scripts/query_audit.py`
Query audit events for a user by username or token.

```bash
# By username (recommended)
docker compose exec syncserver python scripts/query_audit.py --username ivanov --console

# By token (when username unknown)
docker compose exec syncserver python scripts/query_audit.py --token <UUID> --console

# Filter by event type and date range
docker compose exec syncserver python scripts/query_audit.py --username ivanov \
  --event-type operation.submit --date-from 2026-06-01 --console

# JSON output for piping
docker compose exec syncserver python scripts/query_audit.py --username ivanov \
  --format json --console | jq .
```

See [docs/audit-query-examples.md](docs/audit-query-examples.md) for full documentation.

## Audit journal (TZ-AUDIT_BACKEND_FOUNDATION / ADR-0018)

The audit surface is **append-only** and consists of three tables:

| Table | Purpose |
|---|---|
| `audit_events` | Spanning event log. v2 fields (`event_version`, `outcome`, `correlation_id`, `parent_event_id`, `source_client`, `actor_username_snapshot`, plus Phase 2 hooks `credential_kind` / `credential_fingerprint` / `external_event_id`). |
| `audit_event_resources` | Edge table — one row per (event × resource × relation) triple, with optional `snapshot_before` / `snapshot_after`. No FK to the linked entity. |
| `audit_item_effects` | Balance-change journal. `inventory_subject_id` is mandatory; `item_id` is nullable for temporary items. Snapshots survive deletion. |

Helper:
```python
from app.services.audit_helper import record_audit_event

await record_audit_event(
    uow,
    event_type="operation.submit",
    event_version=2,
    actor_user_id=actor,
    entity_type="operation",
    entity_id=str(op.id),
    summary="…",
    changes={"operation_type": "ADJUSTMENT", "lines_count": 3, "total_qty": "5.0000"},
    outcome="success",
    parent_event_id=uow.audit_parent_event_id,  # for child-of merge flows
)
```

Phase 1 covers 20 event types across four groups: operations, catalog,
related (temporary / review / issue_object) and batch. See
[`docs/audit-event-catalog.md`](docs/audit-event-catalog.md) for the
table.

The `item.merge` flow has a critical ordering invariant:
1. INSERT parent `audit_events` row → flush → keep its `event_id`.
2. Set `uow.audit_parent_event_id` and `audit_effect_type_override`.
3. Create + submit each system ADJUSTMENT, so each child
   `operation.submit` event has `parent_event_id` set.
4. Persist the `audit_item_effects` rows while the `OperationLine.item_id`
   FK still points at the source item — capturing `item_id=source_id`
   while the source is still linked is the only way to keep the
   chronicle truthful after the reassignment.
5. Reassign `OperationLine.item_id` to the target.
6. Insert `audit_event_resources` (merge_source, merge_target,
   generated → ADJUSTMENT ids).
7. Deactivate the source item.

Cancellation is symmetric with `effect_type='cancel_reversal'`; effects
are written AFTER the `operation.cancel` audit event so the FK
`audit_event_id` is valid.

Phase 2 (out of scope for this repo): Django `AuditOutbox` model +
delivery command, `POST /system/audit-event` for inbound events with
retry / dedup using `external_event_id`, `credential_*` population,
admin / security events, `GET /admin/audit/items/{id}/history` API.

## API Overview
Base prefix: `/api/v1`

Primary auth:
- `X-User-Token`
- `X-Device-Token`

Access model:
- one shared API contour for all clients
- no separate service or AI-only API contour
- permissions are determined by role plus site-scoped `UserAccessScope`

Operations note:
- `effective_at` is the operation posting date
- if omitted on create, the server sets it to the current timestamp
- changing `effective_at` is done only through `PATCH /api/v1/operations/{operation_id}/effective-at`

Primary documentation:
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- [docs/ENDPOINT_INVENTORY.md](docs/ENDPOINT_INVENTORY.md)

## Canonical Architecture Docs
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [INDEX.md](INDEX.md)
- [AI_CONTEXT.md](AI_CONTEXT.md)
- [AI_ENTRY_POINTS.md](AI_ENTRY_POINTS.md)
- [MEMORY.md](MEMORY.md)
- [docs/adr/0018-audit-architecture.md](docs/adr/0018-audit-architecture.md)
