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
- Treat legacy compatibility endpoints as transitional, not canonical

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
- New integrations should prefer `/api/v1` primary routes over legacy compatibility routes

## Architecture Constraints
- Root access is global via `User.is_root`
- Non-root access is site-scoped via `UserAccessScope`
- Catalog entities are global
- `site_id` on some catalog reads is an access-context check, not a data partition
- Operation lifecycle is constrained to `draft -> submitted -> cancelled`
- Compatibility code exists and should be changed cautiously
