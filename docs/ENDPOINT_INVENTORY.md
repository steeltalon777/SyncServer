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
- `GET /admin/access/scopes` - list access scopes (root)
- `POST /admin/access/scopes` - create access scope (root)
- `PATCH /admin/access/scopes/{scope_id}` - update access scope (root)
- `GET /admin/devices` - list devices
- `POST /admin/devices` - create device
- `PATCH /admin/devices/{device_id}` - update device
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
- `POST /catalog/admin/units` - create unit
- `PATCH /catalog/admin/units/{unit_id}` - update unit
- `POST /catalog/admin/categories` - create category
- `PATCH /catalog/admin/categories/{category_id}` - update category
- `POST /catalog/admin/items` - create item
- `PATCH /catalog/admin/items/{item_id}` - update item
- `POST /catalog/admin/items` fallback: missing/null/unknown/inactive category resolves to `__UNCATEGORIZED__`
- `PATCH /catalog/admin/items/{item_id}` category semantics: omitted keeps current category, `null` moves to `__UNCATEGORIZED__`

## Operations
- `GET /operations` - list operations by visible scope
- `GET /operations/{operation_id}` - get operation
- `POST /operations` - create operation
- `PATCH /operations/{operation_id}` - update draft operation
- `POST /operations/{operation_id}/submit` - submit operation and apply deltas
- `POST /operations/{operation_id}/cancel` - cancel operation and rollback if submitted

## Balances
- `GET /balances` - list balances
- `GET /balances/by-site` - list balances for one site
- `GET /balances/summary` - aggregated balances summary

## Sync
- `POST /ping` - device heartbeat and seq status
- `POST /push` - upload events
- `POST /pull` - download events

## Health
- `GET /health` - liveness
- `GET /ready` - readiness + DB check
