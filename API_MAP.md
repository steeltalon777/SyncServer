# API Map

Practical technical map of how to talk to SyncServer.

Use this file when you need:
- real endpoint paths
- real headers
- auth expectations
- request / response shape overview
- current verification status
- TODO areas

Full client-facing examples still live in `docs/API_REFERENCE.md`.
Flat inventory of all routes lives in `docs/ENDPOINT_INVENTORY.md`.

## Base
- Base prefix: `/api/v1`
- OpenAPI docs: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`

## Real Headers

### User auth
- `X-User-Token: <uuid>`

Used by:
- `/auth/*`
- `/admin/*`
- `/catalog/*` primary read API
- `/catalog/admin/*`
- `/operations/*`
- `/balances/*`

### Device auth
- `X-Device-Token: <uuid>`

Used by:
- `/ping`
- `/push`
- `/pull`

### Optional auth context headers
- `X-Device-Id: <device_id>`
  - optional on `/auth/me`, `/auth/context`, `/auth/sync-user`
- `X-Site-Id: <site_id>`
  - required for `chief_storekeeper` on `/catalog/admin/*` as action context

### Common request header
- `Content-Type: application/json`

## Auth Modes

| Mode | Real Header(s) | Where Used |
|---|---|---|
| User token | `X-User-Token` | primary app/admin/catalog/operations/balances |
| Device token | `X-Device-Token` | sync routes and optional auth context |

## Endpoint Groups

### Auth API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/auth/sync-user` | root `X-User-Token` | user payload: `id`, `username`, `email`, `full_name`, `is_active`, `is_root=false`, `role`, `default_site_id` | `{status, user, synced_by}` with `user.user_token` |
| `GET` | `/auth/me` | `X-User-Token` | no body | `{user, device}` |
| `GET` | `/auth/sites` | `X-User-Token` | no body | `{is_root, available_sites}` |
| `GET` | `/auth/context` | `X-User-Token` | no body | `{user, role, is_root, default_site, available_sites, permissions_summary, device}` |

Notes:
- `sync-user` is root-only.
- `sync-user` cannot create or update root users.
- `auth/me` does not return `user_token`.

### Admin API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/roles` | `X-User-Token` | no body | `list[str]` |
| `GET` | `/admin/sites` | `X-User-Token` | query: `is_active`, `search`, `page`, `page_size` | `{sites, total_count, page, page_size}` |
| `POST` | `/admin/sites` | `X-User-Token` | `{code, name, is_active, description}` | `SiteResponse` |
| `PATCH` | `/admin/sites/{site_id}` | `X-User-Token` | partial site payload | `SiteResponse` |
| `GET` | `/admin/users` | root `X-User-Token` | query: `is_active`, `is_root`, `role`, `search`, `page`, `page_size` | `{users, total_count, page, page_size}` |
| `GET` | `/admin/users/{user_id}` | root `X-User-Token` | no body | `UserResponse` |
| `POST` | `/admin/users` | root `X-User-Token` | `UserCreate` | `UserResponse` |
| `PATCH` | `/admin/users/{user_id}` | root `X-User-Token` | `UserUpdate` | `UserResponse` |
| `DELETE` | `/admin/users/{user_id}` | root `X-User-Token` | no body | `UserResponse` (soft-deactivated) |
| `GET` | `/admin/users/{user_id}/sync-state` | root `X-User-Token` | no body | `{user, scopes}` with `user.user_token` |
| `PUT` | `/admin/users/{user_id}/scopes` | root `X-User-Token` | `{scopes:[{site_id, can_view, can_operate, can_manage_catalog}]}` | `list[UserAccessScopeResponse]` |
| `POST` | `/admin/users/{user_id}/rotate-token` | root `X-User-Token` | no body | `{user_id, username, user_token, generated_at}` |
| `GET` | `/admin/access/scopes` | root `X-User-Token` | query: `user_id`, `site_id`, `is_active`, `limit`, `offset` | `list[UserAccessScopeResponse]` |
| `POST` | `/admin/access/scopes` | root `X-User-Token` | `UserAccessScopeCreate` | `UserAccessScopeResponse` |
| `PATCH` | `/admin/access/scopes/{scope_id}` | root `X-User-Token` | `UserAccessScopeUpdate` | `UserAccessScopeResponse` |
| `GET` | `/admin/devices` | `X-User-Token` | query: `site_id`, `is_active`, `search`, `page`, `page_size` | `{devices, total_count, page, page_size}` |
| `POST` | `/admin/devices` | `X-User-Token` | `DeviceCreate` | `DeviceResponse` |
| `PATCH` | `/admin/devices/{device_id}` | `X-User-Token` | `DeviceUpdate` | `DeviceResponse` |
| `POST` | `/admin/devices/{device_id}/rotate-token` | `X-User-Token` | no body | `{device_id, device_token, generated_at}` |

### Catalog Read API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/items` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{items, server_time, next_updated_after}` |
| `GET` | `/catalog/categories` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{categories, server_time, next_updated_after}` |
| `GET` | `/catalog/categories/tree` | `X-User-Token` | query: `site_id` | `list[CategoryTreeNode]` |
| `GET` | `/catalog/units` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{units, server_time, next_updated_after}` |
| `GET` | `/catalog/sites` | `X-User-Token` | query: `is_active` | `{sites, server_time}` |
| `GET` | `/catalog/read/items` | `X-User-Token` | query: `search`, `category_id`, `page`, `page_size`, `site_id` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories` | `X-User-Token` | query: `search`, `parent_id`, `page`, `page_size`, `include`, `items_preview_limit`, `site_id` | `{categories, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/items` | `X-User-Token` | query: `search`, `page`, `page_size`, `site_id` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/children` | `X-User-Token` | query: `page`, `page_size`, `include`, `items_preview_limit`, `site_id` | `{categories, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/parent-chain` | `X-User-Token` | query: `site_id` | `{category_id, parent_chain_summary}` |

Notes:
- `site_id` on catalog read is currently an access-context check, not a true data partition for items/categories/units.
- `root` and `chief_storekeeper` have global business read access across all sites.
- `storekeeper` and `observer` read only within assigned scopes.
- `/catalog/read/*` is the new browse/read-model layer for UI/Django usage.
- `/catalog/items|categories|units` remain the sync-style incremental feed and are not replaced by `/catalog/read/*`.
- `include` on `/catalog/read/categories` and `/catalog/read/categories/{category_id}/children` supports `parent`, `parent_chain_summary`, `items_preview`; default is all three.
- `items_preview_limit` defaults to `5` and is capped at `20`.
- Browse/read-model endpoints return only active categories/items/units.

### Catalog Admin API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/catalog/admin/units` | `X-User-Token` | `{name, symbol, sort_order, is_active}` | `UnitResponse` |
| `PATCH` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | partial unit payload | `UnitResponse` |
| `POST` | `/catalog/admin/categories` | `X-User-Token` | `{name, code, parent_id, sort_order, is_active}` | `CategoryResponse` |
| `PATCH` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | partial category payload | `CategoryResponse` |
| `POST` | `/catalog/admin/items` | `X-User-Token` | `{sku, name, category_id?, unit_id, description, is_active}` | `ItemResponse` |
| `PATCH` | `/catalog/admin/items/{item_id}` | `X-User-Token` | partial item payload; `category_id: null` -> `__UNCATEGORIZED__` | `ItemResponse` |

Notes:
- `root` may call these without `X-Site-Id`.
- `chief_storekeeper` must send `X-Site-Id` as action context and has global business catalog access.
- `storekeeper` and `observer` cannot mutate catalog.
- `POST /api/v1/catalog/admin/items`: missing or `null` `category_id` resolves to the system category `__UNCATEGORIZED__` (`"Без категории"`).
- `POST /api/v1/catalog/admin/items`: unknown or inactive `category_id` also resolves to `__UNCATEGORIZED__`.
- `PATCH /api/v1/catalog/admin/items/{item_id}`: omitted `category_id` keeps the current category; explicit `null` moves the item to `__UNCATEGORIZED__`.
- `__UNCATEGORIZED__` is a reserved read-only system category and cannot be created or edited through catalog admin.

### Operations API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/operations` | `X-User-Token` | query: `site_id`, `type`, `status`, `created_by_user_id`, `created_after`, `created_before`, `updated_after`, `updated_before`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/operations/{operation_id}` | `X-User-Token` | no body | `OperationResponse` |
| `POST` | `/operations` | `X-User-Token` | `OperationCreate` | `OperationResponse` |
| `PATCH` | `/operations/{operation_id}` | `X-User-Token` | `OperationUpdate` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/submit` | `X-User-Token` | `{submit: true}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/cancel` | `X-User-Token` | `{cancel: true, reason}` | `OperationResponse` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`
- Write roles: `root`, `chief_storekeeper`, `storekeeper`
- MOVE requires both `source_site_id` and `destination_site_id`
- Supported operation types: `RECEIVE`, `EXPENSE`, `WRITE_OFF`, `MOVE`, `ADJUSTMENT`, `ISSUE`, `ISSUE_RETURN`
- `ADJUSTMENT` accepts signed `qty`; other operation types require positive `qty`
- `ISSUE` and `ISSUE_RETURN` are accepted by the API, but submit/rollback currently returns `501 Not Implemented`
- `chief_storekeeper` is a global business supervisor across all sites
- `storekeeper` may create operations on sites where `can_operate=true`
- `storekeeper` may update only own draft operations
- only `chief_storekeeper` and `root` may submit operations
- `storekeeper` may cancel only own drafts; `chief_storekeeper` and `root` may cancel any draft or submitted operation
- rollback is blocked when reversing a submitted operation would make the affected balance invalid

### Balances API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/balances` | `X-User-Token` | query: `site_id`, `item_id`, `category_id`, `search`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/by-site` | `X-User-Token` | query: `site_id`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/summary` | `X-User-Token` | no body | `{accessible_sites_count, summary}` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`
- `chief_storekeeper` sees balances across all sites
- `storekeeper` and `observer` see balances only for accessible sites
- `/balances` returns UI-ready rows with site/item/category/unit labels, not only raw `(site_id, item_id, qty)`
- `category_id`, `search`, `only_positive`, pagination and total count are applied on the server side

### Device Sync API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/ping` | `X-Device-Token` | `{site_id, device_id, last_server_seq, outbox_count, client_time}` | `{server_seq_upto, backoff_seconds}` |
| `POST` | `/push` | `X-Device-Token` | `{site_id, device_id, batch_id, events:[...]}` | `{accepted, duplicates, rejected, server_seq_upto?}` |
| `POST` | `/pull` | `X-Device-Token` | `{site_id, device_id, since_seq, limit}` | `{events, next_since_seq, server_seq_upto}` |

### Health API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/health` | none | no body | health payload |
| `GET` | `/ready` | none | no body | readiness payload |

## Real Auth Rules
- `root` = global authority
- `chief_storekeeper` = global business supervisor across all sites
- `storekeeper` = operational user
- `observer` = read-only user
- device routes do not use user roles; they use registered device token

## Verified Endpoints

Verified in repository tests:
- `POST /api/v1/ping`
- `POST /api/v1/push`
- `POST /api/v1/pull`
- `GET /api/v1/catalog/read/items`
- `GET /api/v1/catalog/read/categories`
- `GET /api/v1/catalog/read/categories/{category_id}/items`
- `GET /api/v1/catalog/read/categories/{category_id}/children`
- `GET /api/v1/catalog/read/categories/{category_id}/parent-chain`
- `POST /api/v1/catalog/admin/units`
- `POST /api/v1/catalog/admin/categories`
- `POST /api/v1/catalog/admin/items`
- `PATCH /api/v1/catalog/admin/items/{item_id}`
- `PATCH /api/v1/catalog/admin/categories/{category_id}` including cycle validation
- `GET /api/v1/auth/me` (no token leak in normal response)
- `POST /api/v1/auth/sync-user`
- `PUT /api/v1/admin/users/{user_id}/scopes`
- `GET /api/v1/admin/users/{user_id}/sync-state`
- `POST /api/v1/admin/users/{user_id}/rotate-token`

Verification sources:
- `tests/test_http_sync.py`
- `tests/test_auth_routes.py`
- `tests/test_user_admin_flow.py`

## TODO

High-priority verification TODO:
- dedicated tests for `/admin/sites`
- dedicated tests for `/admin/users` CRUD
- dedicated tests for `/admin/access/scopes`
- dedicated tests for `/admin/devices` and device token rotation
- dedicated tests for primary `GET /catalog/items|categories|units|sites|categories/tree`
- dedicated tests for browse/read-model include validation edge cases
- dedicated tests for `/operations/*`
- dedicated tests for `/balances*`
- dedicated tests for `/health` and `/ready`

Documentation TODO:
- keep `docs/API_REFERENCE.md` and this file in sync when routes change
- keep `docs/ENDPOINT_INVENTORY.md` synchronized with actual router set

Environment TODO:
- stabilize test database setup so the endpoint verification suite can be run end-to-end without manual DB preparation
