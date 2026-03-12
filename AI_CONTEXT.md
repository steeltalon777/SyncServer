# AI_CONTEXT

## System architecture
- Architecture style: layered monolith with clear separation of concerns.
- Request path: FastAPI router → service → repository → PostgreSQL.
- Transaction management: `UnitOfWork` (`async with uow`).
- Dual authentication modes: device auth for sync, service auth for web clients.

## Backend rules
- Keep route handlers thin; business rules stay in `app/services`.
- Repository layer owns SQLAlchemy query details.
- Preserve push idempotency semantics (`accepted`, `duplicate_same_payload`, `uuid_collision`).
- Support dual authentication: device auth for sync endpoints, service auth for business endpoints.
- Use standardized error format across all endpoints.

## Authentication rules
### Device Authentication
- Required for: `/api/v1/sync/*` endpoints exclusively.
- Headers: `X-Device-Token`, `X-Site-Id`, `X-Device-Id`.
- Validation: `require_device_auth()` checks device registration, site binding, activity.
- Do not break existing device auth flow for sync clients.

### Service Authentication
- Used by: Django web client as trusted internal service.
- Header: `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>`.
- Validation: `require_service_auth()` validates service token.
- Acting user context: `X-Acting-User-Id`, `X-Acting-Site-Id` headers required.
- User access validation: `require_acting_user()` checks user-site-role mapping.

### Role-based Permissions
- **storekeeper**: View operations/balances, create operations within assigned sites.
- **chief_storekeeper**: All storekeeper permissions + edit catalog, work across permitted sites.
- **root**: All permissions + system administration (users, sites, devices, access).

### Dual-mode endpoints
- `/catalog/*` endpoints support both authentication modes.
- Determine mode by presence of `X-Device-Token` vs `Authorization: Bearer`.
- `/business/*` endpoints are service-auth only.
- `/sync/*` endpoints are device-auth only.

## Database rules
- PostgreSQL is the only runtime datastore.
- Domain entities use UUID identifiers where appropriate.
- `events.server_seq` is the authoritative pull cursor.
- Catalog deactivation is soft (`is_active=false`), not hard delete.
- User access controlled via `user_site_roles` table.
- Operations use integer IDs with UUID for external reference.

## Layered architecture
- API: `app/api/` - HTTP endpoints, dependencies, exception handlers
- Service: `app/services/` - Business logic, validation, orchestration
- Repository: `app/repos/` - Data access, SQLAlchemy queries
- Models: `app/models/` - SQLAlchemy ORM entities
- Schemas: `app/schemas/` - Request/response contracts, validation
- Config/DB wiring: `app/core/` - Settings, database session factory
## Client rules
- Clients must use HTTP API; no direct DB writes.
- Sync clients use device headers (`X-Device-Token`, `X-Site-Id`, `X-Device-Id`).
- Django web client uses service token + acting user context.
- Clients should treat `/push` as retry-safe due to idempotent ingest.
- Business operations follow draft → submitted → cancelled workflow.

## Architecture constraints
- Do not bypass `UnitOfWork` for transactional writes.
- Do not move repository logic into routers.
- Do not break category hierarchy invariants (no self-parent, no cycles, unique sibling names).
- In-memory rate limiter is process-local; do not assume cluster-wide protection.
- Maintain backward compatibility for existing sync clients.
- Sync API remains device-only; Django does not authenticate as a sync device.
- All business logic validation must happen in service layer.
- Use standardized exception classes from `app/api/exceptions.py`.

## Error handling rules
- Use `SyncServerException` and its subclasses for all errors.
- Follow standard error format: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- Map HTTP status codes appropriately:
  - `400` - ValidationError
  - `401` - UnauthorizedError
  - `403` - ForbiddenError, PermissionDeniedError, RolePermissionError
  - `404` - NotFoundError
  - `409` - ConflictError, OperationStateError, BalanceInsufficientError
  - `422` - FastAPI/Pydantic validation errors
  - `429` - RateLimitError
  - `500` - InternalServerError

## Deployment constraints
- SyncServer is commonly deployed behind nginx reverse proxy.
- In container deployment SyncServer should live in a shared external Docker network (e.g., `backend`).
- Other services must call SyncServer by service/container name: `http://syncserver:8000`
- Do not document or recommend `127.0.0.1` for cross-container communication.
- Public ingress may terminate at nginx, while SyncServer remains internal-only.
- Service token (`SYNC_SERVER_SERVICE_TOKEN`) must be configured for Django integration.

## API versioning
- Current API version: `v1` (prefix: `/api/v1/`)
- Maintain backward compatibility within major version.
- Use semantic versioning for API changes.

## Testing rules
- Test business logic in service layer.
- Test repository layer with database integration.
- Test API endpoints with authentication and authorization.
- Mock external dependencies in unit tests.
- Use fixtures for common test data setup.

## Documentation rules
- Keep documentation AI-friendly and grounded in actual code.
- Update documentation when making architectural changes.
- Document API endpoints with examples.
- Maintain architecture decision records (ADRs) for significant changes.
- Keep README.md up-to-date with setup and deployment instructions.
