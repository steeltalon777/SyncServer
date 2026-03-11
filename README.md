# SyncServer

SyncServer — FastAPI backend для синхронизации данных распределённой складской системы. Сервис выступает источником истины (source of truth) и принимает все операции записи только через HTTP API.

## Project overview
- Принимает события от клиентских устройств (`/push`).
- Отдаёт события клиентам по курсору последовательности (`/pull`).
- Предоставляет каталог (items/categories/units) для чтения и admin-управления.
- Хранит данные в PostgreSQL через SQLAlchemy Async ORM.

## Architecture overview
Высокоуровневый поток:

`Clients → FastAPI API → Services → Repositories → PostgreSQL`

Подробности: [ARCHITECTURE.md](./ARCHITECTURE.md)

## Tech stack
- Python 3.11
- FastAPI
- SQLAlchemy 2.x (async)
- PostgreSQL
- Pydantic v2 / pydantic-settings
- Pytest
- Docker / Docker Compose

## Project structure
- `main.py` — точка входа FastAPI приложения.
- `app/api/` — HTTP роуты и зависимости (auth/rate-limit/UoW).
- `app/services/` — бизнес-логика (sync ingest, catalog admin, UoW).
- `app/repos/` — доступ к данным.
- `app/models/` — SQLAlchemy ORM модели.
- `app/schemas/` — Pydantic схемы API.
- `app/core/` — конфигурация и подключение к БД.
- `db/init/` — SQL инициализация схемы.
- `tests/` — тесты API и репозиториев.
- `docs/adr/` — архитектурные решения (ADR).

## Installation / Setup
1. Создать venv и установить зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Подготовить переменные окружения:
   - скопировать `.env.example` в `.env`
   - указать `DATABASE_URL` (и при необходимости `DATABASE_URL_TEST`)
3. Поднять PostgreSQL и применить `db/init/001_init_schema.sql` (или через docker compose).

## Running the project
### Local
```bash
uvicorn main:app --reload
```

### Docker
```bash
docker compose up --build
```

## Main modules
- **Sync module**: `/ping`, `/push`, `/pull`.
- **Catalog read/sync module**: `/catalog/items`, `/catalog/categories`, `/catalog/units`, `/catalog/categories/tree`.
- **Catalog admin module**: `/catalog/admin/*` для create/update `Unit`, `Category`, `Item`.
- **Health module**: `/health`, `/ready`, `/db_check`.

## API overview
### Sync API
- `POST /ping`
- `POST /push`
- `POST /pull`

### Catalog read API
- `POST /catalog/items`
- `POST /catalog/categories`
- `POST /catalog/units`
- `GET /catalog/categories/tree`

### Catalog admin API
- `POST /catalog/admin/units`
- `PATCH /catalog/admin/units/{unit_id}`
- `POST /catalog/admin/categories`
- `PATCH /catalog/admin/categories/{category_id}`
- `POST /catalog/admin/items`
- `PATCH /catalog/admin/items/{item_id}`

## Testing
```bash
pytest -q
```
