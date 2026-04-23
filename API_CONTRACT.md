# API_CONTRACT

Canonical client contract is maintained in:
- `docs/API_REFERENCE.md`
- `docs/ENDPOINT_INVENTORY.md`

## Current Contract Principles
- Primary auth is token-based:
  - `X-User-Token`
  - `X-Device-Token` (device/sync context)
- Access is evaluated server-side via `User.is_root` + `UserAccessScope`.
- Business logic remains server-side.
- Use the documented token-based API paths for all clients.
## Temporary items Phase 1

- [`POST /api/v1/operations`](app/api/routes_operations.py) принимает смешанные строки с legacy [`item_id`](app/schemas/operation.py:30) и inline [`temporary_item`](app/schemas/temporary_item.py:10).
- Ограничение Phase 1: inline temporary creation поддержан только для `RECEIVE` и требует [`client_request_id`](app/schemas/operation.py:72).
- Ограничение Phase 1: [`temporary_item.category_id`](app/schemas/temporary_item.py:13) фактически обязателен, потому что текущая модель всё ещё создаёт скрытый backing [`Item`](app/repos/catalog_repo.py:359).
- Добавлены moderation endpoints: [`GET /api/v1/temporary-items`](app/api/routes_temporary_items.py), [`GET /api/v1/temporary-items/{id}`](app/api/routes_temporary_items.py), [`POST /api/v1/temporary-items/{id}/approve-as-item`](app/api/routes_temporary_items.py), [`POST /api/v1/temporary-items/{id}/merge`](app/api/routes_temporary_items.py).
- Обратная совместимость сохранена: старые payload'ы, передающие только [`item_id`](app/schemas/operation.py:30), продолжают работать без изменений.
## Phase 2 (read-path) — subject-first (внедрено)

- Для read-моделей инвентаря и регистров источником идентичности строки является `inventory_subject_id`.
- В ответах `balances`, `operations.lines`, `pending-acceptance`, `lost-assets`, `issued-assets` возвращаются:
  - `inventory_subject_id`
  - `subject_type`
  - `item_id`
  - `temporary_item_id`
  - `resolved_item_id`
  - `display_name`
- Для строк операций дополнительно возвращаются snapshot-поля и `resolved_item_name`.
- Для `reports/item-movement` и `reports/stock-summary` внедрён минимально совместимый subject-first этап: добавлены subject-first поля, но агрегации пока остаются близкими к предыдущей модели и требуют отдельного полного этапа стабилизации.
