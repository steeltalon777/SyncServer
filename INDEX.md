# INDEX - SyncServer Documentation

## Overview
- [README.md](./README.md) - Project overview, setup, deployment
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture and design

## AI Context
- [AI_CONTEXT.md](./AI_CONTEXT.md) - Rules and constraints for AI assistance
- [AI_ENTRY_POINTS.md](./AI_ENTRY_POINTS.md) - Key entry points and modules
- [MEMORY.md](./MEMORY.md) - System knowledge and decisions
## Project overview
SyncServer is an async FastAPI backend for event synchronization and catalog management over PostgreSQL.

## Architecture overview
`Clients → API layer → Service layer → Repository layer → PostgreSQL`

## Authentication Documentation

### Device Authentication (Sync Clients)
- **Purpose**: Authenticate WPF offline clients, sync devices
- **Headers**:
  - `X-Device-Token`: Device registration token
  - `X-Site-Id`: Site UUID
  - `X-Device-Id`: Device UUID
- **Endpoints**: `/api/v1/sync/*` exclusively
- **Validation**: `require_device_auth()` in `app/api/deps.py`

### Service Authentication (Django Web Client)
- **Purpose**: Authenticate trusted internal services
- **Headers**:
  - `Authorization: Bearer <SYNC_SERVER_SERVICE_TOKEN>`
  - `X-Acting-User-Id`: User ID (integer)
  - `X-Acting-Site-Id`: Site UUID
- **Endpoints**: All business/admin endpoints except sync
- **Validation**: `require_service_auth()` + `require_acting_user()`

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

## API Groups

### Sync API (`/api/v1/sync/*`)
- Device authentication only
- `POST /ping` - Device heartbeat
- `POST /push` - Event ingestion
- `POST /pull` - Event retrieval
- **Location**: `app/api/routes_sync.py`

### Catalog API (`/api/v1/catalog/*`)
- Dual authentication support
- `POST /items` - List items
- `POST /categories` - List categories
- `POST /units` - List units
- `GET /categories/tree` - Category hierarchy
- **Location**: `app/api/routes_catalog.py`

### Business API (`/api/v1/business/*`)
- Service authentication only
- `POST /catalog/items` - List items
- `POST /catalog/categories` - List categories
- `POST /catalog/units` - List units
- `GET /catalog/categories/tree` - Category hierarchy
- **Location**: `app/api/routes_business.py`

### Operations API (`/api/v1/operations/*`)
- Service authentication only
- `GET /` - List operations
- `GET /{operation_id}` - Get operation
- `POST /` - Create operation
- `PATCH /{operation_id}` - Update operation
- `POST /{operation_id}/submit` - Submit operation
- `POST /{operation_id}/cancel` - Cancel operation
- **Location**: `app/api/routes_operations.py`

### Balances API (`/api/v1/balances/*`)
- Service authentication only
- `GET /` - List balances
- `GET /by-site` - Get balances by site
- `GET /summary` - Get balances summary
- **Location**: `app/api/routes_balances.py`

### Catalog Admin API (`/api/v1/catalog/admin/*`)
- Service authentication + role-based permissions
- Catalog entity create/update endpoints
- Chief storekeeper and root access
- **Location**: `app/api/routes_catalog_admin.py`

### Admin API (`/api/v1/admin/*`)
- Service authentication + root only
- `GET /sites` - List sites
- `POST /sites` - Create site
- `PATCH /sites/{site_id}` - Update site
- `GET /devices` - List devices
- `GET /access/user-sites` - List user-site access
- `POST /access/user-sites` - Create user-site access
- `PATCH /access/user-sites/{access_id}` - Update user-site access
- **Location**: `app/api/routes_admin.py`

### Health API (`/api/v1/health/*`)
- No authentication required
- `GET /` - Health check
- `GET /ready` - Readiness check
- `GET /db-check` - Database connectivity check
- **Location**: `app/api/routes_health.py`
## Deployment overview
- Typically deployed inside shared Docker network `backend`
- Usually accessed through nginx reverse proxy
- Common public route: `/api/` → SyncServer
- Warehouse_web (Django) calls SyncServer internally by `http://syncserver:8000`

## Tech stack
Python 3.11, FastAPI, SQLAlchemy Async, Pydantic v2, PostgreSQL, Pytest, Docker.

## Application structure
- API: `app/api/`
- Services: `app/services/`
- Repositories: `app/repos/`
- Models: `app/models/`
- Schemas: `app/schemas/`
- Infrastructure: `app/core/`, `db/init/`

## Key Modules

### Authentication (`app/api/deps.py`)
- `require_device_auth()` - Device authentication
- `require_service_auth()` - Service token validation
- `require_acting_user()` - User context validation
- `auth_catalog_headers()` - Device header collection
- `auth_service_headers()` - Service header collection

### Exceptions (`app/api/exceptions.py`)
- `SyncServerException` - Base exception class
- Specific exception classes for different error scenarios
- Standardized error format

### Services (`app/services/`)
- `operations_service.py` - Operation business logic
- `access_service.py` - Access control and role management
- `sync_service.py` - Sync processing
- `event_ingest.py` - Event ingestion
- `catalog_admin_service.py` - Catalog admin logic
- `uow.py` - UnitOfWork with all repositories

### Repositories (`app/repos/`)
- `operations_repo.py` - Operation and operation line management
- `user_site_roles_repo.py` - User-site access control
- `balances_repo.py` - Balance operations
- `sites_repo.py` - Site operations
- `catalog_repo.py` - Catalog data access
- `devices_repo.py` - Device management
- `events_repo.py` - Event log management

### Models (`app/models/`)
- `operation.py` - Operation and OperationLine entities
- `user_site_role.py` - User-site-role mapping
- `balance.py` - Balance entity
- `site.py` - Site entity
- `device.py` - Device entity
- `event.py` - Event entity
- `category.py` - Category entity
- `unit.py` - Unit entity
- `item.py` - Item entity

### Schemas (`app/schemas/`)
- `operation.py` - Operation request/response schemas
- `balance.py` - Balance schemas
- `admin.py` - Admin schemas (sites, devices, users, access)
- `catalog.py` - Catalog schemas
- `sync.py` - Sync schemas
- `common.py` - Common utilities

### Configuration (`app/core/config.py`)
- `SYNC_SERVER_SERVICE_TOKEN` - Service authentication token
- `DATABASE_URL` - Database connection
- `DEFAULT_PAGE_SIZE` - Pagination settings
- Other runtime settings
## Entry points
- Runtime: `main.py`
- Router registration: `main.py` + `app/api/routes_*.py`
- New router: `app/api/routes_business.py`

## Important models
`Event`, `Device`, `Site`, `Category`, `Unit`, `Item`, `Balance`, `UserSiteRole`.

## Important services
`SyncService`, `EventIngestService`, `CatalogAdminService`, `UnitOfWork`.

## Setup Notes
1. Set `SYNC_SERVER_SERVICE_TOKEN` in `.env` for Django integration
2. Bootstrap database with `user_site_roles` entries for web users
3. Configure Django to use service token + acting user headers
4. Sync clients continue using existing device authentication

## Architecture Principles
1. SyncServer is source of truth for inventory domain
2. Django is online client, not a sync device
3. Sync API remains device-only for offline clients
4. Business API uses service auth + acting user context
5. Access control centralized in SyncServer backend
6. Role-based permissions with clear hierarchy
7. Standardized error handling across all endpoints
8. Layered architecture with clear separation of concerns

## Error Format
All errors follow standard format:
