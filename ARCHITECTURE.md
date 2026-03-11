# ARCHITECTURE

## System Overview
SyncServer — backend-сервис синхронизации для распределённой складской системы. Сервис принимает события от клиентских приложений, хранит их в PostgreSQL как журнал изменений и предоставляет API для pull/push синхронизации и управления каталогом номенклатуры.

## High-Level Architecture
```text
Clients (Django / WPF / mobile / offline)
                ↓
        API / Application Layer (FastAPI routers)
                ↓
            Service Layer
                ↓
       Repository / Data Layer
                ↓
             PostgreSQL
```

## Application Layers
### API layer
- `main.py` и роутеры в `app/api/*`.
- Отвечает за HTTP-контракт, валидацию входов, auth/rate-limit зависимости, формирование response.

### Service layer
- `app/services/*`.
- Содержит бизнес-правила: идемпотентный ingest событий, валидации админ-операций каталога, границы транзакций через UnitOfWork.

### Repository / data layer
- `app/repos/*`.
- Инкапсулирует SQLAlchemy-запросы, выборки, обновления и вспомогательные data-алгоритмы (например, построение дерева категорий).

### Models / entities
- `app/models/*`.
- ORM-модели таблиц `sites`, `devices`, `events`, `categories`, `items`, `units`, `balances`, `user_site_roles`.

## Data Model
Ключевые сущности:
- `Event` — журнал доменных событий (event sourcing для синхронизации), с `event_uuid`, `server_seq`, `payload_hash`.
- `Device` — зарегистрированное клиентское устройство с токеном и привязкой к `Site`.
- `Site` — склад/площадка (tenant-like область данных).
- `Category` — дерево категорий через self-reference `parent_id`.
- `Unit` — единицы измерения.
- `Item` — номенклатура, связанная с категорией и единицей.
- `Balance` — остаток `item` на `site`.

## Data Flow
Типовой поток sync push:
1. Client вызывает `POST /push`.
2. API слой валидирует batch, применяет rate limit и device auth.
3. `SyncService` передаёт каждое событие в `EventIngestService`.
4. `EventsRepo` проверяет `event_uuid`, считает hash payload и сохраняет/дедуплицирует запись.
5. PostgreSQL присваивает `server_seq`, который клиент использует как курсор pull.

Общий шаблон: **Client → API → Service → Repository → Database**.

## Architectural Principles
- **HTTP-only integration**: клиенты не пишут в БД напрямую.
- **Thin routers**: бизнес-логика вынесена в сервисы.
- **Transactional UoW**: один запрос = одна транзакция UnitOfWork.
- **Idempotent ingest**: `event_uuid + payload_hash` для дедупликации и detection коллизий.
- **Soft deactivation**: для каталога используется `is_active`, а не hard delete.
- **Incremental sync**: `server_seq` и `updated_at` используются как курсоры синхронизации.

## External Integrations
- PostgreSQL (основное хранилище).
- Docker / Docker Compose для локального окружения.
- Прямых внешних SaaS/API интеграций в коде нет.

## Future Architecture
- Выделение auth/rate-limit из in-memory в отдельный shared store (например Redis) для горизонтального масштабирования.
- Добавление миграций (Alembic) поверх SQL bootstrap.
- Разделение bounded contexts (sync/catalog/admin) в отдельные модули при росте домена.
