# MEMORY

## System architecture
- SyncServer — централизованный backend для sync и каталога.
- Архитектура: FastAPI routers → services → repositories → PostgreSQL.
- Транзакционная модель основана на `UnitOfWork`.

## Core entities
- `Site`, `Device` — идентификация площадки и клиента.
- `Event` — immutable log событий для репликации между клиентами.
- `Category`, `Unit`, `Item` — каталог номенклатуры.
- `Balance` — агрегированное состояние остатков по `(site_id, item_id)`.

## Data model decisions
- UUID ключи для доменных таблиц.
- `events.server_seq` — серверный упорядоченный курсор sync pull.
- `categories.parent_id` реализует дерево (adjacency list).
- `is_active` применяется для деактивации записей без физического удаления.

## API design
- Отдельные API группы: sync, catalog read, catalog admin.
- Device token auth проверяется в dependency/route flow.
- Pull/push API используют batch и cursor-подход.

## Business rules
- `event_uuid` уникален; одинаковый payload = duplicate, другой payload = uuid collision.
- Для категорий запрещены циклы и дублирующиеся имена в рамках одного родителя.
- Для unit/item соблюдаются уникальные поля (`name`, `symbol`, `sku`).

## Known pitfalls
- In-memory rate limiter в одном процессе не подходит для multi-instance deployment.
- SQL bootstrap schema и ORM `UserSiteRole` расходятся по полям (`role` vs `role_code`) — зона для выравнивания миграциями.
- Отсутствует встроенный migration toolchain (только init SQL).

## Future architecture
- Вынести rate limit/auth metadata в shared infra.
- Добавить управляемые миграции схемы (Alembic).
- Развить conflict-resolution и reconciliation сценарии для offline клиентов.
