# AI_ENTRY_POINTS

## Server entrypoints
- `main.py` — FastAPI app creation, middleware, router inclusion, exception handlers.

## API Layer

### Routers (`app/api/`)
- `routes_sync.py` — sync endpoints (device auth only)
- `routes_catalog.py` — catalog read endpoints (dual auth)
- `routes_business.py` — business API endpoints (service auth only)
- `routes_operations.py` — operations API (service auth only)
- `routes_balances.py` — balances API (service auth only)
- `routes_catalog_admin.py` — catalog admin endpoints (service auth + role-based)
- `routes_admin.py` — admin API (root only)
- `routes_health.py` — health/readiness endpoints

### Dependencies (`app/api/deps.py`)
- `require_device_auth()` — validates device token, site-device binding, device activity
- `require_service_auth()` — validates service token (`SYNC_SERVER_SERVICE_TOKEN`)
- `require_acting_user()` — validates acting user context and site access
- `auth_catalog_headers()` — collects device auth headers
- `auth_service_headers()` — collects service auth headers
- `get_uow()` — provides UnitOfWork instance
- `get_request_id()` — gets request ID from middleware
- `get_client_ip()` — extracts client IP address
- `enforce_rate_limit()` — applies rate limiting
- `error_response()` — standard error response formatter

### Exceptions (`app/api/exceptions.py`)
- `SyncServerException` — base exception class
- `ValidationError`, `UnauthorizedError`, `ForbiddenError`, `NotFoundError`, `ConflictError`
- `RateLimitError`, `InternalServerError`
- `PermissionDeniedError`, `RolePermissionError`
- `OperationStateError`, `BalanceInsufficientError`
- `CategoryCycleError`, `UniqueConstraintError`

## Service Layer (`app/services/`)
- `sync_service.py` — orchestrates push processing
- `event_ingest.py` — enforces idempotency and collision rules
- `catalog_admin_service.py` — enforces catalog business validations
- `operations_service.py` — operation business logic and validation
- `access_service.py` — access control and role management
- `uow.py` — UnitOfWork with all repositories

## Repository / Data Layer (`app/repos/`)
- `events_repo.py` — event log operations
- `catalog_repo.py` — catalog data access
- `devices_repo.py` — device management
- `sites_repo.py` — site operations
- `balances_repo.py` — balance operations
- `operations_repo.py` — operation and operation line management
- `user_site_roles_repo.py` — user-site access control

## Models / Entities (`app/models/`)
- `site.py` — Site entity
- `device.py` — Device entity
- `event.py` — Event entity
- `category.py` — Category entity
- `unit.py` — Unit entity
- `item.py` — Item entity
- `balance.py` — Balance entity
- `user_site_role.py` — UserSiteRole entity
- `operation.py` — Operation and OperationLine entities
- `base.py` — Base model class

## Schemas (`app/schemas/`)
- `common.py` — ORMBaseModel and common utilities
- `sync.py` — sync request/response schemas
- `catalog.py` — catalog schemas
- `operation.py` — operation schemas
- `balance.py` — balance schemas
- `admin.py` — admin schemas (sites, devices, users, access)
- `event.py` — event schemas

## Configuration (`app/core/`)
- `config.py` — application settings with environment variables
- `db.py` — database session factory and engine

## Key Environment Variables
- `DATABASE_URL` — PostgreSQL connection string
- `SYNC_SERVER_SERVICE_TOKEN` — service authentication token
- `APP_ENV` — application environment (dev, test, prod)
- `LOG_LEVEL` — logging level
- `DEFAULT_PAGE_SIZE` — default pagination size
- `MAX_PUSH_EVENTS` — maximum events per push request
- `DEFAULT_PULL_LIMIT` — default pull limit
## Deployment entrypoints
- `docker-compose.yml` — container deployment descriptor
- `db/init/001_init_schema.sql` — schema bootstrap
- `.env.example` — environment template (copy to `.env`)
- nginx gateway configuration (external) routes `/api/` to this service

## Authentication Configuration
- Device auth: Configured via device registration in database
- Service auth: Set `SYNC_SERVER_SERVICE_TOKEN` environment variable
- User access: Managed via `user_site_roles` table entries

## API Endpoint Groups

### Sync API (`/api/v1/sync/*`)
- `POST /ping` — device heartbeat
- `POST /push` — event ingestion
- `POST /pull` — event retrieval

### Catalog API (`/api/v1/catalog/*`)
- `POST /items` — list items
- `POST /categories` — list categories
- `POST /units` — list units
- `GET /categories/tree` — categories hierarchy

### Business API (`/api/v1/business/*`)
- `POST /catalog/items` — list items (service auth)
- `POST /catalog/categories` — list categories (service auth)
- `POST /catalog/units` — list units (service auth)
- `GET /catalog/categories/tree` — categories tree (service auth)

### Operations API (`/api/v1/operations/*`)
- `GET /` — list operations
- `GET /{operation_id}` — get operation
- `POST /` — create operation
- `PATCH /{operation_id}` — update operation
- `POST /{operation_id}/submit` — submit operation
- `POST /{operation_id}/cancel` — cancel operation

### Balances API (`/api/v1/balances/*`)
- `GET /` — list balances
- `GET /by-site` — get balances by site
- `GET /summary` — get balances summary

### Catalog Admin API (`/api/v1/catalog/admin/*`)
- Catalog entity create/update endpoints
- Role-based access (chief_storekeeper and root)

### Admin API (`/api/v1/admin/*`)
- `GET /sites` — list sites (root only)
- `POST /sites` — create site (root only)
- `PATCH /sites/{site_id}` — update site (root only)
- `GET /devices` — list devices (root only)
- `GET /access/user-sites` — list user-site access (root only)
- `POST /access/user-sites` — create user-site access (root only)
- `PATCH /access/user-sites/{access_id}` — update user-site access (root only)

### Health API (`/api/v1/health/*`)
- `GET /` — health check
- `GET /ready` — readiness check
- `GET /db-check` — database connectivity check
