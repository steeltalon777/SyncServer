# SyncServer

SyncServer — FastAPI backend распределённой складской системы и основной source of truth.

## Architecture overview

```text
Clients (Django/WPF/mobile/offline)
            ↓
         HTTP API
            ↓
     SyncServer (FastAPI)
            ↓
        PostgreSQL
```

Принцип: клиенты не пишут в БД напрямую. Все операции записи идут через HTTP API SyncServer.

## Project structure

- `main.py` — entrypoint FastAPI приложения
- `app/api` — роуты и зависимости
- `app/services` — бизнес-логика
- `app/repos` — доступ к данным
- `app/models` — SQLAlchemy ORM
- `app/schemas` — Pydantic схемы
- `db/init` — SQL инициализация схемы
- `tests` — интеграционные и repo тесты

## Catalog module

Сущности каталога:

- `Category` (дерево через `parent_id`)
- `Unit`
- `Item`

Каталог поддерживает read/sync API и отдельный admin write API.

## API overview

### Sync API

- `POST /ping`
- `POST /push`
- `POST /pull`

### Catalog read/sync API

- `POST /catalog/items`
- `POST /catalog/categories`
- `POST /catalog/units`
- `GET /catalog/categories/tree`

### Catalog admin write API

- `POST /catalog/admin/units`
- `PATCH /catalog/admin/units/{unit_id}`
- `POST /catalog/admin/categories`
- `PATCH /catalog/admin/categories/{category_id}`
- `POST /catalog/admin/items`
- `PATCH /catalog/admin/items/{item_id}`

Удаление реализовано как soft deactivate через `is_active=false`.

## Clients

- Django `Warehouse_web` (trusted client)
- WPF client (planned)
- mobile clients (planned)
- offline warehouse clients (planned)

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Docker

```bash
docker compose up --build
```

## Testing

```bash
pytest -q
```
