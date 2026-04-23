# Реализованное состояние документации по Phase 2 read-path

## 1. Что зафиксировано в коде

### Subject-first проекция остатков и регистров

- [`InventorySubject`](../app/models/inventory_subject.py) стал общей ссылкой для строк операций, балансов и asset-регистров.
- [`Balance`](../app/models/balance.py), [`PendingAcceptanceBalance`](../app/models/asset_register.py), [`LostAssetBalance`](../app/models/asset_register.py) и [`IssuedAssetBalance`](../app/models/asset_register.py) хранят `inventory_subject_id`.
- `item_id` сохранён как nullable compatibility field, чтобы catalog-backed строки могли продолжать отдавать item-метаданные в read DTO.

### Исторический read DTO операций

- [`OperationLine`](../app/models/operation.py) хранит `inventory_subject_id` и исторические snapshots: `item_name_snapshot`, `item_sku_snapshot`, `unit_name_snapshot`, `unit_symbol_snapshot`, `category_name_snapshot`.
- Публичный read DTO строк операций также сохраняет compatibility-поля временных ТМЦ: `temporary_item_id`, `temporary_item_status`, `resolved_item_id`, `resolved_item_name`.
- Для acceptance-сценариев read DTO строк операций отдают `accepted_qty` и `lost_qty`.

### Read endpoints, которые уже реализованы

- Balances: `/balances`, `/balances/by-site`, `/balances/summary`.
- Asset registers: `/pending-acceptance`, `/lost-assets`, `/lost-assets/{operation_line_id}`, `/issued-assets`.
- Basic reporting: `/reports/item-movement`, `/reports/stock-summary`.

## 2. Фактический Phase 2 контракт read-path

### Balances

- Балансовые строки уже subject-aware: содержат `inventory_subject_id`, `subject_type`, `display_name` и optional catalog/temporary-item compatibility fields.
- Доступ ограничен видимыми сайтами пользователя через `UserAccessScope` либо global business access.

### Asset registers

- Pending, lost и issued read DTO также subject-aware и сохраняют site/recipient context.
- `/lost-assets` поддерживает фильтры `updated_after`, `updated_before`, `qty_from`, `qty_to`, а `/lost-assets/{operation_line_id}` отдаёт детальную строку в том же формате.
- `/lost-assets/{operation_line_id}/resolve` остаётся существующим write endpoint around read-model register workflow, но не рассматривается как новая Phase 2 API-добавка в рамках этой документации.

### Operations read DTO

- Read-path по операциям уже отражает subject-first состояние без изменения публичных endpoint paths.
- Исторические snapshot-поля читаются независимо от последующих изменений каталога.

### Basic reporting

- `/reports/item-movement` работает по submitted операциям, фильтруется по видимым сайтам и использует `effective_at`, если он задан, иначе `created_at`.
- Для acceptance-required incoming flows в item movement учитывается accepted quantity, а не исходный quantity строки.
- `/reports/stock-summary` возвращает текущие summary rows в subject-aware DTO-форме.

## 3. Подтверждённое тестовое состояние

- Bootstrap тестов был приведён в актуальное состояние в [`tests/conftest.py`](../tests/conftest.py): изоляция через отдельные schema-per-run и актуальные shared fixtures.
- Это внутреннее тестовое сопровождение, а не изменение публичного API.
- Подтверждённый набор:
  - [`tests/test_balances_endpoints.py`](../tests/test_balances_endpoints.py)
  - [`tests/test_balances_read_model.py`](../tests/test_balances_read_model.py)
  - [`tests/test_operation_snapshots.py`](../tests/test_operation_snapshots.py)
  - [`tests/test_operations_acceptance_and_issue_api.py`](../tests/test_operations_acceptance_and_issue_api.py)
  - [`tests/test_lost_assets_api.py`](../tests/test_lost_assets_api.py)
  - [`tests/test_inventory_read_consistency.py`](../tests/test_inventory_read_consistency.py)
- Итог подтверждения: `14 passed, 2 skipped`.

## 4. Что не менялось в рамках этого хвоста

- Дополнительные правки read-path кода приложения для закрытия документации не понадобились.
- Зафиксировано только фактически реализованное состояние и подтверждённый тестами контракт.
- Phase 3 и несвязанные темы в этот summary не включались.
