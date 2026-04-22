# Architecture

## System Overview
SyncServer is an async FastAPI backend for warehouse management and synchronization. It centralizes users, site access, catalog data, operations, balances, devices, and event sync in one PostgreSQL-backed service.

## High-Level Architecture
```text
Clients
  - Django admin / web client
  - User-facing clients
  - Device sync clients
        |
        v
API / Application Layer
  - FastAPI routes
  - request validation
  - authentication / access checks
        |
        v
Service Layer
  - business rules
  - workflows
  - invariants
        |
        v
Repository / Data Layer
  - query composition
  - persistence
  - transaction boundaries via UnitOfWork
        |
        v
Database
  - PostgreSQL
```

## Application Layers

### API Layer
- Lives in `app/api/`
- Owns HTTP contracts, request parsing, header-based auth, and error mapping
- Delegates business behavior to services or repository-backed workflows

### Service Layer
- Lives in `app/services/`
- Owns domain workflows and business invariants
- Examples: access control, catalog admin workflows, operations lifecycle, sync ingestion

### Repository / Data Layer
- Lives in `app/repos/`
- Owns SQLAlchemy queries and persistence only
- Accessed through `UnitOfWork` to keep one request/transaction boundary

### Models / Entities
- Lives in `app/models/`
- SQLAlchemy ORM models define persistent state and relations

## Data Model
Core entities:
- `User` - authenticated user with global role and default site
- `UserAccessScope` - per-site permissions (`can_view`, `can_operate`, `can_manage_catalog`)
- `Site` - warehouse / working location
- `Device` - sync-capable registered client device
- `Category`, `Item`, `Unit` - global catalog
- `Operation`, `OperationLine` - inventory-changing documents
- `Balance` - derived inventory state
- `Event` - synced device events

**Asset Registers (Acceptance System):**
- `PendingAcceptanceBalance` - items awaiting acceptance after operation submission
- `LostAssetBalance` - unaccepted items (lost assets) waiting for resolution
- `IssuedAssetBalance` - items issued to recipients
- `OperationAcceptanceAction` - audit log of acceptance and resolution actions

Key model choices:
- Sites are integer IDs
- Users use UUID IDs and token-based auth
- Catalog entities are global, not site-owned
- Balances are derived from operations, not edited directly
- Asset registers track intermediate states between operation submission and final acceptance

## Data Flow
Typical request flow:

`Client -> FastAPI route -> dependency auth/access -> service -> repository -> PostgreSQL -> response DTO`

Example:
1. Client sends `POST /api/v1/operations`
2. API validates payload and resolves `X-User-Token`
3. Service checks site permissions and business invariants
4. Repository writes operation and related lines
5. Transaction commits through `UnitOfWork`
6. Response DTO is returned

## Architectural Principles
- SyncServer is the source of truth for warehouse state
- Business logic belongs on the server, not in clients
- Routes stay thin; services enforce rules
- Repositories do not own business decisions
- Token-based auth is the primary integration path
- Root permissions are global; non-root permissions are site-scoped

## External Integrations
- PostgreSQL database
- Django-based admin / client integration over HTTP API
- Device sync clients using token-authenticated sync endpoints

## Future Architecture
- Expand test coverage for end-to-end admin integration flows
- Keep public client contracts explicit and stable
- Continue documenting stable architectural decisions in ADRs
## Temporary items Phase 1

- Реализован безопасный промежуточный этап без полного перевода на `inventory_subjects`.
- Временная ТМЦ хранится в [`TemporaryItem`](app/models/temporary_item.py:14), но для совместимости текущих write/read моделей ей создаётся скрытый backing [`Item`](app/models/item.py:14) с `is_active=false` и `source_system='temporary_item'` через [`CatalogRepo.create_item()`](app/repos/catalog_repo.py:359).
- Операции и остатки продолжают использовать [`operation_lines.item_id`](app/models/operation.py:210) и [`balances.item_id`](app/models/balance.py:20), поэтому текущее поведение read-model не ломается.
- Модерация Phase 1 меняет только жизненный цикл временной ТМЦ: approve активирует backing item, merge помечает временную ТМЦ как слитую. Полный переход на `inventory_subjects`, служебные движения резолюции и перенос read-model отложены.
