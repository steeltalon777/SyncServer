# AI_ENTRY_POINTS

## Server entrypoints
- `main.py` — создание `FastAPI` app, middleware request-id, подключение роутеров.

## API layer
- `app/api/routes_sync.py` — `/ping`, `/push`, `/pull`.
- `app/api/routes_catalog.py` — read/sync API каталога.
- `app/api/routes_catalog_admin.py` — admin create/update API каталога.
- `app/api/routes_health.py` — health/readiness endpoints.
- `app/api/deps.py` — зависимости: UoW, auth headers, rate limiter.

## Service layer
- `app/services/sync_service.py` — orchestration push processing.
- `app/services/event_ingest.py` — идемпотентная обработка событий.
- `app/services/catalog_admin_service.py` — бизнес-правила каталога.
- `app/services/uow.py` — транзакционная обёртка + доступ к repos.

## Repository / Data layer
- `app/repos/events_repo.py`
- `app/repos/catalog_repo.py`
- `app/repos/devices_repo.py`
- `app/repos/sites_repo.py`
- `app/repos/balances_repo.py`

## Models / Entities
- `app/models/event.py`
- `app/models/device.py`
- `app/models/site.py`
- `app/models/category.py`
- `app/models/unit.py`
- `app/models/item.py`
- `app/models/balance.py`
- `app/models/user_site_role.py`

## Configuration
- `app/core/config.py` — env-based settings (`DATABASE_URL`, limits, log level).
- `app/core/db.py` — async SQLAlchemy engine/session factory.
- `.env.example` — пример env-конфига.
- `docker-compose.yml` — локальное окружение приложения и БД.
- `db/init/001_init_schema.sql` — bootstrap SQL schema.
