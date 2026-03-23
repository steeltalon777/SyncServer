# TZ Gap Analysis (after refactor)

This file maps the requested TZ requirements to current implementation status.

## Status legend
- DONE: implemented in code.
- PARTIAL: implemented with caveats.
- TODO: intentionally not in this stage.

## 1. Stack and async mode
- Python/FastAPI/SQLAlchemy async/asyncpg/Pydantic v2: DONE
- Async DB access with awaitable operations: DONE
- `.env` settings including `DATABASE_URL_TEST`: DONE

## 2. Project structure
- `app/core`, `app/models`, `app/schemas`, `app/repos`, `app/services`: DONE
- Separation of concerns (model/schema/repo/service): DONE

## 3. ORM models
- `sites`: DONE
- `devices`: DONE
- `categories`: DONE
- `items`: DONE
- `events`: DONE
- `balances`: DONE
- `user_access_scopes`: DONE

Notes:
- ORM maps existing tables, but app does not auto-migrate schema.
- `events.server_seq` configured as identity/DB-generated.

## 4. DTO contracts
- Sync DTO (`EventLine`, `EventPayload`, `EventIn`, `PushRequest`, `PushResponse`): DONE
- Catalog DTO (`ItemDto`, `CategoryDto`, response envelopes): DONE
- Decimal usage for quantities: DONE

## 5. Repository and transaction layer
- `EventsRepo`: DONE
  - `get_by_uuid`
  - `insert_event`
  - `pull`
  - `compute_payload_hash`
- `BalancesRepo` with `get_for_update` and `upsert`: DONE
- `CatalogRepo`: DONE
- Unit of Work transaction wrapper: DONE

## 6. Duplicate/collision behavior
Required behavior:
1. Missing event -> insert.
2. Existing + same payload -> duplicate.
3. Existing + different payload -> uuid_collision.

Status: DONE (`EventIngestService`).

## 7. Tests
- DB smoke: DONE
- insert + `server_seq`: DONE
- duplicate: DONE
- uuid collision: DONE
- pull ordering: DONE

Additional:
- push-batch classification via `SyncService`: DONE

## 8. Out of current scope
- Business `apply_event` logic (balances mutation semantics) is still not implemented in this repository.
- Device registration and token issuance lifecycle are outside this API (server validates existing device/token only).
