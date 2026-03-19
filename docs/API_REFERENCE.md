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

Legacy compatibility headers (not primary):
- `Authorization: Bearer <service_token>`
- `X-Acting-User-Id`
- `X-Acting-Site-Id`

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
- chief_storekeeper: sites/devices/roles list (no users/access scopes)

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
- `POST /admin/devices`
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

Read (legacy compatibility):
- `POST /catalog/items`
- `POST /catalog/categories`
- `POST /catalog/units`

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
- `WRITE_OFF`
- `MOVE`

Endpoints:
- `GET /operations`
- `GET /operations/{operation_id}`
- `POST /operations`
- `PATCH /operations/{operation_id}`
- `POST /operations/{operation_id}/submit`
- `POST /operations/{operation_id}/cancel`

Rules:
- submit updates balances
- cancel rolls back submitted deltas
- server validates site access and MOVE source/destination

## Balances API (read-only)
- `GET /balances`
- `GET /balances/by-site`
- `GET /balances/summary`

Access:
- root: all sites
- non-root: only active `UserAccessScope` with `can_view=true`

## Sync API (device)
- `POST /ping`
- `POST /push`
- `POST /pull`

## Health
- `GET /health`
- `GET /ready`

## Legacy Compatibility API
- `POST /business/catalog/items`
- `POST /business/catalog/categories`
- `POST /business/catalog/units`
- `GET /business/catalog/categories/tree`

These are compatibility endpoints and should not be used for new clients.

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

### 3) Balances summary
`GET /api/v1/balances/summary`
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
