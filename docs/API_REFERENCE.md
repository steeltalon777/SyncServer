# API Reference

Base URL prefix: `/api/v1`

## Auth Headers

Primary user auth:
- `X-User-Token: <uuid>`

Optional device context (auth endpoints):
- `X-Device-Token: <uuid>`
- `X-Device-Id: <int>`

Device sync auth:
- `X-Device-Token: <uuid>`

Authorization model:
- there is no separate service or AI contour
- all clients use the same token headers and role/scope checks
- access is determined by user role plus `UserAccessScope`

## Error Model
Most errors return FastAPI default:
```json
{ "detail": "message" }
```
Application-specific handlers may return:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "message",
    "details": {}
  }
}
```

## Auth API
- `POST /auth/sync-user` (root)
- `GET /auth/me`
- `GET /auth/sites`
- `GET /auth/context`

## Admin API
Roles:
- root: full admin
- chief_storekeeper: global business supervisor across all sites (no users/access scopes CRUD)

Users (root only):
- `GET /admin/users`
- `GET /admin/users/{user_id}`
- `GET /admin/users/{user_id}/sync-state`
- `POST /admin/users`
- `PATCH /admin/users/{user_id}`
- `DELETE /admin/users/{user_id}`
- `PUT /admin/users/{user_id}/scopes`
- `POST /admin/users/{user_id}/rotate-token`

Sites:
- `GET /admin/sites`
- `POST /admin/sites`
- `PATCH /admin/sites/{site_id}`

Access scopes (root only):
- `GET /admin/access/scopes`
- `POST /admin/access/scopes`
- `PATCH /admin/access/scopes/{scope_id}`

Devices:
- `GET /admin/devices`
- `POST /admin/devices` - creates device and returns its token
- `PATCH /admin/devices/{device_id}`
- `POST /admin/devices/{device_id}/rotate-token`

Roles list:
- `GET /admin/roles`

## Catalog API
Read (primary, user token):
- `GET /catalog/items`
- `GET /catalog/categories`
- `GET /catalog/categories/tree`
- `GET /catalog/units`
- `GET /catalog/sites`

Read model (browse/UI, user token):
- `GET /catalog/read/items`
- `GET /catalog/read/categories`
- `GET /catalog/read/categories/{category_id}/items`
- `GET /catalog/read/categories/{category_id}/children`
- `GET /catalog/read/categories/{category_id}/parent-chain`

Admin:
- `POST /catalog/admin/units`
- `PATCH /catalog/admin/units/{unit_id}`
- `POST /catalog/admin/categories`
- `PATCH /catalog/admin/categories/{category_id}`
- `POST /catalog/admin/items`
- `PATCH /catalog/admin/items/{item_id}`

## Operations API
Supported operation types:
- `RECEIVE`
- `EXPENSE`
- `WRITE_OFF`
- `MOVE`
- `ADJUSTMENT`
- `ISSUE`
- `ISSUE_RETURN`

Endpoints:
- `GET /operations`
- `GET /operations/{operation_id}`
- `POST /operations`
- `PATCH /operations/{operation_id}`
- `PATCH /operations/{operation_id}/effective-at`
- `POST /operations/{operation_id}/submit`
- `POST /operations/{operation_id}/cancel`

Rules:
- submit updates balances
- cancel rolls back submitted deltas
- if `effective_at` is omitted on create, the server sets it to the current timestamp
- `effective_at` cannot be changed through the general `PATCH /operations/{operation_id}` endpoint
- `PATCH /operations/{operation_id}/effective-at` is reserved for `chief_storekeeper` and `root`
- `PATCH /operations/{operation_id}/effective-at` is allowed for `draft` and `submitted` operations and blocked for `cancelled`
- rollback is blocked if reversing a submitted operation would make a balance invalid (for example, negative stock on the affected site)
- server validates site access and MOVE source/destination
- `ADJUSTMENT` uses signed `qty`: positive adds stock, negative subtracts stock
- `ISSUE` and `ISSUE_RETURN` are accepted by the API, but submit/rollback is currently a placeholder and returns `501`
- `storekeeper` may create operations on allowed sites, but submit is reserved for `chief_storekeeper` and `root`
- `storekeeper` may update only own draft operations
- `storekeeper` may cancel only own draft operations
- `storekeeper` may not change `effective_at`
- `chief_storekeeper` is a global business supervisor and may work with operations across all sites

## Balances API (read-only)
- `GET /balances`
- `GET /balances/by-site`
- `GET /balances/summary`

Access:
- root: all sites
- chief_storekeeper: all sites as global business supervisor
- storekeeper/observer: only active `UserAccessScope` with `can_view=true`

`GET /balances` list rows are UI-ready and include:
- `site_id`, `site_name`
- `item_id`, `item_name`, `sku`
- `unit_id`, `unit_symbol`
- `category_id`, `category_name`
- `qty`, `updated_at`

## Reports API (read-only)
- `GET /reports/item-movement`
- `GET /reports/stock-summary`

Access:
- root: all sites
- chief_storekeeper: all sites as global business supervisor
- storekeeper/observer: only active `UserAccessScope` with `can_view=true`

`GET /reports/item-movement` returns aggregated rows with:
- `site_id`, `site_name`
- `item_id`, `item_name`, `sku`
- `unit_id`, `unit_symbol`
- `category_id`, `category_name`
- `incoming_qty`, `outgoing_qty`, `net_qty`
- `last_operation_at`

Rules:
- only `submitted` operations participate in movement reports
- report period uses `effective_at` when present, otherwise falls back to `created_at`
- movement is grouped by `(site_id, item_id)` so internal `MOVE` operations appear as outgoing on source and incoming on destination

`GET /reports/stock-summary` returns grouped current-balance aggregates per site:
- `site_id`, `site_name`
- `items_count`
- `positive_items_count`
- `total_quantity`
- `last_balance_at`

## Sync API (device)
- `POST /ping`
- `POST /push`
- `POST /pull`

## Health
- `GET /health`
- `GET /ready`

## Postman Examples

### 1) Current user
`GET /api/v1/auth/me`
Headers:
- `X-User-Token: {{user_token}}`
- `X-Device-Token: {{device_token}}` (optional)

### 1.1) Sync user from Django admin
`POST /api/v1/auth/sync-user`
Headers:
- `X-User-Token: {{root_user_token}}`
- `Content-Type: application/json`
Body:
```json
{
  "id": "6b8d9d4d-8b74-4c77-9f0a-5d6b6d3f2b11",
  "username": "ivanov",
  "email": "ivanov@example.com",
  "full_name": "Иван Иванов",
  "is_active": true,
  "is_root": false,
  "role": "storekeeper",
  "default_site_id": 1
}
```
Notes:
- root-only
- root users cannot be created or updated through this endpoint
- existing non-root users keep their current `user_token`

### 1.2) Replace user scopes
`PUT /api/v1/admin/users/{user_id}/scopes`
Headers:
- `X-User-Token: {{root_user_token}}`
- `Content-Type: application/json`
Body:
```json
{
  "scopes": [
    {
      "site_id": 1,
      "can_view": true,
      "can_operate": true,
      "can_manage_catalog": false
    }
  ]
}
```

### 1.3) Read sync state
`GET /api/v1/admin/users/{user_id}/sync-state`
Headers:
- `X-User-Token: {{root_user_token}}`

### 1.4) Rotate non-root user token
`POST /api/v1/admin/users/{user_id}/rotate-token`
Headers:
- `X-User-Token: {{root_user_token}}`
Notes:
- root-only
- root token rotation is not allowed via API

### 1.5) Create device and receive token
`POST /api/v1/admin/devices`
Headers:
- `X-User-Token: {{admin_user_token}}`
- `Content-Type: application/json`
Body:
```json
{
  "device_code": "django-web",
  "device_name": "Django Web Client",
  "site_id": null,
  "is_active": true
}
```
Notes:
- allowed for `root` and `chief_storekeeper`
- response includes `device_id` and `device_token`

### 2) Create operation
`POST /api/v1/operations`
Headers:
- `X-User-Token: {{user_token}}`
- `Content-Type: application/json`
Body:
```json
{
  "operation_type": "RECEIVE",
  "site_id": 1,
  "lines": [
    { "line_number": 1, "item_id": 10, "qty": 5 }
  ],
  "notes": "incoming"
}
```

### 2.1) Change operation effective date
`PATCH /api/v1/operations/{operation_id}/effective-at`
Headers:
- `X-User-Token: {{chief_or_root_user_token}}`
- `Content-Type: application/json`
Body:
```json
{
  "effective_at": "2026-04-08T12:30:00Z"
}
```
Notes:
- allowed only for `root` and `chief_storekeeper`
- use this endpoint instead of the general operation patch endpoint when changing posting date

### 3) Balances summary
`GET /api/v1/balances/summary`
Headers:
- `X-User-Token: {{user_token}}`

### 3.1) Item movement report for dashboard/documents
`GET /api/v1/reports/item-movement?site_id=1&date_from=2026-01-01T00:00:00Z&date_to=2026-01-31T23:59:59Z&page=1&page_size=50`
Headers:
- `X-User-Token: {{user_token}}`

### 3.2) Stock summary report
`GET /api/v1/reports/stock-summary?page=1&page_size=50`
Headers:
- `X-User-Token: {{user_token}}`

### 4) Create catalog item
`POST /api/v1/catalog/admin/items`
Headers:
- `X-User-Token: {{root_user_token}}`
- `Content-Type: application/json`
Body:
```json
{
  "sku": "ITEM-001",
  "name": "Example",
  "category_id": 1,
  "unit_id": 1,
  "description": "demo",
  "is_active": true
}
```

Notes:
- `category_id` may be omitted or sent as `null`; the server assigns the system category `__UNCATEGORIZED__` (`"Без категории"`).
- If `category_id` points to a missing or inactive category, the server also assigns `__UNCATEGORIZED__`.
- On `PATCH /api/v1/catalog/admin/items/{item_id}`, omitted `category_id` keeps the current category, while explicit `null` moves the item to `__UNCATEGORIZED__`.
- `__UNCATEGORIZED__` is seeded during bootstrap and treated as a reserved read-only category in catalog admin.

### 5) Browse catalog categories for Django/UI
`GET /api/v1/catalog/read/categories?search=Milk&page=1&page_size=20&include=parent,parent_chain_summary,items_preview&items_preview_limit=5`
Headers:
- `X-User-Token: {{user_token}}`

Response:
```json
{
  "categories": [
    {
      "id": 12,
      "name": "Whole Milk",
      "code": "MILK-WHOLE",
      "parent_id": 4,
      "parent": { "id": 4, "name": "Milk" },
      "parent_chain_summary": [
        { "id": 1, "name": "Food" },
        { "id": 4, "name": "Milk" }
      ],
      "children_count": 0,
      "items_count": 1,
      "items_preview": [
        { "id": 55, "name": "Whole Milk 1L" }
      ],
      "is_active": true,
      "updated_at": "2026-03-20T10:00:00+00:00",
      "sort_order": 1
    }
  ],
  "total_count": 1,
  "page": 1,
  "page_size": 20
}
```

Notes:
- `include` supports `parent`, `parent_chain_summary`, `items_preview`
- when `include` is omitted, the endpoint returns all three by default
- browse/read-model endpoints return only active categories/items/units

### 6) Browse catalog items for Django/UI
`GET /api/v1/catalog/read/items?search=milk&category_id=12&page=1&page_size=20`
Headers:
- `X-User-Token: {{user_token}}`

Response:
```json
{
  "items": [
    {
      "id": 55,
      "sku": "MILK-001",
      "name": "Whole Milk 1L",
      "category_id": 12,
      "category_name": "Whole Milk",
      "unit_id": 2,
      "unit_symbol": "l",
      "description": "Shelf item",
      "is_active": true,
      "updated_at": "2026-03-20T10:00:00+00:00"
    }
  ],
  "total_count": 1,
  "page": 1,
  "page_size": 20
}
```

### 7) Category-scoped helpers for Django/UI
- `GET /api/v1/catalog/read/categories/{category_id}/items?search=&page=&page_size=&site_id=`
- `GET /api/v1/catalog/read/categories/{category_id}/children?page=&page_size=&include=&items_preview_limit=&site_id=`
- `GET /api/v1/catalog/read/categories/{category_id}/parent-chain?site_id=`
