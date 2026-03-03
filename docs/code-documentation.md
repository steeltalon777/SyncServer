# Документация кода (текущее состояние)

## 1. Конфигурация

### `app/core/config.py`

`Settings` читает параметры из `.env`:
- `DATABASE_URL`
- `APP_ENV`
- `LOG_LEVEL`

`get_settings()` кешируется через `lru_cache`, чтобы один раз создать объект конфигурации на процесс.

### `app/core/db.py`

- Создаётся async engine (`create_async_engine`).
- Создаётся фабрика сессий `AsyncSessionLocal`.
- `get_db()` — dependency для FastAPI, выдаёт и закрывает `AsyncSession`.

## 2. Модели

### `app/models/base.py`

Базовый `DeclarativeBase` для всех ORM-классов.

### `app/models/site.py`

Таблица `sites`:
- `id` (UUID, PK)
- `code` (unique)
- `name`
- `is_active`
- `created_at`

Есть relationship на `Device` через `devices`.

### `app/models/device.py`

Таблица `devices`:
- `id` (UUID, PK)
- `site_id` (FK -> `sites.id`)
- `name`
- `registration_token`
- `last_ip`
- `last_seen_at`
- `client_version`
- `is_active`
- `created_at`

Есть relationship `site`.

### `app/models/event.py`

Таблица `events`:
- `event_uuid` (UUID, PK, присылает клиент)
- `site_id`, `device_id`, `user_id`
- `event_type`, `event_datetime`, `received_at`
- `schema_version`
- `payload` (JSON)
- `server_seq` (unique)
- `payload_hash`

Назначение: безопасно принимать события и различать:
- повтор того же payload (`duplicate`);
- коллизию UUID (`uuid_collision`).

## 3. Pydantic-схемы

### `app/schemas/event.py`

Основные DTO:
- `EventLine`
- `EventPayload`
- `EventIn`
- `PushRequest`
- `PushResponse`

`EventPayload.lines` валидируется как непустой массив.
`qty` хранится как `Decimal`.

## 4. Репозитории

### `app/repos/site_repo.py`

- `get_by_id`
- `get_by_code`
- `create`

### `app/repos/device_repo.py`

- `get_by_id`
- `get_by_site`
- `create`
- `update_last_seen`

### `app/repos/event_repo.py`

- `_compute_payload_hash(payload)` — SHA-256 от канонизированного JSON.
- `get_next_seq()` — вычисляет `max(server_seq)+1`.
- `get_by_uuid(event_uuid)`.
- `create_event(...)` — создаёт событие и делает `flush()`.
- `process_event(...)` — реализует логику `accepted` / `duplicate` / `rejected(UUID_COLLISION)`.
- `pull_events(site_id, since_seq, limit)` — выборка в порядке `server_seq`.

## 5. Поток обработки `POST /push`

1. Приходит `PushRequest`.
2. Для каждого `EventIn` вызывается `EventRepo.process_event(...)`.
3. Результат раскладывается по массивам:
   - `accepted`
   - `duplicates`
   - `rejected`
4. После обработки всей пачки выполняется `commit()`.

## 6. Ограничения и риски

- `server_seq` считается в приложении, что может приводить к гонкам при высокой конкуренции.
- В `main.py` на startup выполняется `create_all`, что конфликтует с подходом “схемой управляет Django”.
- Пока отсутствуют модельные слои `categories/items/balances/user_site_roles` и Unit of Work.
