# SyncServer

FastAPI-сервис для синхронизации событий между устройствами и сервером. Проект использует асинхронный SQLAlchemy и ориентирован на работу с PostgreSQL. В текущем состоянии реализованы базовые модели (`sites`, `devices`, `events`), схемы для `push` и репозитории для CRUD/синхронизации.

## Что уже реализовано

- Асинхронное подключение к БД через `AsyncEngine`/`AsyncSession`.
- Модели SQLAlchemy:
  - `Site`
  - `Device`
  - `Event`
- Репозитории:
  - `SiteRepo`
  - `DeviceRepo`
  - `EventRepo`
- Обработка `push`-событий:
  - вставка нового события;
  - дедупликация по `event_uuid` + `payload_hash`;
  - выявление коллизии UUID (одинаковый `event_uuid`, разный payload).
- Базовые служебные эндпоинты (`/`, `/db_check`) и простые эндпоинты для `sites`/`devices`.

---

## Архитектура

```text
main.py
└── app/
    ├── core/
    │   ├── config.py      # чтение .env (Settings)
    │   ├── db.py          # engine + sessionmaker + get_db
    │   └── json_encoder.py
    ├── models/
    │   ├── base.py
    │   ├── site.py
    │   ├── device.py
    │   └── event.py
    ├── repos/
    │   ├── site_repo.py
    │   ├── device_repo.py
    │   └── event_repo.py
    └── schemas/
        └── event.py
```

Подробная документация по коду и потокам данных: `docs/code-documentation.md`.
Сопоставление с вашим ТЗ v1: `docs/tz-gap-analysis.md`.

---

## Запуск

### 1) Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Настройка

```bash
cp .env.example .env
```

Минимально заполните:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname
APP_ENV=dev
LOG_LEVEL=INFO
```

### 3) Старт сервера

```bash
uvicorn main:app --reload
```

---

## Важные замечания

- Сейчас на `startup` вызывается `Base.metadata.create_all(...)` (удобно для локальной разработки).
- По вашему ТЗ v1 миграции и создание таблиц должен вести Django, поэтому в прод-контуре это поведение нужно отключить.
- `server_seq` сейчас вычисляется в приложении как `max(server_seq)+1`; в ТЗ предполагается генерация БД (`BIGSERIAL`) для безопасной конкурентной записи.

---

## API (текущее состояние)

- `GET /` — health/info
- `GET /db_check` — проверка подключения к БД
- `POST /sites/`, `GET /sites/`
- `POST /devices/`, `GET /devices/`, `GET /devices/{device_id}`
- `PATCH /devices/{device_id}/heartbeat`
- `POST /push` — приём пачки событий
- `GET /pull` — получение событий по `site_id` и `since_seq`

Примеры ручной проверки: `test_main.http`.

---

## Следующий этап по ТЗ

Согласно вашему ТЗ, для полного v1 стоит добавить:

- модели `categories`, `items`, `balances`, `user_site_roles`;
- отдельные DTO для `catalog`/`sync`/`common`;
- Unit of Work слой;
- тесты на duplicate / uuid_collision / pull-сортировку;
- отказ от `create_all` в пользу существующей схемы Django.
