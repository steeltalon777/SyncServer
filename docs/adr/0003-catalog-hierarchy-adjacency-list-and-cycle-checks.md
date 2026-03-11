# ADR-0003: Catalog hierarchy via adjacency list and application-level cycle checks

## Status
Accepted

## Context
Категории каталога требуют иерархию и поддержку CRUD/update операций. Нужна простая и понятная модель в PostgreSQL/ORM без сложных БД-структур.

## Decision
- Использовать adjacency list: `categories.parent_id -> categories.id`.
- Проверять циклы и корректность parent в сервисном слое (`CatalogAdminService`).
- Гарантировать уникальность имени в пределах одного parent через constraint `(parent_id, name)`.

## Consequences
Плюсы:
- Простая SQL/ORM модель.
- Гибкие update операции.
- Проверки циклов контролируются бизнес-логикой.

Минусы:
- Для глубоких деревьев путь/ancestor вычисляется в приложении.
- Нет встроенного materialized path для мгновенных subtree выборок.

## Alternatives Considered
### Option 1: Materialized path
Удобнее для чтения дерева, но усложняет обновления и перемещения узлов.

### Option 2: Closure table
Быстрые ancestor/descendant запросы, но существенно сложнее схема и поддержка.
