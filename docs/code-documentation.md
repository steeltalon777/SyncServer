# Подробная документация по серверу Sync API

Документ описывает текущую архитектуру проекта и распределение ответственности по слоям: **что за что отвечает** в кодовой базе.

## 1. Назначение сервиса

`SyncServer` — backend-сервис для офлайн/онлайн синхронизации клиентских устройств с центральной БД:

- принимает события от клиентов (`/push`),
- отдает события для догонки клиенту (`/pull`),
- отдает инкрементальные справочники (`/catalog/items`, `/catalog/categories`),
- проверяет доступность и БД (`/health`, `/ready`, `/db_check`),
- валидирует устройство по `X-Device-Token` + привязке к `site_id/device_id`.

---

## 2. Точка входа и HTTP-обвязка

## `main.py`

### Что делает

- Создает приложение `FastAPI(title="Server Sync API")`.
- Подключает роутеры:
  - sync-роуты (`/ping`, `/push`, `/pull`),
  - catalog-роуты (`/catalog/*`),
  - health-роуты (`/health`, `/ready`).
- Добавляет middleware для request correlation:
  - читает `X-Request-Id` из входящего запроса (или генерирует UUID),
  - сохраняет в `request.state.request_id`,
  - возвращает `X-Request-Id` в ответе,
  - логирует и превращает необработанные ошибки в `500 internal server error`.

### Технические endpoints

- `GET /` — простая информация о сервисе и окружении.
- `GET /db_check` — выполняет `SELECT 1` через текущую DB-сессию.

---

## 3. API-слой (`app/api`)

Слой API отвечает за:

- прием/валидацию HTTP-запросов,
- привязку зависимостей (`uow`, auth, rate-limit),
- преобразование доменных результатов в DTO ответа,
- единообразное поведение по ошибкам HTTP.

### `app/api/deps.py`

### Что за что отвечает

- `get_uow()` — DI-фабрика `UnitOfWork` на базе `AsyncSession`.
- `require_device_auth()` — авторизация устройства:
  - проверяет наличие `X-Device-Token`,
  - загружает устройство,
  - валидирует: `device.site_id == site_id`, `is_active == True`, токен совпадает,
  - обновляет `last_seen_at`, `last_ip`, `client_version`.
- `auth_catalog_headers()` — считывает catalog-заголовки: `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`.
- `InMemoryRateLimiter` + `enforce_rate_limit()`:
  - `/ping`: минимум 5 секунд между запросами для пары IP+device,
  - `/push`: минимум 1 секунда между запросами для пары IP+device.
- `get_request_id()` и `get_client_ip()` — служебные хелперы для логирования/трассировки.

> Важно: rate-limit в памяти процесса, без распределенного state.

### `app/api/routes_sync.py`

### `POST /ping`

Назначение:

- «легкий heartbeat» клиента,
- проверка авторизации устройства,
- возврат верхней границы `server_seq_upto` для текущего `site_id`.

Пайплайн:

1. rate-limit,
2. транзакция UoW,
3. `require_device_auth`,
4. чтение max `server_seq` по сайту,
5. ответ `PingResponse`.

### `POST /push`

Назначение:

- прием пачки клиентских событий,
- идемпотентная классификация на accepted/duplicates/rejected.

Пайплайн:

1. валидация размера батча (`MAX_PUSH_EVENTS`),
2. rate-limit,
3. транзакция UoW,
4. `require_device_auth`,
5. `SyncService.process_push(...)`,
6. дополнительный пересчет `server_seq_upto` как max(локальный из обработки, max в БД),
7. логирование uuid_collision и метрик батча.

### `POST /pull`

Назначение:

- отдать клиенту события данного `site_id`, у которых `server_seq > since_seq`, по возрастанию `server_seq`.

Пайплайн:

1. лимит из payload или `DEFAULT_PULL_LIMIT`,
2. транзакция UoW,
3. `require_device_auth`,
4. выборка событий через repo,
5. вычисление `next_since_seq` как `server_seq` последнего события (или текущее `since_seq`, если список пуст),
6. возврат `PullResponse`.

### `app/api/routes_catalog.py`

Роутер имеет префикс `/catalog`.

- `POST /catalog/items`
- `POST /catalog/categories`

Оба endpoint:

1. читают auth-заголовки через `auth_catalog_headers`,
2. в транзакции выполняют `require_device_auth`,
3. читают список сущностей с инкрементальным фильтром `updated_after` и лимитом,
4. возвращают `next_updated_after` = max(`updated_at`) из выданной страницы.

### `app/api/routes_health.py`

- `GET /health` — liveness,
- `GET /ready` — readiness + проверка `SELECT 1` в БД.

---

## 4. Конфигурация и БД (`app/core`)

### `app/core/config.py`

`Settings` (pydantic-settings) загружает:

- `DATABASE_URL`
- `DATABASE_URL_TEST`
- `APP_ENV`
- `LOG_LEVEL`
- `DEFAULT_PAGE_SIZE`
- `ALLOWED_ORIGINS`
- `MAX_PUSH_EVENTS`
- `DEFAULT_PULL_LIMIT`

`get_settings()` закэширован через `lru_cache`.

### `app/core/db.py`

Отвечает за:

- создание async engine SQLAlchemy,
- фабрику `SessionFactory` (`async_sessionmaker`),
- FastAPI-зависимость `get_db()`.

---

## 5. Модель данных (`app/models`)

Слой ORM — это отображение на существующие PostgreSQL-таблицы.

- `Site` (`sites`) — справочник площадок.
- `Device` (`devices`) — устройства, включая `registration_token`, `last_seen_*`, версию клиента.
- `Category` (`categories`) — категории (иерархия через `parent_id`).
- `Item` (`items`) — номенклатура.
- `Event` (`events`) — журнал событий синхронизации:
  - ключ идемпотентности `event_uuid`,
  - серверный порядковый `server_seq` для pull,
  - `payload` + `payload_hash`.
- `Balance` (`balances`) — текущее количество товара по `(site_id, item_id)`.
- `UserSiteRole` (`user_site_roles`) — роли пользователей на площадке.

---

## 6. DTO-контракты (`app/schemas`)

### `app/schemas/sync.py`

#### Вход

- `PingRequest`
- `PushRequest` → `events: list[EventIn]`
- `PullRequest`

`EventIn` содержит:

- `event_uuid`
- `event_type`
- `event_datetime`
- `schema_version`
- `payload` (`EventPayload` с `lines: list[EventLine]`, где `qty` — Decimal с точностью `18,3`)

#### Выход

- `PingResponse`
- `PushResponse` (`accepted`, `duplicates`, `rejected`, `server_seq_upto`, `server_time`)
- `PullResponse` (`events`, `next_since_seq`, `server_seq_upto`, `server_time`)

### `app/schemas/catalog.py`

- `CatalogRequest` (`updated_after`, `limit`)
- `ItemDto`, `CategoryDto`
- `CatalogItemsResponse`, `CatalogCategoriesResponse`

### `app/schemas/common.py`

`ORMBaseModel` — базовая модель для корректной сериализации ORM/типов (`datetime`, `Decimal`, `UUID`).

---

## 7. Репозитории (`app/repos`)

Репозитории не содержат бизнес-оркестрацию, только доступ к данным.

- `SitesRepo` — чтение площадок.
- `DevicesRepo` — чтение/создание устройств, обновление `last_seen`.
- `EventsRepo`:
  - `get_by_uuid`,
  - `insert_event`,
  - `pull(site_id, since_seq, limit)`,
  - `get_max_server_seq(site_id)`,
  - `compute_payload_hash(payload)` (канонический JSON + SHA-256).
- `CatalogRepo` — инкрементальная выборка items/categories по `updated_after`.
- `BalancesRepo` — upsert/блокировка записей балансов.

---

## 8. Сервисы (`app/services`)

### `UnitOfWork`

Транзакционная оболочка:

- при `async with` открывает транзакцию,
- при успехе коммитит,
- при ошибке ролбэк,
- агрегирует репозитории в одном месте (`uow.events`, `uow.catalog` и т.д.).

### `EventIngestService`

Ядро идемпотентности:

1. ищет событие по `event_uuid`,
2. считает `payload_hash`,
3. если записи нет → `accepted` (insert),
4. если hash совпадает → `duplicate_same_payload`,
5. если hash отличается → `uuid_collision`.

### `SyncService`

Оркестратор push-пакета:

- последовательно обрабатывает `events[]` через `EventIngestService`,
- собирает `PushResponse` по трем корзинам,
- обновляет `server_seq_upto`.

---

## 9. Транзакционные и доменные инварианты

- Идемпотентность опирается на пару: `event_uuid` + совпадение `payload_hash`.
- `pull` всегда возвращает события в порядке `server_seq ASC`.
- Авторизация устройства обязательна для sync и catalog endpoints.
- Лимиты запросов:
  - `MAX_PUSH_EVENTS` на размер push-пакета,
  - rate-limit на `/ping` и `/push`.

---

## 10. Логирование и трассировка

- Все ключевые операции логируются с `request_id`.
- При наличии коллизии UUID в `push` пишется warning.
- Middleware гарантирует корреляционный заголовок `X-Request-Id` в ответе.

---

## 11. Тесты

Текущие тесты покрывают:

- репозиторный слой (insert/duplicate/collision/pull ordering),
- HTTP-слой (`/ping`, `/push`, `/pull`, catalog, auth).

Файлы:

- `tests/test_events_repo.py`
- `tests/test_http_sync.py`

---

## 12. Ограничения текущей реализации

- In-memory rate-limit не подходит для горизонтально масштабированного продакшена без внешнего хранилища (например, Redis).
- Нет отдельной версии API (`/v1`) — все роуты в корне.
- Бизнес-обработка событий (изменение `balances`) в текущей версии ограничена архитектурной заготовкой и не выделена в полноценный доменный pipeline.
