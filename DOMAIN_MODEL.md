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
