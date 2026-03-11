# AI_CONTEXT

## System architecture
SyncServer построен как слой синхронизации и каталогизации данных для складских клиентов. Архитектура слоистая: API слой только оркестрирует запрос, доменная логика в сервисах, SQL доступ в репозиториях.

## Backend rules
- Не добавлять бизнес-логику в роуты (`app/api`).
- Любые доменные проверки размещать в `app/services`.
- Транзакционные операции выполнять внутри `UnitOfWork` (`async with uow`).
- Исключения уровня бизнес-правил возвращать как HTTP 4xx из сервисов/роутов согласованно.

## Database rules
- PostgreSQL — единственное хранилище сервиса.
- Избегать переноса доменной логики в триггеры/процедуры БД.
- Использовать UUID как primary id для сущностей домена.
- Для sync-событий использовать `server_seq` как монотонный курсор выдачи.

## Layered architecture
### API
`app/api/routes_*.py`, `main.py`, `app/api/deps.py`.

### Services
`app/services/sync_service.py`, `event_ingest.py`, `catalog_admin_service.py`, `uow.py`.

### Repositories
`app/repos/*.py` — все запросы и запись в БД через repo-слой.

### Models
`app/models/*.py` — ORM отражение таблиц и связей.

## Client rules
- Поддерживаемые клиенты: web (Django), desktop/mobile/offline клиенты.
- Клиенты обязаны обращаться только к HTTP API сервера.
- Device-level аутентификация (`X-Device-Token`) обязательна для sync/catalog endpoints.

## Architecture constraints
- Нельзя писать напрямую в PostgreSQL из клиентских приложений.
- Нельзя смешивать sync ingestion и catalog admin логику в одном endpoint.
- Нельзя ломать идемпотентность ingest (`event_uuid + payload_hash`).
- Для каталога использовать soft deactivation (`is_active`), не hard delete.
