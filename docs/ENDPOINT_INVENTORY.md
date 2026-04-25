# Endpoint Inventory

Base prefix: `/api/v1`

## Auth
- `POST /auth/sync-user` - create/update user in registry (root only)
- `GET /auth/me` - current user and optional current device
- `GET /auth/sites` - sites available to current user
- `GET /auth/context` - bootstrap payload (user, role, default_site, permissions)

## Admin
- `GET /admin/roles` - canonical role list
- `GET /admin/sites` - list sites
- `POST /admin/sites` - create site
- `PATCH /admin/sites/{site_id}` - update site
- `GET /admin/users` - list users (root)
- `GET /admin/users/{user_id}` - get user (root)
- `POST /admin/users` - create user (root)
- `PATCH /admin/users/{user_id}` - update user (root)
- `DELETE /admin/users/{user_id}` - deactivate user (root)
- `GET /admin/users/{user_id}/sync-state` - get user sync state (root)
- `PUT /admin/users/{user_id}/scopes` - replace user access scopes (root)
- `POST /admin/users/{user_id}/rotate-token` - rotate user token (root)
- `GET /admin/access/scopes` - list access scopes (root)
- `POST /admin/access/scopes` - create access scope (root)
- `PATCH /admin/access/scopes/{scope_id}` - update access scope (root)
- `GET /admin/devices` - list devices
- `GET /admin/devices/{device_id}` - get device by ID
- `POST /admin/devices` - create device and return token
- `PATCH /admin/devices/{device_id}` - update device
- `DELETE /admin/devices/{device_id}` - delete device
- `POST /admin/devices/{device_id}/rotate-token` - rotate device token

## Catalog
- `GET /catalog/items` - list items (primary)
- `GET /catalog/categories` - list categories (primary)
- `GET /catalog/categories/tree` - category tree (primary)
- `GET /catalog/units` - list units (primary)
- `GET /catalog/sites` - list available sites for catalog work (primary)
- `GET /catalog/read/items` - browse items for UI/Django read model
- `GET /catalog/read/categories` - browse categories with parent chain and preview data
- `GET /catalog/read/categories/{category_id}/items` - browse items scoped to one category
- `GET /catalog/read/categories/{category_id}/children` - browse direct child categories
- `GET /catalog/read/categories/{category_id}/parent-chain` - get parent chain summary for one category

## Catalog Admin
- `GET /catalog/admin/units` - list units
- `GET /catalog/admin/units/{unit_id}` - get unit by ID
- `POST /catalog/admin/units` - create unit
- `POST /catalog/admin/units/bulk` - create units in one atomic request
- `PATCH /catalog/admin/units/{unit_id}` - update unit
- `DELETE /catalog/admin/units/{unit_id}` - delete unit
- `GET /catalog/admin/categories` - list categories
- `GET /catalog/admin/categories/{category_id}` - get category by ID
- `POST /catalog/admin/categories` - create category
- `POST /catalog/admin/categories/bulk` - create categories in one atomic request
- `PATCH /catalog/admin/categories/{category_id}` - update category
- `DELETE /catalog/admin/categories/{category_id}` - delete category
- `GET /catalog/admin/items` - list items
- `GET /catalog/admin/items/{item_id}` - get item by ID
- `POST /catalog/admin/items` - create item
- `PATCH /catalog/admin/items/{item_id}` - update item
- `DELETE /catalog/admin/items/{item_id}` - delete item
- `POST /catalog/admin/items` fallback: missing/null/unknown/inactive category resolves to `__UNCATEGORIZED__`
- `PATCH /catalog/admin/items/{item_id}` category semantics: omitted keeps current category, `null` moves to `__UNCATEGORIZED__`

## Operations
- `GET /operations` - list operations by visible scope
- `GET /operations/{operation_id}` - get operation
- `POST /operations` - create operation
- `PATCH /operations/{operation_id}` - update draft operation
- `PATCH /operations/{operation_id}/effective-at` - change operation effective date (`chief_storekeeper` and `root` only)
- `POST /operations/{operation_id}/submit` - submit operation and apply deltas
- `POST /operations/{operation_id}/cancel` - cancel operation and rollback if submitted
- `POST /operations/{operation_id}/accept-lines` - accept operation lines (destination site access)

## Balances
- `GET /balances` - list balances
- `GET /balances/by-site` - list balances for one site
- `GET /balances/summary` - aggregated balances summary

## Asset Register
- `GET /pending-acceptance` - список ожидающих приёмки активов (фильтры: site_id, operation_id, item_id, search, пагинация)
- `GET /lost-assets` - список непринятых активов (lost assets) с фильтрацией по дате, количеству, source_site_id, operation_id, item_id, search, пагинация
- `GET /lost-assets/{operation_line_id}` - детали одного непринятого актива
- `POST /lost-assets/{operation_line_id}/resolve` - разрешение непринятого актива (возврат, списание, перемещение) с полями action, qty, note, responsible_recipient_id
- `GET /issued-assets` - список выданных активов (фильтры: recipient_id, item_id, search, пагинация)

## Documents
- `POST /documents/generate` - generate document from operation
- `GET /documents/{document_id}` - get document metadata
- `GET /documents/{document_id}/render?format=html` - render document as HTML
- `GET /documents/{document_id}/render?format=pdf` - render document as PDF
- `GET /documents` - list documents with filtering
- `PATCH /documents/{document_id}/status` - update document status
- `GET /documents/operations/{operation_id}/documents` - list documents for an operation
- `POST /documents/operations/{operation_id}/documents` - generate document for operation (shortcut)

## Reports
- `GET /reports/item-movement` - aggregated item movement by site and item for a period
- `GET /reports/stock-summary` - aggregated current balance summary by site

## Recipients
- `POST /recipients` - create recipient
- `POST /recipients/merge` - merge recipients (chief_storekeeper or root only)
- `GET /recipients/{recipient_id}` - get recipient
- `PATCH /recipients/{recipient_id}` - update recipient
- `DELETE /recipients/{recipient_id}` - delete recipient
- `GET /recipients` - list recipients with filtering (search, recipient_type, include_inactive, include_deleted, pagination)

## Sync
- `POST /ping` - device heartbeat and seq status
- `POST /push` - upload events
- `POST /pull` - download events
- `POST /bootstrap/sync` - initial bootstrap for Django client (root only)

## Health
- `GET /health` - liveness
- `GET /ready` - readiness + DB check
- `GET /health/detailed` - detailed health with all dependencies
- `GET /health/readiness` - readiness check for critical dependencies
- `GET /health/liveness` - liveness check for basic application health
