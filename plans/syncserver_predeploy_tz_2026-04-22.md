# ТЗ: доводка SyncServer до состояния pre-deploy

Дата фиксации: 2026-04-22

Статус документа: рабочее ТЗ по результатам live-проверки и локального прогона тестов

Цель: не переписывать систему, а быстро и безопасно довести SyncServer до преддеплойного состояния, сохранив уже реализованный функционал версии склада 2.0 и сняв реальные runtime-блокеры.

Границы этого ТЗ:
- В фокусе только `SyncServer`.
- Django на `8001` в это ТЗ не включён.
- Здесь нет требований “переделать архитектуру”.
- Здесь есть только конкретные доработки, проверки и тестовые задачи, разбитые на маленькие шаги.

## 1. Что было проверено

Проверка проводилась по двум контурам:
- Живой API стенда на `http://127.0.0.1:8000/api/v1`.
- Полный локальный прогон `pytest` по репозиторию `SyncServer` на поднятой тестовой БД.

Команды и прогоны, на которые опирается это ТЗ:
- `python scripts/phase1_stand_check.py`
- `python -m pytest -q`
- Точечные прогоны падений: `test_catalog_admin_soft_delete`, `test_http_sync`, `test_reports_read_model`
- Отдельный live workflow через API: сайт -> пользователи -> scopes -> каталог -> RECEIVE с temporary item -> submit -> документы -> merge -> asset registers
- Проверка Alembic/схемы БД: `alembic current`, `alembic heads`, запросы в `information_schema` и `pg_constraint`

## 2. Что подтверждено как работающее

Подтверждено на живом стенде:
- `GET /health` и `GET /ready` работают.
- Root-аутентификация через `X-User-Token` работает.
- Аутентификация с `X-Device-Token` для root-контекста работает.
- Создание `site`, `user`, rotation token и назначение scopes работают.
- Catalog admin CRUD на создание `unit`, `category`, `item` работает.
- `hashtags` у `item` сохраняются и читаются.
- Создание `RECEIVE`-операции с mixed lines работает.
- Inline `temporary_item` при создании операции создаётся.
- Права на temporary items для `chief_storekeeper` и запрет для `observer` работают.
- `PATCH /operations/{id}/effective-at` работает.
- `POST /operations/{id}/submit` работает.
- Автогенерация документа на submit работает.
- `GET /documents/operations/{operation_id}/documents` работает.
- `GET /documents/{document_id}` работает.
- `GET /documents/{document_id}/render?format=html` работает.
- Ручная генерация `waybill` через shortcut endpoint работает.
- `POST /temporary-items/{id}/merge` работает.
- `POST /temporary-items/{id}/approve-as-item` корректно блокируется, если по ТМЦ есть активные pending/lost/issued registers.
- `GET /pending-acceptance`, `GET /lost-assets`, `GET /issued-assets` живы как роуты и отвечают.

Подтверждено по коду и/или unit/integration:
- Временная ТМЦ реализована для write-path операций.
- Механизм `effective_at` реализован на модели, схемах, сервисе и API.
- Snapshot-поля на строках операций есть и заполняются.
- `hashtags` есть и у `item`, и у `temporary_item`.
- Batch CSV/import сценарий для справочников существует и имеет локальные тесты.

## 3. Сводка по тестам

Полный `pytest` дал итог:
- `160 passed`
- `10 failed`
- `23 errors`
- `2 skipped`
- `4 deselected`
- `1 xfailed`

Ключевой вывод:
- Значимая часть кодовой базы жива.
- Основной шум в тестах делится на две группы.
- Первая группа: реальные продуктовые проблемы, подтверждённые runtime.
- Вторая группа: тесты и stand-обвязка отстали от текущего контракта и модели данных.

## 4. Реальные блокеры, найденные на стенде

### Блокер B1. `GET /documents` падает с `500`

Симптом:
- На живом стенде `GET /documents` возвращает `500 internal server error` и для root, и для пользователя с доступом к площадке.

Подтверждение:
- Live API прогон.
- По коду: `app/api/routes_documents.py` вызывает `uow.documents.list_documents(filter_obj=filter_obj, ...)`.
- Репозиторий `app/repos/documents_repo.py` принимает аргумент `filter`, а не `filter_obj`.

Вероятная причина:
- Неверное имя keyword-аргумента в вызове репозитория.

Минимальная задача:
- Исправить вызов `list_documents` в `routes_documents.py`.
- Прогнать live и локальные тесты для списка документов.

Критерий готовности:
- `GET /documents` возвращает `200`.
- Root видит документы.
- Пользователь с доступом к площадке видит документы хотя бы по `site_id`.

### Блокер B2. `POST /operations/{id}/accept-lines` падает с `500`

Симптом:
- На живом стенде при приёмке mixed RECEIVE с temporary item endpoint падает с `500`.

Подтверждение:
- Live workflow.
- Локальный ASGI-прогон на той же БД дал точный stacktrace.
- Ошибка: `null value in column "item_id" of relation "balances" violates not-null constraint`.

Техническая картина:
- `BalancesRepo.upsert()` вставляет `Balance(site_id, inventory_subject_id, qty)` без `item_id`.
- Для inventory-subject сценариев это допустимо на уровне Python-модели.
- Но живая БД держит `public.balances.item_id` как `NOT NULL`.
- В результате временная ТМЦ не может пройти приёмку.

Дополнительное наблюдение:
- `pending_acceptance_balances.item_id` и `lost_asset_balances.item_id` в `public` уже nullable.
- `balances.item_id` в `public` всё ещё `NOT NULL`.
- Alembic при этом стоит на `0008_inventory_subjects_backfill (head)`.

Минимальная задача:
- Согласовать код, ORM и живую схему `balances`.
- Убрать schema drift.
- Проверить, должен ли `balances.item_id` быть nullable или должен заполняться legacy/backing item id.

Критерий готовности:
- `accept-lines` возвращает `200`.
- После приёмки появляются корректные balance rows.
- Приёмка работает и для временной ТМЦ, и для обычной номенклатуры.

### Блокер B3. Idempotent replay для mixed RECEIVE работает некорректно

Симптом:
- Повторный `POST /operations` с тем же `client_request_id` и тем же payload для RECEIVE с temporary line + catalog line возвращает `409 Idempotency conflict`.

Подтверждение:
- `scripts/phase1_stand_check.py` стабильно падает именно на втором `POST /operations`.
- Отдельный live workflow воспроизвёл тот же конфликт.

Причина по коду:
- В `app/services/operations_service.py` существующие строки сравниваются через `item_name_snapshot`.
- Для обычной строки existing payload содержит snapshot имени catalog item.
- Для incoming payload non-temporary line сравнивается как `item_name_snapshot=None`.
- Из-за этого mixed payload определяется как “different payload”, хотя запрос идентичен.

Минимальная задача:
- Исправить сравнение replay payload для операций с temporary items.
- Сравнивать non-temporary line по `item_id` или по согласованному нормализованному ключу.
- Сохранить защиту от реального изменения payload.

Критерий готовности:
- Второй identical POST по тому же `client_request_id` возвращает ту же операцию и `200`.
- Действительно изменённый payload продолжает возвращать `409`.

### Блокер B4. Machine/batch-функционал не выставлен наружу

Симптом:
- В коде есть `MachineService`, `MachineRepo`, `MachineBatch*` схемы и таблицы.
- В OpenAPI живого сервера machine routes отсутствуют.

Подтверждение:
- В `main.py` machine router не зарегистрирован.
- В live OpenAPI нет paths с `/machine`.

Риск:
- Если batch-работа со справочниками ожидалась как внешний API, то сейчас она не доведена до пользовательского состояния.

Минимальная задача:
- Определиться, является ли machine/batch частью преддеплоя.
- Если да, то зарегистрировать router и закрыть API-контракт.
- Если нет, то явно вынести из релизного scope и не обещать в changelog/API.

Критерий готовности:
- Либо machine API доступен и протестирован.
- Либо machine API явно исключён из релизных обязательств.

## 5. Не блокеры деплоя, но важные проблемы

### NB1. Поведение `GET /documents` для non-global без `site_id` сейчас неверное по бизнес-смыслу

Картина по коду:
- После починки `500` роут всё равно для non-global без `site_id` возвращает пустой список.
- Это явно временная заглушка в `app/api/routes_documents.py`.

Задача:
- Либо вернуть документы по всем доступным площадкам пользователя.
- Либо жёстко требовать `site_id` и документировать это в контракте.

### NB2. Автогенерация документа на `RECEIVE` создаёт `acceptance_certificate`, а не `waybill`

Картина:
- В `app/services/operations_service.py` тип документа для `RECEIVE` жёстко маппится в `acceptance_certificate`.
- Ручная генерация `waybill` при этом работает.

Что решить:
- Это осознанное правило или расхождение с ожиданием “для начала накладных”.
- Нужен явный выбор продуктового правила.

### NB3. Нумерация документов не является сквозной последовательностью

Картина:
- `DocumentService._generate_document_number()` генерирует номер с random hex suffix.
- В комментарии при этом говорится про сквозную нумерацию.

Риск:
- Для преддеплоя это не обязательно блокер.
- Для документооборота это может стать конфликтом ожиданий.

Задача:
- Или переписать на реальную последовательность.
- Или убрать вводящий в заблуждение комментарий и зафиксировать текущий формат как временный.

### NB4. Soft delete item пока без проверки ненулевых остатков

Картина:
- В `app/repos/catalog_repo.py` у `soft_delete_item()` оставлен комментарий про упрощённую логику без интеграции с balance repo.

Риск:
- Можно архивировать номенклатуру, которая ещё участвует в остатках.

Задача:
- Добавить проверку ненулевых остатков до архивирования item.

## 6. Шумные проблемы тестового слоя, которые надо довести до рабочего состояния

### T1. `tests/test_document_service.py` не подключён к реальным фикстурам

Симптом:
- Ошибки `fixture 'test_site' not found`, `fixture 'test_user' not found`, `fixture 'test_operation_with_lines' not found`.

Вывод:
- Тесты написаны, но не wired в актуальный `tests/conftest.py`.

Задача:
- Добавить/вернуть missing fixtures.
- Или перевести тесты на уже существующие `site`, `user`, `session_factory`, `uow`.

### T2. `tests/test_documents_routes.py` не подключён к test client/fixture layer

Симптом:
- Ошибки `fixture 'client' not found`, `fixture 'auth_headers_user' not found`, `fixture 'test_document' not found`.

Вывод:
- API тесты документов пока не интегрированы в общий тестовый каркас.

Задача:
- Унифицировать фикстуры с остальными API-тестами.

### T3. `tests/test_catalog_admin_soft_delete.py` отстал от текущих правил удаления

Симптом:
- Тесты ожидают архивирование активных `unit/category/item`.
- Сервис теперь требует сначала `is_active=False`, затем archive/delete.

Вывод:
- Это, скорее всего, конфликт тестовых ожиданий с актуальной доменной политикой.

Задача:
- Подтвердить бизнес-правило.
- После подтверждения обновить тесты под текущий контракт.

### T4. `tests/test_reports_read_model.py` использует старую модель `Balance`

Симптом:
- В seed используются `Balance(site_id, item_id, qty)` без `inventory_subject_id`.
- Падает на insertmanyvalues/flush.

Вывод:
- Тесты застряли в допредметной модели остатков, до `inventory_subject_id`.

Задача:
- Переписать seed и assertions на актуальную модель.

### T5. `tests/test_http_sync.py::test_auth_fail_bad_token` падает из-за текста ошибки

Симптом:
- Ожидается `Invalid X-Device-Token`.
- Фактически приходит `invalid X-Device-Token`.

Вывод:
- Это не продуктовый блокер.
- Это несогласованность текста/теста.

Задача:
- Зафиксировать единый стиль текста ошибок и синхронизировать тест.

### T6. `tests/stand` сейчас фактически нерабочие

Поймано реальным запуском:
- `StandSettings` валится на extra env из `.env`.
- Даже после этого в коде использованы устаревшие `Authorization: Bearer ...`.
- Использованы устаревшие пути `/api/health` и `/api/health/ready`.
- Реальный сервер работает через `/api/v1/health` и `/api/v1/ready`.

Задача:
- Разрешить лишние env или изолировать `StandSettings` от общего `.env`.
- Перевести stand auth на `X-User-Token`.
- Обновить base paths до `/api/v1/...`.
- Синхронизировать smoke/auth сценарии со стендом.

Критерий готовности:
- `pytest tests/stand/smoke/test_stand_smoke.py -m stand` проходит на текущем стенде.

## 7. Пошаговый план работ

### Этап 0. Зафиксировать baseline

0.1 Снять и сохранить текущий `alembic current`, `alembic heads`, `openapi.json`.

0.2 Снять короткий инвентарь текущих runtime ошибок:
- `GET /documents`
- `POST /operations/{id}/accept-lines`
- replay `POST /operations` с same `client_request_id`

0.3 Не трогать большой функциональный рефакторинг до закрытия runtime-blockers.

Результат этапа:
- Есть baseline, от которого можно безопасно проверять regressions.

### Этап 1. Починить runtime-блокеры API

1.1 Исправить `GET /documents`.

1.2 Исправить `accept-lines` для inventory-subject сценариев.

1.3 Согласовать DDL `balances` с моделью и миграциями.

1.4 Исправить idempotent replay mixed RECEIVE.

1.5 Перепроверить live workflow:
- create RECEIVE with temporary + catalog
- replay same payload
- submit
- get generated docs
- accept-lines
- pending/lost registers

Результат этапа:
- Ключевой пользовательский сценарий не падает.

### Этап 2. Довести модуль документов

2.1 После фикса списка документов проверить:
- root list
- list by `site_id`
- filters by `document_type`
- filters by `status`
- pagination

2.2 Уточнить продуктовое правило для non-global без `site_id`.

2.3 Уточнить продуктовое правило для auto-generated document type на `RECEIVE`.

2.4 Проверить и зафиксировать политику numbering.

2.5 Проверить render:
- html
- pdf, если PDF считается обязательным перед релизом

Результат этапа:
- Документы работают не только точечно, но и как пользовательский модуль.

### Этап 3. Довести приёмку и asset registers

3.1 Закрыть runtime-ошибку при приёмке temporary item.

3.2 Прогнать сценарии:
- full accept
- partial accept + lost
- list pending after submit
- list lost after mark lost
- resolve lost asset
- повторная попытка approve/merge после очистки активных регистров

3.3 Проверить, где должен храниться legacy `item_id` для inventory-subject остатков и регистров.

Результат этапа:
- Механизм приёмки реально годен для эксплуатации.

### Этап 4. Довести каталог и archive/delete поведение

4.1 Зафиксировать бизнес-правило:
- сначала deactivate
- потом archive/delete

4.2 Обновить тесты и документацию под это правило.

4.3 Добавить проверку ненулевых остатков перед archive item.

4.4 Перепроверить `hashtags`, soft delete filters, `include_deleted`, `include_inactive`.

Результат этапа:
- Catalog admin поведение предсказуемо и не ломает остатки.

### Этап 5. Определиться с batch/spravochnik scope

5.1 Принять решение, должен ли machine API входить в преддеплойный scope.

5.2 Если да:
- зарегистрировать router
- выровнять OpenAPI
- добавить хотя бы smoke на batch preview/apply

5.3 Если нет:
- оставить как internal-only
- убрать из формулировок статуса реализации
- не обещать как готовый API

Результат этапа:
- Нет расхождения между обещанным функционалом и реальным API.

### Этап 6. Восстановить тестовую инфраструктуру

6.1 Починить `tests/test_document_service.py`.

6.2 Починить `tests/test_documents_routes.py`.

6.3 Переписать `tests/test_reports_read_model.py` под `inventory_subject_id`.

6.4 Актуализировать `tests/test_catalog_admin_soft_delete.py`.

6.5 Актуализировать `tests/stand/conftest.py`.

6.6 Актуализировать `tests/stand/smoke/test_stand_smoke.py`.

6.7 Выделить отдельный быстрый набор predeploy tests:
- documents
- temporary_items
- acceptance
- catalog_admin
- reports smoke
- stand smoke

Результат этапа:
- Перед деплоем можно нажать один набор команд и получить честную картину.

### Этап 7. Финальный преддеплойный прогон

7.1 Прогнать локально целевой pytest-набор.

7.2 Прогнать stand smoke.

7.3 Прогнать live сценарий:
- create site
- create users/scopes
- create catalog entities
- create mixed RECEIVE
- replay same `client_request_id`
- submit
- verify auto doc
- generate waybill manually
- accept lines
- verify pending/lost/issued endpoints
- verify temporary item approve/merge rules

7.4 Зафиксировать release note:
- что точно работает
- что временно out of scope

Результат этапа:
- Есть чёткий go/no-go сигнал перед деплоем.

## 8. Приоритеты

P0 до деплоя:
- B1 `GET /documents` 500
- B2 `accept-lines` 500
- B3 replay same `client_request_id` returns 409 on identical mixed payload
- T6 stand harness unusable

P1 в том же цикле до релиза, если успеваете:
- NB1 поведение documents list для non-global без `site_id`
- NB2 выбор auto document type на `RECEIVE`
- T1/T2 документы тесты без fixtures
- T4 reports tests на старой модели balances

P2 можно после первого деплоя, если времени не хватит:
- NB3 настоящая сквозная нумерация документов
- NB4 проверка ненулевых остатков перед archive item
- Machine API как внешний контракт, если это не релизный обязательный scope

## 9. Definition of Done для преддеплоя

Считать SyncServer готовым к преддеплою только если выполнено всё ниже:
- `GET /documents` больше не даёт `500`.
- `POST /operations/{id}/accept-lines` больше не даёт `500`.
- Mixed RECEIVE с temporary item корректно проходит replay по тому же `client_request_id`.
- Stand smoke запускается и проходит на актуальном стенде.
- Целевой predeploy pytest-набор зелёный.
- Есть короткий зафиксированный список того, что входит в релиз, и того, что явно остаётся вне релиза.

## 10. Короткий вывод для исполнителя

Система уже не “сырой черновик”. Большая часть версии склада 2.0 реально существует и работает. Перед деплоем надо не “дописывать всё заново”, а аккуратно закрыть несколько конкретных дыр:
- список документов
- приёмка temporary item
- идемпотентный replay mixed RECEIVE
- тестовая обвязка и stand smoke

Именно эти точки сейчас дают максимальную отдачу на единицу времени.
