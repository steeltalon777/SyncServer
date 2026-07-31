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
- `OperationRevision`, `OperationRevisionLine` - immutable history of operation lines (INV-C1)
- `OperationCorrection`, `OperationCorrectionLine` - 3-state correction drafts (draft/applied/abandoned)
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

**Correction flow (V1, RECEIVE without acceptance):**
1. `POST /api/v1/operations/{id}/corrections` — clones current `OperationRevision` lines into a `OperationCorrection` draft (INV-C7)
2. `PUT`/`PATCH`/`POST`/`DELETE lines` — edits the correction draft (INV-C9: PUT full target state, absence = REMOVED)
3. `POST .../submit` — server computes correction_kind (INV-C8), validates deltas, atomically:
   - Creates immutable `OperationRevision` N+1 (INV-C6)
   - Applies balance delta effects
   - Rebuilds `OperationLine` current projection (INV-C2)
   - Generates documents from `OperationRevisionLine` (INV-C16)
   - Supersedes old documents (INV-C17)
   - Records audit events: `operation.correction.applied`, `document.revision_created`, `document.superseded`
4. `DELETE .../corrections/{cid}` — abandons the draft (3-state: draft/applied/abandoned)
- Lock order: Correction → Operation → inventory_subject_id ASC → Balances (INV-C18)

## Architectural Principles
- SyncServer is the source of truth for warehouse state
- Business logic belongs on the server, not in clients
- Routes stay thin; services enforce rules
- Repositories do not own business decisions
- Token-based auth is the primary integration path
- Root permissions are global; non-root permissions are site-scoped
- **Operation history is immutable** — `OperationRevision` and `OperationRevisionLine` cannot be updated after creation (INV-C1)
- `OperationLine` is a **current projection** of the latest revision, mutable for API compatibility (INV-C2)
- **Correction kind is always computed server-side** — clients never pass `correction_kind` (INV-C8)
- **V1 scope:** only RECEIVE without `acceptance_required`

## External Integrations
- PostgreSQL database
- Django-based admin / client integration over HTTP API
- Device sync clients using token-authenticated sync endpoints

## Search Normalization (TZ-SEARCH_NORMALIZATION)
Все точки поиска по SyncServer (15 точек в 10 репозиториях: catalog, asset_registers, balances, operations, reports, sites, devices, temporary_items, issue_objects, issue_object_categories) используют единый pipeline нормализации ввода:

1. **Единая утилита:** [`app/core/search_utils.py`](app/core/search_utils.py)
   - `normalize_search_text(value)` — strip → lower → ё→е → удаление пунктуации → сворачивание пробелов
   - `normalize_for_storage(value)` — для `normalized_name` колонки (None для пустого ввода)
   - `escape_like_pattern(text)` — экранирование LIKE-спецсимволов (`%`, `_`, `\\`)
   - `build_normalized_like_term(search)` — для поиска по `normalized_name` / `normalized_key` колонкам
   - `build_raw_like_term(search)` — для поиска по сырым техническим колонкам (`sku`, `code`, `device_code`, `description`, `notes`, снапшоты) — НЕ удаляет пунктуацию и НЕ сворачивает пробелы

2. **Критическое правило:** для одного поиска используются **два term**: `normalized_term` для нормализованных колонок, `raw_term` для сырых. Использование `normalized_term` для `sku`/`code` сломает поиск по артикулам с дефисами/слешами/точками (например `17М-03-49270-G` → `%17м 03 49270 g%` → 0 матчей).

3. **Event listeners:** [`app/models/events.py`](app/models/events.py) автоматически вычисляют `normalized_name` для `Item`, `Category`, `TemporaryItem`, `Site`, `Device` через `before_insert`/`before_update`. Для `IssueObject.normalized_key` и `IssueObjectCategory.normalized_key` сохранено ручное управление (другая семантика: unique constraint).

4. **Миграция `0020_search_normalization`:** добавляет `normalized_name` в `sites`/`devices`, делает backfill всех 5 таблиц правильной логикой (lowercase + ё→е + remove punctuation + collapse spaces), создаёт B-tree и GIN-trigram индексы. Расширение `pg_trgm` — обязательная зависимость.

5. **Индексы:** B-tree `ix_<table>_normalized_name` для точного соответствия и prefix-search; GIN `ix_<table>_normalized_name_trgm` (USING gin gin_trgm_ops) для ILIKE `%term%` acceleration.

## Future Architecture
- Expand test coverage for end-to-end admin integration flows
- Keep public client contracts explicit and stable
- Continue documenting stable architectural decisions in ADRs
## Temporary items Phase 1

- Реализован безопасный промежуточный этап без полного перевода на `inventory_subjects`.
- Временная ТМЦ хранится в [`TemporaryItem`](app/models/temporary_item.py:14), но для совместимости текущих write/read моделей ей создаётся скрытый backing [`Item`](app/models/item.py:14) с `is_active=false` и `source_system='temporary_item'` через [`CatalogRepo.create_item()`](app/repos/catalog_repo.py:359).
- Операции и остатки продолжают использовать [`operation_lines.item_id`](app/models/operation.py:210) и [`balances.item_id`](app/models/balance.py:20), поэтому текущее поведение read-model не ломается.
- Модерация Phase 1 меняет только жизненный цикл временной ТМЦ: approve активирует backing item, merge помечает временную ТМЦ как слитую. Полный переход на `inventory_subjects`, служебные движения резолюции и перенос read-model отложены.
