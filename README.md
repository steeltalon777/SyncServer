# SyncServer

SyncServer — центральный сервер синхронизации распределённой системы складского учёта.

## Назначение

Сервис синхронизирует данные между офлайн-клиентами складов и центральной базой PostgreSQL.

Поток данных:

```text
Клиенты складов (desktop / offline-first)
        ↓
      HTTP API
        ↓
    SyncServer
        ↓
    PostgreSQL
```

SyncServer выполняет три ключевые роли:

- **Event Store** — принимает и хранит события операций.
- **Sync Engine** — обеспечивает push/pull синхронизацию между клиентами и сервером.
- **Catalog Provider** — отдает инкрементальные справочники (номенклатура и категории).

## Архитектурные принципы

Система построена на событийной модели:

- все операции сохраняются как события;
- события неизменяемы;
- текущие остатки рассчитываются на основе событий.

## Технологический стек

- Python
- FastAPI
- SQLAlchemy (async)
- PostgreSQL

## Слои приложения

Проект организован по слоям:

- **API Layer** — HTTP endpoints, валидация и авторизация.
- **Service Layer** — бизнес-логика синхронизации и оркестрация сценариев.
- **Repository Layer** — доступ к данным и инкапсуляция SQL/ORM-запросов.
- **Models Layer** — ORM-модели доменных сущностей.

## Основные доменные сущности

- `Item`
- `Category`
- `Site`
- `Device`
- `Event`
- `Balance`

## Основные API endpoints

### Sync API

- `POST /ping` — heartbeat клиента и получение верхней границы `server_seq`.
- `POST /push` — прием пачки событий с идемпотентной обработкой.
- `POST /pull` — выдача событий для догонки клиента по `since_seq`.

### Catalog API

- `POST /catalog/items` — инкрементальная выгрузка номенклатуры.
- `POST /catalog/categories` — инкрементальная выгрузка категорий.

### Технические endpoints

- `GET /`
- `GET /health`
- `GET /ready`
- `GET /db_check`

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Настройка окружения

Создайте `.env` из `.env.example`:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname
DATABASE_URL_TEST=postgresql+asyncpg://user:password@localhost:5432/dbname_test
APP_ENV=dev
LOG_LEVEL=INFO
```

## Тесты

```bash
pytest -q
```

## Дополнительная документация

- Архитектура и код по слоям: `docs/code-documentation.md`
- Технический аудит и анализ: `docs/audit-syncserver.md`, `docs/tz-gap-analysis.md`
- ТЗ для клиентской части: `docs/client-development-tz.md`
