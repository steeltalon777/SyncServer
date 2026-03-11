# AI_CONTEXT

## System architecture
- SyncServer является источником истины данных.
- Все клиенты работают через HTTP API.

## Backend rules
- Бизнес-логика находится в `app/services`.
- Доступ к данным выполняется через `app/repos`.
- Роуты в `app/api` должны быть тонкими.

## Database rules
- Не использовать сложные PostgreSQL триггеры.
- Не переносить бизнес-логику в БД.
- UUID используется как primary id.

## Catalog rules
- Категории реализованы через adjacency list (`parent_id -> categories.id`).
- Дерево категорий не должно содержать циклов.
- Для категорий действует уникальность `(parent_id, name)`.

## Client rules
- Django является клиентом, а не backend-частью системы.
- Django не должен писать напрямую в PostgreSQL.
- Все операции записи идут через SyncServer API.
