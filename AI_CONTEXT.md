# AI_CONTEXT

## System architecture
- Architecture style: layered monolith.
- Request path: FastAPI router → service → repository → PostgreSQL.
- Transaction management: `UnitOfWork` (`async with uow`).
- Dual authentication modes: device auth for sync, service auth for web clients.

## Backend rules
- Keep route handlers thin; business rules stay in `app/services`.
- Repository layer owns SQLAlchemy query details.
- Preserve push idempotency semantics (`accepted`, `duplicate_same_payload`, `uuid_collision`).
- Support dual authentication: device auth for sync endpoints, service auth for business endpoints.

## Authentication rules
### Device Authentication
- Required for: `/sync/*` endpoints exclusively.
- Headers: `X-Device-Token`, `X-Site-Id`, `X-Device-Id`.
- Validation: `require_device_auth()` checks device registration, site binding, activity.
- Do not break existing device auth flow for sync clients.

### Service Authentication
- Used by: Django web client as trusted internal service.
- Header: `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>`.
- Validation: `require_service_auth()` validates service token.
- Acting user context: `X-Acting-User-Id`, `X-Acting-Site-Id` headers required.
- User access validation: `require_acting_user()` checks user-site-role mapping.

### Dual-mode endpoints
- `/catalog/*` endpoints support both authentication modes.
- Determine mode by presence of `X-Device-Token` vs `Authorization: Bearer`.
- `/business/*` endpoints are service-auth only.
- `/sync/*` endpoints are device-auth only.
## Database rules
- PostgreSQL is the only runtime datastore.
- Domain entities use UUID identifiers.
- `events.server_seq` is the authoritative pull cursor.
- Catalog deactivation is soft (`is_active=false`), not hard delete.
- User access controlled via `user_site_roles` table.

## Layered architecture
- API: `app/api/`
- Service: `app/services/`
- Repository: `app/repos/`
- Models: `app/models/`
- Config/DB wiring: `app/core/`

## Client rules
- Clients must use HTTP API; no direct DB writes.
- Sync clients use device headers (`X-Device-Token`, `X-Site-Id`, `X-Device-Id`).
- Django web client uses service token + acting user context.
- Clients should treat `/push` as retry-safe due to idempotent ingest.

## Architecture constraints
- Do not bypass `UnitOfWork` for transactional writes.
- Do not move repository logic into routers.
- Do not break category hierarchy invariants (no self-parent, no cycles, unique sibling names).
- In-memory rate limiter is process-local; do not assume cluster-wide protection.
- Maintain backward compatibility for existing sync clients.
- Sync API remains device-only; Django does not authenticate as a sync device.

## Deployment constraints
- SyncServer is commonly deployed behind nginx reverse proxy.
- In container deployment SyncServer should live in a shared external Docker network (for example `backend`).
- Other services must call SyncServer by service/container name:
  - `http://syncserver:8000`
- Do not document or recommend `127.0.0.1` for cross-container communication.
- Public ingress may terminate at nginx, while SyncServer remains internal-only.
- Service token (`SYNC_SERVER_SERVICE_TOKEN`) must be configured for Django integration.
