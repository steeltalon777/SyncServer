# MEMORY

## System architecture
- Async FastAPI service with strict API → service → repository separation.
- Per-request transaction boundary through `UnitOfWork`.
- PostgreSQL stores both sync event log and catalog domain data.
- Dual authentication modes: device auth for sync, service auth for web clients.

## Core entities
- `Site`: tenant-like warehouse/site context.
- `Device`: authenticated sync client bound to site.
- `Event`: append-only sync log with monotonic `server_seq`.
- `Category`, `Unit`, `Item`: catalog entities.
- `Balance`: quantity snapshot by `(site_id, item_id)`.
- `UserSiteRole`: user-site-role mapping for access control.
- `Operation`: business operations (RECEIVE, WRITE_OFF, MOVE, ISSUE).
- `OperationLine`: operation line items.

## Data model decisions
- UUID-based keys across domain entities.
- Event idempotency: `event_uuid` + `payload_hash`.
- Category hierarchy: adjacency list (`parent_id`) with service-level cycle checks.
- Catalog records use `is_active` for soft deactivation.
- User access: `user_site_roles` table with `(user_id, site_id, role)` unique constraint.
- Operations: integer IDs with UUID for external reference.
- Balances: derived state updated atomically with operations.

## Authentication Architecture
### Device Authentication
- Purpose: Authenticate sync devices (WPF clients, offline devices).
- Headers: `X-Device-Token`, `X-Site-Id`, `X-Device-Id`.
- Validation: Checks device registration, site binding, device activity.
- Endpoints: `/api/v1/sync/*` exclusively.
### Service Authentication
- Purpose: Authenticate trusted internal services (Django web client).
- Header: `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>`.
- Acting user context: `X-Acting-User-Id`, `X-Acting-Site-Id`.
- Validation: Service token + user-site access verification.
- Endpoints: All business/admin endpoints except sync.

## Role Model
### storekeeper
- View operations and balances
- Create operations (RECEIVE, WRITE_OFF, MOVE, ISSUE)
- Only within assigned sites

### chief_storekeeper
- All storekeeper permissions
- Work across permitted sites
- Edit catalog (items, categories)

### root
- All chief_storekeeper permissions
- Create users and assign roles
- Create sites and devices
- Manage user-site access
## API design
- Sync API: `/ping`, `/push`, `/pull` (device auth only).
- Catalog read API: `/catalog/*` (dual auth).
- Business API: `/business/catalog/*` (service auth only).
- Operations API: `/operations/*` (service auth only).
- Balances API: `/balances/*` (service auth only).
- Catalog admin API: `/catalog/admin/*` (service auth + role-based).
- Admin API: `/admin/*` (root only).
- Health API: `/health/*` (no auth).

## Business rules
- `/push` classifies incoming events as accepted / duplicate / uuid collision.
- Device token and site-device match are mandatory for sync endpoints.
- Service token validation is required for business endpoints.
- User must have `user_site_roles` entry to access a site.
- Unit name/symbol and item SKU are uniqueness-constrained.
- Category names are unique within the same parent.
- Operations follow draft → submitted → cancelled workflow.
- Balance updates are atomic with operation submission/cancellation.

## Error handling
- Standardized error format: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- Exception hierarchy: `SyncServerException` with specific subclasses.
- HTTP status codes mapped to business scenarios.
- All errors return consistent JSON structure.

## Known implementation details
- In-memory rate limiter is not distributed.
- SQL bootstrap and ORM differ for `user_site_roles` shape.
- No migration framework configured in repository.
- Service token (`SYNC_SERVER_SERVICE_TOKEN`) must be configured for Django integration.
- Operation lines use integer line numbers within operation.
- Balance quantities use Decimal for precision.

## Future architecture
- Introduce distributed rate-limit storage.
- Adopt migration tooling for schema evolution.
- Add audit logging for service authentication requests.
- Implement WebSocket support for real-time updates.
- Add event sourcing for complete audit trail.
- Implement distributed cache for frequently accessed data.

## Deployment notes
- In Docker deployment, `127.0.0.1` from another container does not reach SyncServer.
- Cross-container access must use `http://syncserver:8000`.
- Reverse proxy deployments should route `/api/` to SyncServer instead of exposing SyncServer as the main public entrypoint.
- Database bootstrap is required before first use:
  - apply `db/init/001_init_schema.sql`
  - create `site`
  - create `device`
  - create `registration_token`
  - create `user_site_roles` entries for web users
- Device/site IDs and registration token must match real bootstrap data, not placeholder strings.
- Service token must be shared between SyncServer and Django web client.

## Testing approach
- Test business logic in service layer.
- Test repository layer with database integration.
- Test API endpoints with authentication and authorization.
- Mock external dependencies in unit tests.
- Use fixtures for common test data setup.

## Documentation status
- README.md: Complete with setup, deployment, API overview.
- ARCHITECTURE.md: Complete architecture documentation.
- AI_CONTEXT.md: AI-friendly rules and constraints.
- AI_ENTRY_POINTS.md: Complete entry points reference.
- INDEX.md: Navigation and overview.
- API_CONTRACT.md: API contract documentation (if exists).
- DOMAIN_MODEL.md: Domain model documentation (if exists).

## Current implementation status
- ✅ Dual authentication architecture
- ✅ Sync API (device auth only)
- ✅ Catalog API (dual auth)
- ✅ Business API (service auth only)
- ✅ Operations API with workflow
- ✅ Balances API with filtering
- ✅ Catalog Admin API (role-based)
- ✅ Admin API (root only)
- ✅ Standardized error handling
- ✅ Role-based permissions
- ✅ Unit of Work pattern
- ✅ Repository pattern
- ✅ Service layer business logic
- ✅ Pydantic schemas for validation
- ✅ Database models for all entities
- ✅ Health endpoints
- ✅ API versioning (`/api/v1/`)
- ✅ Docker deployment support

## Remaining work
- Implement missing repository methods (devices, user-site access listing)
- Add comprehensive tests
- Implement audit logging
- Add WebSocket support
- Implement distributed caching
- Add migration framework
- Implement distributed rate limiting
