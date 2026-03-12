# MEMORY

## System architecture
- Async FastAPI service with strict API → service → repository separation.
- Per-request transaction boundary through `UnitOfWork`.
- PostgreSQL stores both sync event log and catalog domain data.

## Core entities
- `Site`: tenant-like warehouse/site context.
- `Device`: authenticated sync client bound to site.
- `Event`: append-only sync log with monotonic `server_seq`.
- `Category`, `Unit`, `Item`: catalog entities.
- `Balance`: quantity snapshot by `(site_id, item_id)`.

## Data model decisions
- UUID-based keys across domain entities.
- Event idempotency: `event_uuid` + `payload_hash`.
- Category hierarchy: adjacency list (`parent_id`) with service-level cycle checks.
- Catalog records use `is_active` for soft deactivation.

## API design
- Sync API: `/ping`, `/push`, `/pull`.
- Catalog read API: `/catalog/items|categories|units`, `/catalog/categories/tree`.
- Catalog admin API: `/catalog/admin/*` create/update only.

## Business rules
- `/push` classifies incoming events as accepted / duplicate / uuid collision.
- Device token and site-device match are mandatory for protected endpoints.
- Unit name/symbol and item SKU are uniqueness-constrained.
- Category names are unique within the same parent.

## Known pitfalls
- In-memory rate limiter is not distributed.
- SQL bootstrap and ORM differ for `user_site_roles` shape.
- No migration framework configured in repository.

## Future architecture
- Introduce distributed rate-limit storage.
- Adopt migration tooling for schema evolution.
- Add reconciliation workflows for long-offline clients.

- In Docker deployment, `127.0.0.1` from another container does not reach SyncServer.
- Cross-container access must use `http://syncserver:8000`.
- Reverse proxy deployments should route `/api/` to SyncServer instead of exposing SyncServer as the main public entrypoint.
- Database bootstrap is required before first use:
  - apply `db/init/001_init_schema.sql`
  - create `site`
  - create `device`
  - create `registration_token`
- Device/site IDs and registration token must match real bootstrap data, not placeholder strings.