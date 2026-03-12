# AI_CONTEXT

## System architecture
- Architecture style: layered monolith.
- Request path: FastAPI router → service → repository → PostgreSQL.
- Transaction management: `UnitOfWork` (`async with uow`).

## Backend rules
- Keep route handlers thin; business rules stay in `app/services`.
- Repository layer owns SQLAlchemy query details.
- Preserve push idempotency semantics (`accepted`, `duplicate_same_payload`, `uuid_collision`).
- Keep auth checks via `require_device_auth` for sync/catalog endpoints.

## Database rules
- PostgreSQL is the only runtime datastore.
- Domain entities use UUID identifiers.
- `events.server_seq` is the authoritative pull cursor.
- Catalog deactivation is soft (`is_active=false`), not hard delete.

## Layered architecture
- API: `app/api/`
- Service: `app/services/`
- Repository: `app/repos/`
- Models: `app/models/`
- Config/DB wiring: `app/core/`

## Client rules
- Clients must use HTTP API; no direct DB writes.
- Sync/catalog calls require device headers (`X-Device-Token`, plus catalog auth headers).
- Clients should treat `/push` as retry-safe due to idempotent ingest.

## Architecture constraints
- Do not bypass `UnitOfWork` for transactional writes.
- Do not move repository logic into routers.
- Do not break category hierarchy invariants (no self-parent, no cycles, unique sibling names).
- In-memory rate limiter is process-local; do not assume cluster-wide protection.

## Deployment constraints

- SyncServer is commonly deployed behind nginx reverse proxy.
- In container deployment SyncServer should live in a shared external Docker network (for example `backend`).
- Other services must call SyncServer by service/container name:
  - `http://syncserver:8000`
- Do not document or recommend `127.0.0.1` for cross-container communication.
- Public ingress may terminate at nginx, while SyncServer remains internal-only.