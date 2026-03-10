# SyncServer

SyncServer — сервер синхронизации для распределённого складского учёта с офлайн-клиентами.

## Что делает сервис

SyncServer решает три задачи:

- принимает события от устройств (`/push`);
- отдаёт недостающие события для догонки (`/pull`);
- отдаёт справочники номенклатуры и категорий (`/catalog/*`).

Поток данных:

```text
Офлайн-клиенты складов
        ↓
      HTTP API
        ↓
    SyncServer
        ↓
    PostgreSQL
```

## Технологии

- Python 3.11+
- FastAPI
- SQLAlchemy Async + asyncpg
- PostgreSQL 16

## Структура проекта

- `app/api` — HTTP-роуты и зависимости
- `app/services` — сценарии синхронизации и бизнес-логика
- `app/repos` — слой доступа к данным
- `app/models` — ORM-модели
- `app/schemas` — Pydantic-схемы API
- `db/init` — SQL-инициализация схемы БД
- `tests` — автотесты

## API (кратко)

### Синхронизация

- `POST /ping` — heartbeat клиента и получение верхней границы `server_seq_upto`
- `POST /push` — приём пачки событий (идемпотентно)
- `POST /pull` — выдача событий начиная с `since_seq`

### Каталоги

- `POST /catalog/items` — инкрементальная выдача номенклатуры
- `POST /catalog/categories` — инкрементальная выдача категорий
- `GET /catalog/categories` — дерево категорий

### Технические эндпоинты

- `GET /` — базовая информация о сервисе
- `GET /health` — liveness-check
- `GET /ready` — readiness-check с проверкой БД
- `GET /db_check` — ручная проверка подключения к БД

## Авторизация и заголовки

Для рабочих эндпоинтов (`/ping`, `/push`, `/pull`, `/catalog/*`) используются заголовки устройства:

- `X-Device-Token`
- `X-Client-Version`

Также в middleware проставляется `X-Request-Id`:

- если клиент прислал `X-Request-Id`, он будет использован;
- иначе сервер сгенерирует UUID и вернёт его в ответе.

## Конфигурация

Скопируйте `.env.example` в `.env` и при необходимости скорректируйте значения:

```bash
cp .env.example .env
```

Основные переменные:

- `DATABASE_URL` — основное подключение к PostgreSQL
- `DATABASE_URL_TEST` — тестовая БД
- `APP_ENV` — окружение (`dev`, `prod` и т.д.)
- `LOG_LEVEL` — уровень логирования
- `MAX_PUSH_EVENTS` — максимум событий в одном `/push`
- `DEFAULT_PULL_LIMIT` — лимит по умолчанию для `/pull`

## Локальный запуск (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Сервис будет доступен на `http://127.0.0.1:8000`.

## Запуск через Docker Compose

```bash
docker compose up --build
```

- PostgreSQL поднимется на `localhost:5432`
- API будет доступен на `localhost:8000`
- SQL-инициализация загрузится из `db/init/001_init_schema.sql`

## Тестирование

```bash
pytest -q
```

## Дополнительная документация

- `docs/code-documentation.md` — описание слоёв и структуры кода
- `docs/audit-syncserver.md` — технический аудит
- `docs/tz-gap-analysis.md` — gap-анализ требований
- `docs/client-development-tz.md` — ТЗ для клиентской команды
