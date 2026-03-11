# PROJECT_BRAIN

## Project purpose
SyncServer provides reliable event synchronization and catalog APIs for distributed inventory clients.

## Architecture summary
Layered FastAPI backend:
`routes -> services -> repositories -> PostgreSQL` with per-request `UnitOfWork` transactions.

## Key modules
- Sync module (`/ping`, `/push`, `/pull`)
- Catalog read module (`/catalog/*`)
- Catalog admin module (`/catalog/admin/*`)
- Health endpoints

## Key entities
`Event`, `Site`, `Device`, `Category`, `Unit`, `Item`, `Balance`.

## Key services
- `SyncService` orchestrates push batches.
- `EventIngestService` enforces idempotency using `event_uuid + payload_hash`.
- `CatalogAdminService` enforces catalog invariants.

## Entry points
- `main.py` (application bootstrap)
- `app/api/routes_*.py` (HTTP contracts)

## Important constraints
- Device token auth required for sync and catalog routes.
- `server_seq` is the sync cursor for pull.
- Catalog uses soft deactivation (`is_active`) instead of hard delete.
- Category hierarchy must remain acyclic.

## Data flow in one line
Client request → API validation/auth → service business rule → repository query/write → DB commit → response DTO.
