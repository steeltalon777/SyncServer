# Code Documentation

This document describes current implementation details of the data/model layer.

## 1. Core layer

### `app/core/config.py`

`Settings` (Pydantic Settings):
- `DATABASE_URL`: main asyncpg connection string.
- `DATABASE_URL_TEST`: optional test DB connection string.
- `APP_ENV`: environment label.
- `LOG_LEVEL`: logging level.
- `DEFAULT_PAGE_SIZE`: default pagination helper.

`get_settings()` uses `lru_cache` to avoid repeated environment parsing.

### `app/core/db.py`

- Creates async SQLAlchemy engine (`create_async_engine`).
- Exposes `SessionFactory` (`async_sessionmaker`).
- Exposes FastAPI dependency `get_db()` yielding `AsyncSession`.

## 2. ORM models

### `Site` (`sites`)
- Columns: `id`, `code`, `name`, `is_active`, `created_at`.
- Constraint/index: unique index on `code`.

### `Device` (`devices`)
- Columns: `id`, `site_id`, `name`, `registration_token`, `last_ip`, `last_seen_at`, `client_version`, `is_active`, `created_at`.
- Constraints/indexes:
  - unique `(site_id, registration_token)`
  - index on `site_id`
  - index on `last_seen_at`

### `Category` (`categories`)
- Columns: `id`, `name`, `parent_id`, `is_active`, `updated_at`.
- Self-reference: `parent_id -> categories.id`.
- Index on `updated_at`.

### `Item` (`items`)
- Columns: `id`, `sku`, `name`, `category_id`, `unit`, `is_active`, `updated_at`.
- `sku` unique (nullable).
- Index on `updated_at`.

### `Event` (`events`)
- PK: `event_uuid` (client-generated UUID).
- Core fields: `site_id`, `device_id`, `user_id`, `event_type`, `event_datetime`, `received_at`, `schema_version`, `payload`, `payload_hash`.
- `server_seq`: unique bigint identity (DB-generated).
- Indexes:
  - `(site_id, server_seq)` for pull
  - `(site_id, event_datetime)` for investigation
  - `(event_type)`

### `Balance` (`balances`)
- Composite PK: `(site_id, item_id)`.
- Fields: `qty NUMERIC(18,3)`, `updated_at`.

### `UserSiteRole` (`user_site_roles`)
- Fields: `id`, `user_id`, `site_id`, `role`.
- Unique `(user_id, site_id)`.
- Check constraint: role in `admin|clerk|viewer`.

## 3. DTO schemas

### `app/schemas/sync.py`

Input DTO:
- `EventLine`
- `EventPayload`
- `EventIn`
- `PushRequest`
- `PingRequest`

Output DTO:
- `AcceptedEvent`
- `DuplicateEvent`
- `RejectedEvent`
- `PushResponse`
- `PingResponse`

`ReasonCode` literal currently includes:
- `uuid_collision`
- `processing_error`
- `validation_error`

### `app/schemas/catalog.py`

- `CategoryDto`
- `ItemDto`
- `CatalogItemsResponse`
- `CatalogCategoriesResponse`
- `CatalogRequest`

### `app/schemas/common.py`

`ORMBaseModel` enables `from_attributes` and JSON serialization for `Decimal`, `datetime`, `UUID`.

## 4. Repositories

### `SitesRepo`
- `get_by_id`
- `get_by_code`

### `DevicesRepo`
- `get_by_id`
- `get_by_site`
- `create`
- `update_last_seen`

### `EventsRepo`
- `get_by_uuid`
- `insert_event`
- `pull(site_id, since_seq, limit)`
- `compute_payload_hash(payload)`

### `BalancesRepo`
- `get_for_update(site_id, item_id)`
- `upsert(site_id, item_id, delta_qty)`

### `CatalogRepo`
- `list_items(updated_after, limit)`
- `list_categories(updated_after, limit)`

## 5. Services and transactions

### `UnitOfWork`

Wraps a transaction and bundles repositories:
- `sites`, `devices`, `events`, `catalog`, `balances`.
- Supports `async with` semantics.

### `EventIngestService`

Implements event idempotency:
1. Query existing by `event_uuid`.
2. Compute canonical payload hash.
3. If no existing -> insert (`accepted`).
4. If same hash -> `duplicate_same_payload`.
5. Else -> `uuid_collision`.

### `SyncService`

Orchestrates push-batch classification over a `UnitOfWork` and returns `PushResponse`.

## 6. Tests

### `tests/conftest.py`
- Creates temporary Postgres schema per test session.
- Creates all ORM tables in that schema.
- Drops schema after test session.

### `tests/test_events_repo.py`
Covers:
- connectivity smoke;
- insert + server_seq;
- duplicate;
- uuid collision;
- pull ordering;
- `SyncService` result classification.

## 7. Operational notes

- App does not run `create_all()` at startup.
- Django remains the source of truth for production schema migrations.
- The current FastAPI app intentionally exposes only technical health endpoints.
