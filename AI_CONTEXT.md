# AI Context

## System Architecture
- SyncServer is a layered backend: API -> Services -> Repositories -> PostgreSQL
- The service is the authoritative source of warehouse state
- Clients integrate through HTTP APIs; they should not own domain logic

## Backend Rules
- Keep HTTP handlers thin
- Put business rules and workflows in `app/services/`
- Put only persistence/query logic in `app/repos/`
- Use `UnitOfWork` for transaction-scoped access to repositories

## Database Rules
- PostgreSQL is the source of persisted state
- ORM models live in `app/models/`
- Repository methods should not embed business decisions
- Balances are derived from operations, not edited as primary truth
- Soft deactivation uses `is_active` in multiple domains

## Layered Architecture
### API
- `app/api/`
- request/response mapping
- auth headers
- access guard entry points

### Services
- `app/services/`
- business invariants
- domain workflows
- orchestration across repositories

### Repositories
- `app/repos/`
- SQLAlchemy access
- query composition
- persistence helpers

### Models
- `app/models/`
- persistent domain entities
- relations and schema-level constraints

## Client Rules
- Django admin / web clients should use token-based endpoints
- Device clients use sync endpoints with `X-Device-Token`
- New integrations should prefer documented `/api/v1` routes and avoid reviving removed compatibility paths

## Architecture Constraints
- Root access is global via `User.is_root`
- Non-root access is site-scoped via `UserAccessScope`
- Catalog entities are global
- `site_id` on some catalog reads is an access-context check, not a data partition
- Operation lifecycle is constrained to `draft -> submitted -> cancelled`
- Django auth may include optional device context on `/auth/*`

## Search Normalization Rules
- All search inputs MUST flow through `app/core/search_utils.py` — never use raw `f"%{search}%"` patterns.
- For columns with `normalized_name` / `normalized_key` use `build_normalized_like_term(search)`.
- For raw technical columns (`sku`, `code`, `device_code`, `description`, `notes`, snapshots) use `build_raw_like_term(search)` — it preserves hyphens, slashes, dots, and case.
- Two terms per query, never one: mixing the same term across both column types breaks SKU search.
- All `.ilike()` calls MUST include `escape="\\"` argument.
- `normalized_name` is auto-computed via SQLAlchemy event listeners (`app/models/events.py`) on `before_insert`/`before_update` for `Item`, `Category`, `TemporaryItem`, `Site`, `Device` — services must not set it manually.
- `IssueObject.normalized_key` / `IssueObjectCategory.normalized_key` are computed in services (different semantics, used in unique constraints).
