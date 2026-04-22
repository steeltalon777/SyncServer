# DOMAIN_MODEL

## Entity: Site
**Description:** Warehouse/site boundary for data partitioning.

**Fields:**
- `id`
- `code`
- `name`
- `is_active`
- `created_at`

**Relations:**
- one-to-many with `Device`
- one-to-many with `Event`

## Entity: Device
**Description:** Registered client device authorized to sync for a site.

**Fields:**
- `id`
- `site_id`
- `name`
- `registration_token`
- `last_ip`
- `last_seen_at`
- `client_version`
- `is_active`
- `created_at`

**Relations:**
- belongs to `Site`
- optional link from `Event`

## Entity: Event
**Description:** Immutable sync event stored in ordered server log.

**Fields:**
- `event_uuid`
- `site_id`
- `device_id`
- `user_id`
- `event_type`
- `event_datetime`
- `received_at`
- `schema_version`
- `payload`
- `server_seq`
- `payload_hash`

**Relations:**
- belongs to `Site`
- optional belongs to `Device`

## Entity: Category
**Description:** Catalog category node in hierarchy.

**Fields:**
- `id`
- `name`
- `code`
- `parent_id`
- `is_active`
- `sort_order`
- `created_at`
- `updated_at`

**Relations:**
- self-reference `parent` / `children`
- one-to-many with `Item`

## Entity: Unit
**Description:** Measurement unit for catalog items.

**Fields:**
- `id`
- `name`
- `symbol`
- `is_active`
- `sort_order`
- `created_at`
- `updated_at`

**Relations:**
- one-to-many with `Item`

## Entity: Item
**Description:** Catalog item/product.

**Fields:**
- `id`
- `sku`
- `name`
- `category_id`
- `unit_id`
- `description`
- `is_active`
- `created_at`
- `updated_at`

**Relations:**
- belongs to `Category`
- belongs to `Unit`
- used by `Balance`

## Entity: Balance
**Description:** Aggregated quantity of an item on a site.

**Fields:**
- `site_id`
- `item_id`
- `qty`
- `updated_at`

**Relations:**
- references `Site`
- references `Item`

## Entity: PendingAcceptanceBalance
**Description:** Items awaiting acceptance after operation submission (for RECEIVE and MOVE operations).

**Fields:**
- `operation_line_id` (primary key)
- `operation_id`
- `destination_site_id` – warehouse where items are expected
- `source_site_id` – source warehouse (only for MOVE)
- `item_id`
- `qty` – quantity awaiting acceptance
- `updated_at`

**Relations:**
- references `OperationLine` via `operation_line_id`
- references `Site` as destination site
- references `Site` as source site (optional)
- references `Item`

**Lifecycle:**
- Created when a RECEIVE or MOVE operation is submitted
- Removed when the operation line is accepted (or cancelled)

## Entity: LostAssetBalance
**Description:** Unaccepted items that were not received during acceptance (lost assets).

**Fields:**
- `operation_line_id` (primary key)
- `operation_id`
- `site_id` – warehouse where the lost items are physically located
- `source_site_id` – source warehouse (only for MOVE)
- `item_id`
- `qty` – lost quantity
- `updated_at`

**Relations:**
- references `OperationLine` via `operation_line_id`
- references `Site` as current site
- references `Site` as source site (optional)
- references `Item`

**Lifecycle:**
- Created when an operation line is accepted with `lost_qty > 0`
- Removed when the lost asset is resolved (returned, written off, or moved)

## Entity: IssuedAssetBalance
**Description:** Items issued to a recipient (for ISSUE and ISSUE_RETURN operations).

**Fields:**
- `recipient_id` (primary key)
- `item_id` (primary key)
- `qty` – issued quantity
- `updated_at`

**Relations:**
- references `Recipient`
- references `Item`

## Entity: OperationAcceptanceAction
**Description:** Audit log of acceptance and lost asset resolution actions.

**Fields:**
- `id`
- `operation_id`
- `operation_line_id`
- `action_type` – "accept", "return_to_source", "write_off", "found_to_destination"
- `performed_by_user_id`
- `recipient_id` (for ISSUE operations)
- `performed_at`

**Relations:**
- references `Operation`
- references `OperationLine`
- references `User`
- references `Recipient` (optional)

## Entity: UserAccessScope
**Description:** Per-site permissions for a user.

**Fields:**
- `id`
- `user_id`
- `site_id`
- `can_view`
- `can_operate`
- `can_manage_catalog`
- `is_active`

**Relations:**
- references `User`
- references `Site`
## Temporary items Phase 1

- Добавлена сущность [`TemporaryItem`](app/models/temporary_item.py:14) со статусом, автором создания, ссылкой на backing [`Item`](app/models/temporary_item.py:18) и опциональной резолюцией в постоянную ТМЦ.
- Phase 1 не вводит `inventory_subjects`: текущие связи остаются item-centric в [`OperationLine`](app/models/operation.py:197), [`Balance`](app/models/balance.py:12) и asset-регистрах.
- Для исторического API строк операций добавлены вычисляемые поля [`OperationLine.temporary_item_id`](app/models/operation.py:247), [`OperationLine.temporary_item_status`](app/models/operation.py:252) и [`OperationLine.resolved_item_id`](app/models/operation.py:257).
