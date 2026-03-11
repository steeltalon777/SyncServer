# MEMORY

## System architecture
- SyncServer является главным источником истины.
- Все клиенты работают через HTTP API.

## Catalog model
- Сущности: `Category`, `Unit`, `Item`.
- `Category` реализует дерево через `parent_id`.

## Write API
- Write API используется для создания, обновления и деактивации (`is_active=false`).
- Физическое удаление данных не используется.

## Client architecture
- Django web client
- WPF client
- mobile clients
- offline warehouse clients

Все клиенты взаимодействуют с системой через HTTP API.

## Known pitfalls
Нельзя:
- писать в БД напрямую из клиентов;
- переносить бизнес-логику в PostgreSQL;
- смешивать sync API и admin API в одном неразделённом слое.
