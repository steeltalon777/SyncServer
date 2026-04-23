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

## Entity: InventorySubject
**Description:** Canonical inventory subject key used by operation lines and read projections. A subject points either to a catalog item or to a temporary item.

**Fields:**
- `id`
- `subject_type` – `catalog_item` or `temporary_item`
- `item_id` – optional backing catalog item
- `temporary_item_id` – optional temporary item reference
- `created_at`
- `archived_at`

**Relations:**
- optional one-to-one with `Item`
- optional one-to-one with `TemporaryItem`
- referenced by `OperationLine`
- referenced by `Balance`
- referenced by `PendingAcceptanceBalance`
- referenced by `LostAssetBalance`
- referenced by `IssuedAssetBalance`

## Entity: Balance
**Description:** Subject-based stock balance projection for a site.

**Fields:**
- `site_id`
- `inventory_subject_id`
- `item_id` – optional compatibility/back-reference to catalog item
- `qty`
- `updated_at`

**Relations:**
- references `Site`
- references `InventorySubject`
- optionally references `Item`

## Entity: PendingAcceptanceBalance
**Description:** Items awaiting acceptance after operation submission (for RECEIVE and MOVE operations).

**Fields:**
- `operation_line_id` (primary key)
- `operation_id`
- `destination_site_id` – warehouse where items are expected
- `source_site_id` – source warehouse (only for MOVE)
- `inventory_subject_id`
- `item_id` – optional compatibility/back-reference to catalog item
- `qty` – quantity awaiting acceptance
- `updated_at`

**Relations:**
- references `OperationLine` via `operation_line_id`
- references `Site` as destination site
- references `Site` as source site (optional)
- references `InventorySubject`
- optionally references `Item`

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
- `inventory_subject_id`
- `item_id` – optional compatibility/back-reference to catalog item
- `qty` – lost quantity
- `updated_at`

**Relations:**
- references `OperationLine` via `operation_line_id`
- references `Site` as current site
- references `Site` as source site (optional)
- references `InventorySubject`
- optionally references `Item`

**Lifecycle:**
- Created when an operation line is accepted with `lost_qty > 0`
- Removed when the lost asset is resolved (returned, written off, or moved)

## Entity: IssuedAssetBalance
**Description:** Inventory subjects issued to a recipient (for ISSUE and ISSUE_RETURN operations).

**Fields:**
- `recipient_id` (primary key)
- `inventory_subject_id` (primary key)
- `item_id` – optional compatibility/back-reference to catalog item
- `qty` – issued quantity
- `updated_at`

**Relations:**
- references `Recipient`
- references `InventorySubject`
- optionally references `Item`

## Entity: OperationAcceptanceAction
**Description:** Audit log of acceptance, mark-lost, and lost asset resolution actions.

**Fields:**
- `id`
- `operation_id`
- `operation_line_id`
- `action_type` – `accept`, `mark_lost`, `return_to_source`, `write_off`, `found_to_destination`
- `qty`
- `performed_by_user_id`
- `recipient_id` (for ISSUE operations)
- `notes`
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

## Inventory subjects and historical operation read-model

- Phase 2 uses `inventory_subjects` as the shared link for `OperationLine`, `Balance`, and asset registers.
- `item_id` remains a nullable compatibility field in balances and asset registers so catalog-backed rows can still expose item metadata.
- `OperationLine` stores historical snapshots: `item_name_snapshot`, `item_sku_snapshot`, `unit_name_snapshot`, `unit_symbol_snapshot`, `category_name_snapshot`.
- Public read DTOs keep temporary-item compatibility fields: `temporary_item_id`, `temporary_item_status`, `resolved_item_id`, `resolved_item_name`.
