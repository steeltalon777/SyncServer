# API MAP

Generated from FastAPI OpenAPI schema on 2026-04-20 05:03:20Z.

Source of truth: mounted routers in `main.py` and schemas registered in FastAPI OpenAPI.

## Global notes

- Primary API prefix: `/api/v1`
- This file includes all OpenAPI-exposed HTTP endpoints, including service-level routes like `/` and `/db_check`.
- Request and response examples below are schema-shaped examples generated from the OpenAPI contract.
- Total paths: `69`
- Total operations: `92`

## System

### GET /

- Summary: Root
- Operation ID: `root__get`

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Root  Get`

```json
{
  "key": "string"
}
```

---

### GET /db_check

- Summary: Db Check
- Operation ID: `db_check_db_check_get`

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Db Check Db Check Get`

```json
{
  "key": "string"
}
```

---

## Auth

### GET /api/v1/auth/context

- Summary: Get Auth Context
- Operation ID: `get_auth_context_api_v1_auth_context_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `inline`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/auth/me

- Summary: Get Me
- Operation ID: `get_me_api_v1_auth_me_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `inline`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/auth/sites

- Summary: Get User Sites
- Operation ID: `get_user_sites_api_v1_auth_sites_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `inline`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/auth/sync-user

- Summary: Sync User
- Operation ID: `sync_user_api_v1_auth_sync_user_post`
- Description: Sync user registry record (Django-compatible), authenticated by user token.
Root-only operation.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UserCreate`
- Required top-level fields: `username`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `inline`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

## Admin

### GET /api/v1/admin/access/scopes

- Summary: List Access Scopes
- Operation ID: `list_access_scopes_api_v1_admin_access_scopes_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `query` | no | `anyOf` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `is_active` | `query` | no | `anyOf` |  |
| `limit` | `query` | no | `integer` |  |
| `offset` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response List Access Scopes Api V1 Admin Access Scopes Get`

```json
[
  {
    "id": 0,
    "user_id": "00000000-0000-0000-0000-000000000000",
    "site_id": 0,
    "can_view": true,
    "can_operate": true,
    "can_manage_catalog": true,
    "is_active": true,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/admin/access/scopes

- Summary: Create Access Scope
- Operation ID: `create_access_scope_api_v1_admin_access_scopes_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UserAccessScopeCreate`
- Required top-level fields: `site_id, user_id`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "can_view": true,
  "can_operate": true,
  "can_manage_catalog": true,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserAccessScopeResponse`
- Required top-level fields: `can_manage_catalog, can_operate, can_view, created_at, id, is_active, site_id, updated_at, user_id`

```json
{
  "id": 0,
  "user_id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "can_view": true,
  "can_operate": true,
  "can_manage_catalog": true,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/admin/access/scopes/{scope_id}

- Summary: Update Access Scope
- Operation ID: `update_access_scope_api_v1_admin_access_scopes__scope_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `scope_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UserAccessScopeUpdate`

```json
{
  "can_view": true,
  "can_operate": true,
  "can_manage_catalog": true,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserAccessScopeResponse`
- Required top-level fields: `can_manage_catalog, can_operate, can_view, created_at, id, is_active, site_id, updated_at, user_id`

```json
{
  "id": 0,
  "user_id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "can_view": true,
  "can_operate": true,
  "can_manage_catalog": true,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/devices

- Summary: List Devices
- Operation ID: `list_devices_api_v1_admin_devices_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` |  |
| `is_active` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DeviceListResponse`
- Required top-level fields: `devices, page, page_size, total_count`

```json
{
  "devices": [
    {
      "device_id": 0,
      "device_code": "device code",
      "device_name": "device name",
      "site_id": "...",
      "is_active": true,
      "last_seen_at": "...",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/admin/devices

- Summary: Create Device
- Operation ID: `create_device_api_v1_admin_devices_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `DeviceCreate`
- Required top-level fields: `device_name`

```json
{
  "device_code": "string",
  "device_name": "device name",
  "site_id": 0,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DeviceWithTokenResponse`
- Required top-level fields: `created_at, device_code, device_id, device_name, device_token, is_active, updated_at`

```json
{
  "device_id": 0,
  "device_code": "device code",
  "device_name": "device name",
  "site_id": 0,
  "is_active": true,
  "last_seen_at": "2026-01-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "device_token": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/devices/{device_id}

- Summary: Get Device
- Operation ID: `get_device_api_v1_admin_devices__device_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `device_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DeviceResponse`
- Required top-level fields: `created_at, device_code, device_id, device_name, is_active, updated_at`

```json
{
  "device_id": 0,
  "device_code": "device code",
  "device_name": "device name",
  "site_id": 0,
  "is_active": true,
  "last_seen_at": "2026-01-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/admin/devices/{device_id}

- Summary: Update Device
- Operation ID: `update_device_api_v1_admin_devices__device_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `device_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `DeviceUpdate`

```json
{
  "device_code": "string",
  "device_name": "string",
  "site_id": 0,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DeviceResponse`
- Required top-level fields: `created_at, device_code, device_id, device_name, is_active, updated_at`

```json
{
  "device_id": 0,
  "device_code": "device code",
  "device_name": "device name",
  "site_id": 0,
  "is_active": true,
  "last_seen_at": "2026-01-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### DELETE /api/v1/admin/devices/{device_id}

- Summary: Delete Device
- Operation ID: `delete_device_api_v1_admin_devices__device_id__delete`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `device_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DeviceResponse`
- Required top-level fields: `created_at, device_code, device_id, device_name, is_active, updated_at`

```json
{
  "device_id": 0,
  "device_code": "device code",
  "device_name": "device name",
  "site_id": 0,
  "is_active": true,
  "last_seen_at": "2026-01-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/admin/devices/{device_id}/rotate-token

- Summary: Rotate Device Token
- Operation ID: `rotate_device_token_api_v1_admin_devices__device_id__rotate_token_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `device_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DeviceTokenResponse`
- Required top-level fields: `device_id, device_token, generated_at`

```json
{
  "device_id": 0,
  "device_token": "00000000-0000-0000-0000-000000000000",
  "generated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/roles

- Summary: List Roles
- Operation ID: `list_roles_api_v1_admin_roles_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response List Roles Api V1 Admin Roles Get`

```json
[
  "string"
]
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/sites

- Summary: List Sites Admin
- Operation ID: `list_sites_admin_api_v1_admin_sites_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `is_active` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `SiteListResponse`
- Required top-level fields: `page, page_size, sites, total_count`

```json
{
  "sites": [
    {
      "site_id": 0,
      "code": "code",
      "name": "name",
      "is_active": true,
      "description": "...",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/admin/sites

- Summary: Create Site
- Operation ID: `create_site_api_v1_admin_sites_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `SiteCreate`
- Required top-level fields: `code, name`

```json
{
  "code": "code",
  "name": "name",
  "is_active": true,
  "description": "string"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `SiteResponse`
- Required top-level fields: `code, created_at, is_active, name, site_id, updated_at`

```json
{
  "site_id": 0,
  "code": "code",
  "name": "name",
  "is_active": true,
  "description": "string",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/admin/sites/{site_id}

- Summary: Update Site
- Operation ID: `update_site_api_v1_admin_sites__site_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `SiteUpdate`

```json
{
  "code": "string",
  "name": "string",
  "is_active": true,
  "description": "string"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `SiteResponse`
- Required top-level fields: `code, created_at, is_active, name, site_id, updated_at`

```json
{
  "site_id": 0,
  "code": "code",
  "name": "name",
  "is_active": true,
  "description": "string",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/users

- Summary: List Users
- Operation ID: `list_users_api_v1_admin_users_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `is_active` | `query` | no | `anyOf` |  |
| `is_root` | `query` | no | `anyOf` |  |
| `role` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserListResponse`
- Required top-level fields: `page, page_size, total_count, users`

```json
{
  "users": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "username": "username",
      "email": "...",
      "full_name": "...",
      "is_active": true,
      "is_root": true,
      "role": "root",
      "default_site_id": "...",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/admin/users

- Summary: Create User
- Operation ID: `create_user_api_v1_admin_users_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UserCreate`
- Required top-level fields: `username`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserResponse`
- Required top-level fields: `created_at, email, full_name, id, is_active, updated_at, username`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/users/{user_id}

- Summary: Get User
- Operation ID: `get_user_api_v1_admin_users__user_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserResponse`
- Required top-level fields: `created_at, email, full_name, id, is_active, updated_at, username`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/admin/users/{user_id}

- Summary: Update User
- Operation ID: `update_user_api_v1_admin_users__user_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UserUpdate`

```json
{
  "username": "string",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserResponse`
- Required top-level fields: `created_at, email, full_name, id, is_active, updated_at, username`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### DELETE /api/v1/admin/users/{user_id}

- Summary: Delete User
- Operation ID: `delete_user_api_v1_admin_users__user_id__delete`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserResponse`
- Required top-level fields: `created_at, email, full_name, id, is_active, updated_at, username`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "email": "string",
  "full_name": "string",
  "is_active": true,
  "is_root": true,
  "role": "root",
  "default_site_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/admin/users/{user_id}/rotate-token

- Summary: Rotate User Token
- Operation ID: `rotate_user_token_api_v1_admin_users__user_id__rotate_token_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserTokenResponse`
- Required top-level fields: `generated_at, user_id, user_token, username`

```json
{
  "user_id": "00000000-0000-0000-0000-000000000000",
  "username": "username",
  "user_token": "00000000-0000-0000-0000-000000000000",
  "generated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PUT /api/v1/admin/users/{user_id}/scopes

- Summary: Replace User Scopes
- Operation ID: `replace_user_scopes_api_v1_admin_users__user_id__scopes_put`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UserAccessScopeReplaceRequest`
- Required top-level fields: `scopes`

```json
{
  "scopes": [
    {
      "site_id": 0,
      "can_view": true,
      "can_operate": true,
      "can_manage_catalog": true
    }
  ]
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Replace User Scopes Api V1 Admin Users  User Id  Scopes Put`

```json
[
  {
    "id": 0,
    "user_id": "00000000-0000-0000-0000-000000000000",
    "site_id": 0,
    "can_view": true,
    "can_operate": true,
    "can_manage_catalog": true,
    "is_active": true,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/admin/users/{user_id}/sync-state

- Summary: Get User Sync State
- Operation ID: `get_user_sync_state_api_v1_admin_users__user_id__sync_state_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `user_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UserSyncStateResponse`
- Required top-level fields: `scopes, user`

```json
{
  "user": {
    "id": "00000000-0000-0000-0000-000000000000",
    "username": "username",
    "email": "string",
    "full_name": "string",
    "is_active": true,
    "is_root": true,
    "role": "root",
    "default_site_id": 0,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "user_token": "00000000-0000-0000-0000-000000000000"
  },
  "scopes": [
    {
      "id": 0,
      "user_id": "00000000-0000-0000-0000-000000000000",
      "site_id": 0,
      "can_view": true,
      "can_operate": true,
      "can_manage_catalog": true,
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

## Misc

### GET /api/v1/balances

- Summary: List Balances
- Operation ID: `list_balances_api_v1_balances_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` | Filter by site ID |
| `item_id` | `query` | no | `anyOf` | Filter by item ID |
| `category_id` | `query` | no | `anyOf` | Filter by category ID |
| `search` | `query` | no | `anyOf` | Search in item fields |
| `only_positive` | `query` | no | `boolean` | Show only positive balances |
| `page` | `query` | no | `integer` | Page number |
| `page_size` | `query` | no | `integer` | Page size |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `BalanceListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "site_id": 0,
      "site_name": "site name",
      "item_id": 0,
      "item_name": "item name",
      "sku": "...",
      "unit_id": 0,
      "unit_symbol": "unit symbol",
      "category_id": 0,
      "category_name": "category name",
      "qty": "qty",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/balances/by-site

- Summary: List Balances By Site
- Operation ID: `list_balances_by_site_api_v1_balances_by_site_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | yes | `integer` | Site ID |
| `only_positive` | `query` | no | `boolean` | Show only positive balances |
| `page` | `query` | no | `integer` | Page number |
| `page_size` | `query` | no | `integer` | Page size |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `BalanceListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "site_id": 0,
      "site_name": "site name",
      "item_id": 0,
      "item_name": "item name",
      "sku": "...",
      "unit_id": 0,
      "unit_symbol": "unit symbol",
      "category_id": 0,
      "category_name": "category name",
      "qty": "qty",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/balances/summary

- Summary: Get Balances Summary
- Operation ID: `get_balances_summary_api_v1_balances_summary_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `BalanceSummaryResponse`
- Required top-level fields: `accessible_sites_count, summary`

```json
{
  "accessible_sites_count": 0,
  "summary": {
    "rows_count": 0,
    "sites_count": 0,
    "total_quantity": 0
  }
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/bootstrap/sync

- Summary: Bootstrap Sync
- Operation ID: `bootstrap_sync_api_v1_bootstrap_sync_post`
- Description: Endpoint начальной загрузки для Django-клиента.

Primary auth: X-User-Token (root). Device token — опционален для логов/привязки.
site_id и device_id из body могут быть 0 — сервер определит устройство
по токену и вернёт реальные координаты клиенту.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Client-Version` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `BootstrapSyncRequest`

```json
{
  "site_id": 0,
  "device_id": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `BootstrapSyncResponse`

```json
{
  "server_time": "2026-01-01T00:00:00Z",
  "protocol_version": "protocol version",
  "is_root": true,
  "root_user": {},
  "root_role": "string",
  "device_id": 0,
  "device_registered": true,
  "message": "message",
  "bootstrap_data": {
    "available_sites": [
      "..."
    ],
    "protocol_version": "protocol version",
    "settings": {}
  }
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/admin/categories

- Summary: List Categories
- Operation ID: `list_categories_api_v1_catalog_admin_categories_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `include_inactive` | `query` | no | `boolean` |  |
| `include_deleted` | `query` | no | `boolean` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CategoryListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": 0,
      "name": "name",
      "code": "...",
      "parent_id": "...",
      "sort_order": "...",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "deleted_at": "...",
      "deleted_by_user_id": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/catalog/admin/categories

- Summary: Create Category
- Operation ID: `create_category_api_v1_catalog_admin_categories_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `CategoryCreateRequest`
- Required top-level fields: `name`

```json
{
  "name": "name",
  "code": "string",
  "parent_id": 0,
  "sort_order": 0,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CategoryResponse`
- Required top-level fields: `created_at, id, is_active, name, updated_at`

```json
{
  "id": 0,
  "name": "name",
  "code": "string",
  "parent_id": 0,
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/admin/categories/{category_id}

- Summary: Get Category
- Operation ID: `get_category_api_v1_catalog_admin_categories__category_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `category_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CategoryResponse`
- Required top-level fields: `created_at, id, is_active, name, updated_at`

```json
{
  "id": 0,
  "name": "name",
  "code": "string",
  "parent_id": 0,
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/catalog/admin/categories/{category_id}

- Summary: Update Category
- Operation ID: `update_category_api_v1_catalog_admin_categories__category_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `category_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `CategoryUpdateRequest`

```json
{
  "name": "string",
  "code": "string",
  "parent_id": 0,
  "sort_order": 0,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CategoryResponse`
- Required top-level fields: `created_at, id, is_active, name, updated_at`

```json
{
  "id": 0,
  "name": "name",
  "code": "string",
  "parent_id": 0,
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### DELETE /api/v1/catalog/admin/categories/{category_id}

- Summary: Delete Category
- Operation ID: `delete_category_api_v1_catalog_admin_categories__category_id__delete`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `category_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 204

- Description: Successful Response
_No response body_

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/admin/items

- Summary: List Items
- Operation ID: `list_items_api_v1_catalog_admin_items_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `include_inactive` | `query` | no | `boolean` |  |
| `include_deleted` | `query` | no | `boolean` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `ItemListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": 0,
      "sku": "...",
      "name": "name",
      "category_id": 0,
      "unit_id": 0,
      "description": "...",
      "is_active": true,
      "hashtags": "...",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "deleted_at": "...",
      "deleted_by_user_id": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/catalog/admin/items

- Summary: Create Item
- Operation ID: `create_item_api_v1_catalog_admin_items_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `ItemCreateRequest`
- Required top-level fields: `name, unit_id`

```json
{
  "sku": "string",
  "name": "name",
  "category_id": 0,
  "unit_id": 0,
  "description": "string",
  "hashtags": [
    "string"
  ],
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `ItemResponse`
- Required top-level fields: `category_id, created_at, id, is_active, name, unit_id, updated_at`

```json
{
  "id": 0,
  "sku": "string",
  "name": "name",
  "category_id": 0,
  "unit_id": 0,
  "description": "string",
  "is_active": true,
  "hashtags": [
    "string"
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/admin/items/{item_id}

- Summary: Get Item
- Operation ID: `get_item_api_v1_catalog_admin_items__item_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `item_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `ItemResponse`
- Required top-level fields: `category_id, created_at, id, is_active, name, unit_id, updated_at`

```json
{
  "id": 0,
  "sku": "string",
  "name": "name",
  "category_id": 0,
  "unit_id": 0,
  "description": "string",
  "is_active": true,
  "hashtags": [
    "string"
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/catalog/admin/items/{item_id}

- Summary: Update Item
- Operation ID: `update_item_api_v1_catalog_admin_items__item_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `item_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `ItemUpdateRequest`

```json
{
  "sku": "string",
  "name": "string",
  "category_id": 0,
  "unit_id": 0,
  "description": "string",
  "hashtags": [
    "string"
  ],
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `ItemResponse`
- Required top-level fields: `category_id, created_at, id, is_active, name, unit_id, updated_at`

```json
{
  "id": 0,
  "sku": "string",
  "name": "name",
  "category_id": 0,
  "unit_id": 0,
  "description": "string",
  "is_active": true,
  "hashtags": [
    "string"
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### DELETE /api/v1/catalog/admin/items/{item_id}

- Summary: Delete Item
- Operation ID: `delete_item_api_v1_catalog_admin_items__item_id__delete`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `item_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 204

- Description: Successful Response
_No response body_

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/admin/units

- Summary: List Units
- Operation ID: `list_units_api_v1_catalog_admin_units_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `include_inactive` | `query` | no | `boolean` |  |
| `include_deleted` | `query` | no | `boolean` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UnitListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": 0,
      "name": "name",
      "symbol": "symbol",
      "sort_order": "...",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "deleted_at": "...",
      "deleted_by_user_id": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/catalog/admin/units

- Summary: Create Unit
- Operation ID: `create_unit_api_v1_catalog_admin_units_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UnitCreateRequest`
- Required top-level fields: `name, symbol`

```json
{
  "name": "name",
  "symbol": "symbol",
  "sort_order": 0,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UnitResponse`
- Required top-level fields: `created_at, id, is_active, name, symbol, updated_at`

```json
{
  "id": 0,
  "name": "name",
  "symbol": "symbol",
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/admin/units/{unit_id}

- Summary: Get Unit
- Operation ID: `get_unit_api_v1_catalog_admin_units__unit_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `unit_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UnitResponse`
- Required top-level fields: `created_at, id, is_active, name, symbol, updated_at`

```json
{
  "id": 0,
  "name": "name",
  "symbol": "symbol",
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/catalog/admin/units/{unit_id}

- Summary: Update Unit
- Operation ID: `update_unit_api_v1_catalog_admin_units__unit_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `unit_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `UnitUpdateRequest`

```json
{
  "name": "string",
  "symbol": "string",
  "sort_order": 0,
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `UnitResponse`
- Required top-level fields: `created_at, id, is_active, name, symbol, updated_at`

```json
{
  "id": 0,
  "name": "name",
  "symbol": "symbol",
  "sort_order": 0,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### DELETE /api/v1/catalog/admin/units/{unit_id}

- Summary: Delete Unit
- Operation ID: `delete_unit_api_v1_catalog_admin_units__unit_id__delete`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `unit_id` | `path` | yes | `integer` |  |
| `X-Site-Id` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 204

- Description: Successful Response
_No response body_

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/categories

- Summary: List Categories
- Operation ID: `list_categories_api_v1_catalog_categories_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `updated_after` | `query` | no | `anyOf` |  |
| `limit` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogCategoriesResponse`
- Required top-level fields: `categories`

```json
{
  "categories": [
    {
      "id": 0,
      "name": "name",
      "parent_id": "...",
      "is_active": true,
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "server_time": "2026-01-01T00:00:00Z",
  "next_updated_after": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/categories/tree

- Summary: Get Categories Tree
- Operation ID: `get_categories_tree_api_v1_catalog_categories_tree_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Get Categories Tree Api V1 Catalog Categories Tree Get`

```json
[
  {
    "id": 0,
    "name": "name",
    "code": "string",
    "parent_id": 0,
    "is_active": true,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "sort_order": 0,
    "path": [
      "string"
    ],
    "children": [
      {
        "$ref": "CategoryTreeNode"
      }
    ]
  }
]
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/items

- Summary: List Items
- Operation ID: `list_items_api_v1_catalog_items_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `updated_after` | `query` | no | `anyOf` |  |
| `limit` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogItemsResponse`
- Required top-level fields: `items`

```json
{
  "items": [
    {
      "id": 0,
      "sku": "...",
      "name": "name",
      "category_id": 0,
      "unit_id": 0,
      "description": "...",
      "is_active": true,
      "hashtags": "...",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "server_time": "2026-01-01T00:00:00Z",
  "next_updated_after": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/read/categories

- Summary: Browse Categories
- Operation ID: `browse_categories_api_v1_catalog_read_categories_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `search` | `query` | no | `anyOf` |  |
| `parent_id` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `include` | `query` | no | `anyOf` |  |
| `items_preview_limit` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogBrowseCategoriesResponse`
- Required top-level fields: `categories, page, page_size, total_count`

```json
{
  "categories": [
    {
      "id": 0,
      "name": "name",
      "code": "...",
      "parent_id": "...",
      "parent": "...",
      "parent_chain_summary": [
        "..."
      ],
      "children_count": 0,
      "items_count": 0,
      "items_preview": [
        "..."
      ],
      "is_active": true,
      "updated_at": "2026-01-01T00:00:00Z",
      "sort_order": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/read/categories/{category_id}/children

- Summary: Browse Category Children
- Operation ID: `browse_category_children_api_v1_catalog_read_categories__category_id__children_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `category_id` | `path` | yes | `integer` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `include` | `query` | no | `anyOf` |  |
| `items_preview_limit` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogBrowseCategoriesResponse`
- Required top-level fields: `categories, page, page_size, total_count`

```json
{
  "categories": [
    {
      "id": 0,
      "name": "name",
      "code": "...",
      "parent_id": "...",
      "parent": "...",
      "parent_chain_summary": [
        "..."
      ],
      "children_count": 0,
      "items_count": 0,
      "items_preview": [
        "..."
      ],
      "is_active": true,
      "updated_at": "2026-01-01T00:00:00Z",
      "sort_order": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/read/categories/{category_id}/items

- Summary: Browse Category Items
- Operation ID: `browse_category_items_api_v1_catalog_read_categories__category_id__items_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `category_id` | `path` | yes | `integer` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogBrowseItemsResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": 0,
      "sku": "...",
      "name": "name",
      "category_id": 0,
      "category_name": "category name",
      "unit_id": 0,
      "unit_symbol": "unit symbol",
      "description": "...",
      "is_active": true,
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/read/categories/{category_id}/parent-chain

- Summary: Browse Category Parent Chain
- Operation ID: `browse_category_parent_chain_api_v1_catalog_read_categories__category_id__parent_chain_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `category_id` | `path` | yes | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CategoryParentChainResponse`
- Required top-level fields: `category_id`

```json
{
  "category_id": 0,
  "parent_chain_summary": [
    {
      "id": 0,
      "name": "name"
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/read/items

- Summary: Browse Items
- Operation ID: `browse_items_api_v1_catalog_read_items_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `search` | `query` | no | `anyOf` |  |
| `category_id` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogBrowseItemsResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": 0,
      "sku": "...",
      "name": "name",
      "category_id": 0,
      "category_name": "category name",
      "unit_id": 0,
      "unit_symbol": "unit symbol",
      "description": "...",
      "is_active": true,
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/sites

- Summary: List Sites
- Operation ID: `list_sites_api_v1_catalog_sites_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `is_active` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogSitesResponse`
- Required top-level fields: `sites`

```json
{
  "sites": [
    {
      "site_id": 0,
      "code": "code",
      "name": "name",
      "is_active": true,
      "permissions": {
        "key": "..."
      }
    }
  ],
  "server_time": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/catalog/units

- Summary: List Units
- Operation ID: `list_units_api_v1_catalog_units_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `updated_after` | `query` | no | `anyOf` |  |
| `limit` | `query` | no | `integer` |  |
| `site_id` | `query` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `CatalogUnitsResponse`
- Required top-level fields: `units`

```json
{
  "units": [
    {
      "id": 0,
      "name": "name",
      "symbol": "symbol",
      "is_active": true,
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "server_time": "2026-01-01T00:00:00Z",
  "next_updated_after": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/documents

- Summary: List Documents
- Operation ID: `list_documents_api_v1_documents_get`
- Description: Получить список документов с фильтрацией.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` | Фильтр по площадке |
| `document_type` | `query` | no | `anyOf` | Тип документа |
| `status` | `query` | no | `anyOf` | Статус документа |
| `created_by_user_id` | `query` | no | `anyOf` | ID создателя |
| `date_from` | `query` | no | `anyOf` | Дата создания от |
| `date_to` | `query` | no | `anyOf` | Дата создания до |
| `offset` | `query` | no | `integer` | Смещение для пагинации |
| `limit` | `query` | no | `integer` | Лимит для пагинации |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DocumentListResponse`
- Required top-level fields: `items, limit, offset, total`

```json
{
  "items": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "document_type": "waybill",
      "document_number": "...",
      "revision": 0,
      "status": "draft",
      "site_id": 0,
      "template_name": "...",
      "template_version": "...",
      "payload_schema_version": "...",
      "payload": {},
      "payload_hash": "...",
      "created_by_user_id": "...",
      "created_at": "2026-01-01T00:00:00Z",
      "finalized_at": "...",
      "supersedes_document_id": "..."
    }
  ],
  "total": 0,
  "offset": 0,
  "limit": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/documents/generate

- Summary: Generate Document
- Operation ID: `generate_document_api_v1_documents_generate_post`
- Description: Сгенерировать документ на основе операции.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `DocumentGenerateRequest`
- Required top-level fields: `operation_id`

```json
{
  "operation_id": "00000000-0000-0000-0000-000000000000",
  "document_type": "waybill",
  "template_name": "string",
  "auto_finalize": true,
  "language": "language",
  "basis_type": "string",
  "basis_number": "string",
  "basis_date": "2026-01-01T00:00:00Z"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Generate Document Api V1 Documents Generate Post`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/documents/operations/{operation_id}/documents

- Summary: Get Documents By Operation
- Operation ID: `get_documents_by_operation_api_v1_documents_operations__operation_id__documents_get`
- Description: Получить список документов по операции.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `document_type` | `query` | no | `anyOf` | Фильтр по типу документа |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Get Documents By Operation Api V1 Documents Operations  Operation Id  Documents Get`

```json
[
  {
    "id": "00000000-0000-0000-0000-000000000000",
    "document_type": "waybill",
    "document_number": "string",
    "revision": 0,
    "status": "draft",
    "site_id": 0,
    "template_name": "string",
    "template_version": "string",
    "payload_schema_version": "string",
    "payload": {},
    "payload_hash": "string",
    "created_by_user_id": "00000000-0000-0000-0000-000000000000",
    "created_at": "2026-01-01T00:00:00Z",
    "finalized_at": "2026-01-01T00:00:00Z",
    "supersedes_document_id": "00000000-0000-0000-0000-000000000000"
  }
]
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/documents/operations/{operation_id}/documents

- Summary: Generate Document For Operation
- Operation ID: `generate_document_for_operation_api_v1_documents_operations__operation_id__documents_post`
- Description: Удобный shortcut для генерации документа определённого типа по операции.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `document_type` | `query` | no | `enum` | Тип документа |
| `template_name` | `query` | no | `anyOf` | Имя шаблона |
| `auto_finalize` | `query` | no | `boolean` | Автоматически финализировать |
| `language` | `query` | no | `string` | Язык документа (ru/en) |
| `basis_type` | `query` | no | `anyOf` | Тип основания документа |
| `basis_number` | `query` | no | `anyOf` | Номер основания документа |
| `basis_date` | `query` | no | `anyOf` | Дата основания документа |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Generate Document For Operation Api V1 Documents Operations  Operation Id  Documents Post`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/documents/{document_id}

- Summary: Get Document
- Operation ID: `get_document_api_v1_documents__document_id__get`
- Description: Получить документ по ID.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `document_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DocumentResponse`
- Required top-level fields: `created_at, created_by_user_id, document_number, document_type, finalized_at, id, payload, payload_hash, payload_schema_version, revision, site_id, status, supersedes_document_id, template_name, template_version`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "document_type": "waybill",
  "document_number": "string",
  "revision": 0,
  "status": "draft",
  "site_id": 0,
  "template_name": "string",
  "template_version": "string",
  "payload_schema_version": "string",
  "payload": {},
  "payload_hash": "string",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "finalized_at": "2026-01-01T00:00:00Z",
  "supersedes_document_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/documents/{document_id}/render

- Summary: Render Document
- Operation ID: `render_document_api_v1_documents__document_id__render_get`
- Description: Рендеринг документа в HTML или PDF.

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `document_id` | `path` | yes | `string` |  |
| `format` | `query` | no | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `inline`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/documents/{document_id}/status

- Summary: Update Document Status
- Operation ID: `update_document_status_api_v1_documents__document_id__status_patch`
- Description: Обновить статус документа (финализация, аннулирование и т.д.).

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `document_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `DocumentUpdate`

```json
{
  "status": "draft",
  "finalized_at": "2026-01-01T00:00:00Z",
  "payload": {},
  "payload_hash": "string"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `DocumentResponse`
- Required top-level fields: `created_at, created_by_user_id, document_number, document_type, finalized_at, id, payload, payload_hash, payload_schema_version, revision, site_id, status, supersedes_document_id, template_name, template_version`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "document_type": "waybill",
  "document_number": "string",
  "revision": 0,
  "status": "draft",
  "site_id": 0,
  "template_name": "string",
  "template_version": "string",
  "payload_schema_version": "string",
  "payload": {},
  "payload_hash": "string",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "finalized_at": "2026-01-01T00:00:00Z",
  "supersedes_document_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/health

- Summary: Health
- Operation ID: `health_api_v1_health_get`
- Description: Basic health check endpoint.

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Health Api V1 Health Get`

```json
{
  "key": "string"
}
```

---

### GET /api/v1/health/detailed

- Summary: Detailed Health
- Operation ID: `detailed_health_api_v1_health_detailed_get`
- Description: Detailed health check with all dependencies.

Returns comprehensive status of all system components including:
- Database connection
- Configuration validation
- Cache (if configured)
- External services (if configured)

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `HealthCheckResponse`
- Required top-level fields: `checks, status`

```json
{
  "checks": {
    "cache": {
      "details": "Connection timeout",
      "error": "Redis connection failed",
      "status": "unhealthy"
    },
    "config": {
      "details": "All required configs present",
      "status": "healthy"
    },
    "database": {
      "details": "Connection successful",
      "latency_ms": 8.2,
      "status": "healthy"
    }
  },
  "status": "degraded",
  "timestamp": "2026-04-06T06:42:52Z",
  "version": "1.0.0"
}
```

---

### GET /api/v1/health/liveness

- Summary: Liveness Check
- Operation ID: `liveness_check_api_v1_health_liveness_get`
- Description: Liveness check for basic application health.

Used by Kubernetes and container orchestration to determine
if the container should be restarted.

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `LivenessResponse`
- Required top-level fields: `alive`

```json
{
  "alive": true,
  "timestamp": "2026-04-06T06:42:52Z"
}
```

---

### GET /api/v1/health/readiness

- Summary: Readiness Check
- Operation ID: `readiness_check_api_v1_health_readiness_get`
- Description: Readiness check for critical dependencies.

Used by load balancers and orchestration systems to determine
if the service is ready to accept traffic.

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `ReadinessResponse`
- Required top-level fields: `details, ready`

```json
{
  "details": {
    "config": true,
    "database": true
  },
  "ready": true,
  "timestamp": "2026-04-06T06:42:52Z"
}
```

---

### GET /api/v1/issued-assets

- Summary: List Issued Assets
- Operation ID: `list_issued_assets_api_v1_issued_assets_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `recipient_id` | `query` | no | `anyOf` |  |
| `item_id` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `IssuedAssetListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "recipient_id": 0,
      "recipient_name": "recipient name",
      "recipient_type": "recipient type",
      "item_id": 0,
      "item_name": "item name",
      "sku": "...",
      "qty": "qty",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/lost-assets

- Summary: List Lost Assets
- Operation ID: `list_lost_assets_api_v1_lost_assets_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` |  |
| `source_site_id` | `query` | no | `anyOf` |  |
| `operation_id` | `query` | no | `anyOf` |  |
| `item_id` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `updated_after` | `query` | no | `anyOf` |  |
| `updated_before` | `query` | no | `anyOf` |  |
| `qty_from` | `query` | no | `anyOf` |  |
| `qty_to` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `LostAssetListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "operation_id": "00000000-0000-0000-0000-000000000000",
      "operation_line_id": 0,
      "site_id": 0,
      "site_name": "site name",
      "source_site_id": "...",
      "source_site_name": "...",
      "item_id": 0,
      "item_name": "item name",
      "sku": "...",
      "qty": "qty",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/lost-assets/{operation_line_id}

- Summary: Get Lost Asset
- Operation ID: `get_lost_asset_api_v1_lost_assets__operation_line_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_line_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `LostAssetRow`
- Required top-level fields: `item_id, item_name, operation_id, operation_line_id, qty, site_id, site_name, updated_at`

```json
{
  "operation_id": "00000000-0000-0000-0000-000000000000",
  "operation_line_id": 0,
  "site_id": 0,
  "site_name": "site name",
  "source_site_id": 0,
  "source_site_name": "string",
  "item_id": 0,
  "item_name": "item name",
  "sku": "string",
  "qty": "qty",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/lost-assets/{operation_line_id}/resolve

- Summary: Resolve Lost Asset
- Operation ID: `resolve_lost_asset_api_v1_lost_assets__operation_line_id__resolve_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_line_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `LostAssetResolveRequest`
- Required top-level fields: `action, qty`

```json
{
  "action": "found_to_destination",
  "qty": 0,
  "note": "string",
  "responsible_recipient_id": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Resolve Lost Asset Api V1 Lost Assets  Operation Line Id  Resolve Post`

```json
{}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/operations

- Summary: List Operations
- Operation ID: `list_operations_api_v1_operations_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` |  |
| `type` | `query` | no | `anyOf` |  |
| `status` | `query` | no | `anyOf` |  |
| `created_by_user_id` | `query` | no | `anyOf` |  |
| `effective_after` | `query` | no | `anyOf` |  |
| `effective_before` | `query` | no | `anyOf` |  |
| `created_after` | `query` | no | `anyOf` |  |
| `created_before` | `query` | no | `anyOf` |  |
| `updated_after` | `query` | no | `anyOf` |  |
| `updated_before` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "site_id": 0,
      "operation_type": "RECEIVE",
      "status": "draft",
      "effective_at": "...",
      "source_site_id": "...",
      "destination_site_id": "...",
      "issued_to_user_id": "...",
      "issued_to_name": "...",
      "recipient_id": "...",
      "recipient_name_snapshot": "...",
      "acceptance_required": true,
      "acceptance_state": "not_required",
      "acceptance_resolved_at": "...",
      "acceptance_resolved_by_user_id": "...",
      "created_by_user_id": "00000000-0000-0000-0000-000000000000",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "submitted_at": "...",
      "submitted_by_user_id": "...",
      "cancelled_at": "...",
      "cancelled_by_user_id": "...",
      "notes": "...",
      "lines": [
        "..."
      ]
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/operations

- Summary: Create Operation
- Operation ID: `create_operation_api_v1_operations_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `OperationCreate`
- Required top-level fields: `lines, operation_type, site_id`

```json
{
  "operation_type": "RECEIVE",
  "site_id": 0,
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "lines": [
    {
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "batch": "...",
      "comment": "..."
    }
  ],
  "notes": "string"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/operations/{operation_id}

- Summary: Get Operation
- Operation ID: `get_operation_api_v1_operations__operation_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/operations/{operation_id}

- Summary: Update Operation
- Operation ID: `update_operation_api_v1_operations__operation_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `OperationUpdate`

```json
{
  "notes": "string",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "lines": [
    {
      "line_number": "...",
      "item_id": "...",
      "qty": "...",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/operations/{operation_id}/accept-lines

- Summary: Accept Operation Lines
- Operation ID: `accept_operation_lines_api_v1_operations__operation_id__accept_lines_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `OperationAcceptLinesRequest`
- Required top-level fields: `lines`

```json
{
  "lines": [
    {
      "line_id": 0,
      "accepted_qty": "...",
      "lost_qty": "...",
      "note": "..."
    }
  ]
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/operations/{operation_id}/cancel

- Summary: Cancel Operation
- Operation ID: `cancel_operation_api_v1_operations__operation_id__cancel_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `OperationCancel`

```json
{
  "cancel": true,
  "reason": "string"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/operations/{operation_id}/effective-at

- Summary: Update Operation Effective At
- Operation ID: `update_operation_effective_at_api_v1_operations__operation_id__effective_at_patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `OperationEffectiveAtUpdate`
- Required top-level fields: `effective_at`

```json
{
  "effective_at": "2026-01-01T00:00:00Z"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/operations/{operation_id}/submit

- Summary: Submit Operation
- Operation ID: `submit_operation_api_v1_operations__operation_id__submit_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | `path` | yes | `string` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `OperationSubmit`

```json
{
  "submit": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `OperationResponse`
- Required top-level fields: `created_at, created_by_user_id, id, operation_type, site_id, status, updated_at`

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "site_id": 0,
  "operation_type": "RECEIVE",
  "status": "draft",
  "effective_at": "2026-01-01T00:00:00Z",
  "source_site_id": 0,
  "destination_site_id": 0,
  "issued_to_user_id": "00000000-0000-0000-0000-000000000000",
  "issued_to_name": "string",
  "recipient_id": 0,
  "recipient_name_snapshot": "string",
  "acceptance_required": true,
  "acceptance_state": "not_required",
  "acceptance_resolved_at": "2026-01-01T00:00:00Z",
  "acceptance_resolved_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_by_user_id": "00000000-0000-0000-0000-000000000000",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submitted_by_user_id": "00000000-0000-0000-0000-000000000000",
  "cancelled_at": "2026-01-01T00:00:00Z",
  "cancelled_by_user_id": "00000000-0000-0000-0000-000000000000",
  "notes": "string",
  "lines": [
    {
      "id": 0,
      "line_number": 0,
      "item_id": 0,
      "qty": 0,
      "accepted_qty": "accepted qty",
      "lost_qty": "lost qty",
      "batch": "...",
      "comment": "..."
    }
  ]
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/pending-acceptance

- Summary: List Pending Acceptance
- Operation ID: `list_pending_acceptance_api_v1_pending_acceptance_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` |  |
| `operation_id` | `query` | no | `anyOf` |  |
| `item_id` | `query` | no | `anyOf` |  |
| `search` | `query` | no | `anyOf` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `PendingAcceptanceListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "operation_id": "00000000-0000-0000-0000-000000000000",
      "operation_line_id": 0,
      "destination_site_id": 0,
      "destination_site_name": "destination site name",
      "source_site_id": "...",
      "item_id": 0,
      "item_name": "item name",
      "sku": "...",
      "qty": "qty",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/ping

- Summary: Ping
- Operation ID: `ping_api_v1_ping_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Client-Version` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `PingRequest`
- Required top-level fields: `device_id, site_id`

```json
{
  "site_id": 0,
  "device_id": 0,
  "last_server_seq": 0,
  "outbox_count": 0,
  "client_time": "2026-01-01T00:00:00Z"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `PingResponse`

```json
{
  "server_time": "2026-01-01T00:00:00Z",
  "server_seq_upto": 0,
  "backoff_seconds": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/pull

- Summary: Pull
- Operation ID: `pull_api_v1_pull_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Client-Version` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `PullRequest`
- Required top-level fields: `device_id, site_id`

```json
{
  "site_id": 0,
  "device_id": 0,
  "since_seq": 0,
  "limit": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `PullResponse`

```json
{
  "events": [
    {
      "event_uuid": "00000000-0000-0000-0000-000000000000",
      "server_seq": 0,
      "event_type": "event type",
      "event_datetime": "2026-01-01T00:00:00Z",
      "schema_version": 0,
      "payload": "..."
    }
  ],
  "server_time": "2026-01-01T00:00:00Z",
  "server_seq_upto": 0,
  "next_since_seq": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/push

- Summary: Push
- Operation ID: `push_api_v1_push_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-Client-Version` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `PushRequest`
- Required top-level fields: `batch_id, device_id, site_id`

```json
{
  "site_id": 0,
  "device_id": 0,
  "batch_id": "00000000-0000-0000-0000-000000000000",
  "events": [
    {
      "event_uuid": "00000000-0000-0000-0000-000000000000",
      "event_type": "event type",
      "event_datetime": "2026-01-01T00:00:00Z",
      "schema_version": 0,
      "payload": "..."
    }
  ]
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `PushResponse`

```json
{
  "accepted": [
    {
      "event_uuid": "00000000-0000-0000-0000-000000000000",
      "server_seq": 0
    }
  ],
  "duplicates": [
    {
      "event_uuid": "00000000-0000-0000-0000-000000000000",
      "server_seq": 0
    }
  ],
  "rejected": [
    {
      "event_uuid": "00000000-0000-0000-0000-000000000000",
      "reason_code": "uuid_collision",
      "message": "message"
    }
  ],
  "server_time": "2026-01-01T00:00:00Z",
  "server_seq_upto": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/ready

- Summary: Ready
- Operation ID: `ready_api_v1_ready_get`
- Description: Readiness check with database connection test.

**Parameters**

_None_

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `Response Ready Api V1 Ready Get`

```json
{
  "key": "string"
}
```

---

### GET /api/v1/recipients

- Summary: List Recipients
- Operation ID: `list_recipients_api_v1_recipients_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `search` | `query` | no | `anyOf` |  |
| `recipient_type` | `query` | no | `anyOf` |  |
| `include_inactive` | `query` | no | `boolean` |  |
| `include_deleted` | `query` | no | `boolean` |  |
| `page` | `query` | no | `integer` |  |
| `page_size` | `query` | no | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `RecipientListResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "id": 0,
      "recipient_type": "recipient type",
      "display_name": "display name",
      "normalized_key": "normalized key",
      "personnel_no": "...",
      "is_active": true,
      "merged_into_id": "...",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "deleted_at": "...",
      "deleted_by_user_id": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/recipients

- Summary: Create Recipient
- Operation ID: `create_recipient_api_v1_recipients_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `RecipientCreate`
- Required top-level fields: `display_name`

```json
{
  "display_name": "display name",
  "recipient_type": "recipient type",
  "personnel_no": "string"
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `RecipientResponse`
- Required top-level fields: `created_at, display_name, id, is_active, normalized_key, recipient_type, updated_at`

```json
{
  "id": 0,
  "recipient_type": "recipient type",
  "display_name": "display name",
  "normalized_key": "normalized key",
  "personnel_no": "string",
  "is_active": true,
  "merged_into_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### POST /api/v1/recipients/merge

- Summary: Merge Recipients
- Operation ID: `merge_recipients_api_v1_recipients_merge_post`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `RecipientMerge`
- Required top-level fields: `source_id, target_id`

```json
{
  "source_id": 0,
  "target_id": 0
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `RecipientResponse`
- Required top-level fields: `created_at, display_name, id, is_active, normalized_key, recipient_type, updated_at`

```json
{
  "id": 0,
  "recipient_type": "recipient type",
  "display_name": "display name",
  "normalized_key": "normalized key",
  "personnel_no": "string",
  "is_active": true,
  "merged_into_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/recipients/{recipient_id}

- Summary: Get Recipient
- Operation ID: `get_recipient_api_v1_recipients__recipient_id__get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `recipient_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `RecipientResponse`
- Required top-level fields: `created_at, display_name, id, is_active, normalized_key, recipient_type, updated_at`

```json
{
  "id": 0,
  "recipient_type": "recipient type",
  "display_name": "display name",
  "normalized_key": "normalized key",
  "personnel_no": "string",
  "is_active": true,
  "merged_into_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### PATCH /api/v1/recipients/{recipient_id}

- Summary: Update Recipient
- Operation ID: `update_recipient_api_v1_recipients__recipient_id__patch`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `recipient_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

- Required: yes
- Content-Type: `application/json`
- Schema: `RecipientUpdate`

```json
{
  "display_name": "string",
  "recipient_type": "string",
  "personnel_no": "string",
  "is_active": true
}
```

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `RecipientResponse`
- Required top-level fields: `created_at, display_name, id, is_active, normalized_key, recipient_type, updated_at`

```json
{
  "id": 0,
  "recipient_type": "recipient type",
  "display_name": "display name",
  "normalized_key": "normalized key",
  "personnel_no": "string",
  "is_active": true,
  "merged_into_id": 0,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "deleted_at": "2026-01-01T00:00:00Z",
  "deleted_by_user_id": "00000000-0000-0000-0000-000000000000"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### DELETE /api/v1/recipients/{recipient_id}

- Summary: Delete Recipient
- Operation ID: `delete_recipient_api_v1_recipients__recipient_id__delete`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `recipient_id` | `path` | yes | `integer` |  |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 204

- Description: Successful Response
_No response body_

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/reports/item-movement

- Summary: List Item Movement Report
- Operation ID: `list_item_movement_report_api_v1_reports_item_movement_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` | Filter by site ID |
| `item_id` | `query` | no | `anyOf` | Filter by item ID |
| `category_id` | `query` | no | `anyOf` | Filter by category ID |
| `search` | `query` | no | `anyOf` | Search in item, category, or site labels |
| `date_from` | `query` | no | `anyOf` | Inclusive report start datetime |
| `date_to` | `query` | no | `anyOf` | Inclusive report end datetime |
| `page` | `query` | no | `integer` | Page number |
| `page_size` | `query` | no | `integer` | Page size |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `ItemMovementReportResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "site_id": 0,
      "site_name": "site name",
      "item_id": 0,
      "item_name": "item name",
      "sku": "...",
      "unit_id": 0,
      "unit_symbol": "unit symbol",
      "category_id": 0,
      "category_name": "category name",
      "incoming_qty": "incoming qty",
      "outgoing_qty": "outgoing qty",
      "net_qty": "net qty",
      "last_operation_at": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0,
  "date_from": "2026-01-01T00:00:00Z",
  "date_to": "2026-01-01T00:00:00Z"
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

### GET /api/v1/reports/stock-summary

- Summary: List Stock Summary Report
- Operation ID: `list_stock_summary_report_api_v1_reports_stock_summary_get`

**Parameters**

| Name | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `site_id` | `query` | no | `anyOf` | Filter by site ID |
| `category_id` | `query` | no | `anyOf` | Filter by category ID |
| `search` | `query` | no | `anyOf` | Search in item, category, or site labels |
| `only_positive` | `query` | no | `boolean` | Show only positive balances |
| `page` | `query` | no | `integer` | Page number |
| `page_size` | `query` | no | `integer` | Page size |
| `X-User-Token` | `header` | no | `anyOf` |  |
| `X-Device-Token` | `header` | no | `anyOf` |  |
| `X-Client-Version` | `header` | no | `anyOf` |  |

**Request body**

_No request body_

**Expected responses**

#### 200

- Description: Successful Response
- Content-Type: `application/json`
- Schema: `StockSummaryReportResponse`
- Required top-level fields: `items, page, page_size, total_count`

```json
{
  "items": [
    {
      "site_id": 0,
      "site_name": "site name",
      "items_count": 0,
      "positive_items_count": 0,
      "total_quantity": "total quantity",
      "last_balance_at": "..."
    }
  ],
  "total_count": 0,
  "page": 0,
  "page_size": 0
}
```

#### 422

- Description: Validation Error
- Content-Type: `application/json`
- Schema: `HTTPValidationError`

```json
{
  "detail": [
    {
      "loc": [
        "..."
      ],
      "msg": "message",
      "type": "error type",
      "input": {},
      "ctx": {}
    }
  ]
}
```

---

## Component Schemas

Полные JSON Schema definitions для именованных request/response моделей из OpenAPI.

### AcceptedEvent

```json
{
  "properties": {
    "event_uuid": {
      "type": "string",
      "format": "uuid",
      "title": "Event Uuid"
    },
    "server_seq": {
      "type": "integer",
      "title": "Server Seq"
    }
  },
  "type": "object",
  "required": [
    "event_uuid",
    "server_seq"
  ],
  "title": "AcceptedEvent"
}
```

### BalanceListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/BalanceResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "BalanceListResponse"
}
```

### BalanceResponse

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "site_name": {
      "type": "string",
      "title": "Site Name"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "item_name": {
      "type": "string",
      "title": "Item Name"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "unit_id": {
      "type": "integer",
      "title": "Unit Id"
    },
    "unit_symbol": {
      "type": "string",
      "title": "Unit Symbol"
    },
    "category_id": {
      "type": "integer",
      "title": "Category Id"
    },
    "category_name": {
      "type": "string",
      "title": "Category Name"
    },
    "qty": {
      "type": "string",
      "title": "Qty"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "site_name",
    "item_id",
    "item_name",
    "unit_id",
    "unit_symbol",
    "category_id",
    "category_name",
    "qty",
    "updated_at"
  ],
  "title": "BalanceResponse",
  "description": "UI-ready balance row."
}
```

### BalanceSummaryData

```json
{
  "properties": {
    "rows_count": {
      "type": "integer",
      "title": "Rows Count"
    },
    "sites_count": {
      "type": "integer",
      "title": "Sites Count"
    },
    "total_quantity": {
      "type": "number",
      "title": "Total Quantity"
    }
  },
  "type": "object",
  "required": [
    "rows_count",
    "sites_count",
    "total_quantity"
  ],
  "title": "BalanceSummaryData"
}
```

### BalanceSummaryResponse

```json
{
  "properties": {
    "accessible_sites_count": {
      "type": "integer",
      "title": "Accessible Sites Count"
    },
    "summary": {
      "$ref": "#/components/schemas/BalanceSummaryData"
    }
  },
  "type": "object",
  "required": [
    "accessible_sites_count",
    "summary"
  ],
  "title": "BalanceSummaryResponse"
}
```

### BootstrapData

```json
{
  "properties": {
    "available_sites": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "type": "array",
      "title": "Available Sites"
    },
    "protocol_version": {
      "type": "string",
      "title": "Protocol Version",
      "default": "1.0"
    },
    "settings": {
      "additionalProperties": true,
      "type": "object",
      "title": "Settings"
    }
  },
  "type": "object",
  "title": "BootstrapData",
  "description": "Данные начальной загрузки: доступные сайты, каталоги, настройки синхронизации."
}
```

### BootstrapSyncRequest

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id",
      "default": 0
    },
    "device_id": {
      "type": "integer",
      "title": "Device Id",
      "default": 0
    }
  },
  "type": "object",
  "title": "BootstrapSyncRequest"
}
```

### BootstrapSyncResponse

```json
{
  "properties": {
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "protocol_version": {
      "type": "string",
      "title": "Protocol Version",
      "default": "1.0"
    },
    "is_root": {
      "type": "boolean",
      "title": "Is Root",
      "default": false
    },
    "root_user": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Root User"
    },
    "root_role": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Root Role"
    },
    "device_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Device Id"
    },
    "device_registered": {
      "type": "boolean",
      "title": "Device Registered",
      "default": false
    },
    "message": {
      "type": "string",
      "title": "Message",
      "default": ""
    },
    "bootstrap_data": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/BootstrapData"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "type": "object",
  "title": "BootstrapSyncResponse"
}
```

### CatalogBrowseCategoriesResponse

```json
{
  "properties": {
    "categories": {
      "items": {
        "$ref": "#/components/schemas/CatalogBrowseCategoryDto"
      },
      "type": "array",
      "title": "Categories"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "categories",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "CatalogBrowseCategoriesResponse"
}
```

### CatalogBrowseCategoryDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    },
    "parent": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/CategorySummaryDto"
        },
        {
          "type": "null"
        }
      ]
    },
    "parent_chain_summary": {
      "items": {
        "$ref": "#/components/schemas/CategorySummaryDto"
      },
      "type": "array",
      "title": "Parent Chain Summary"
    },
    "children_count": {
      "type": "integer",
      "title": "Children Count",
      "default": 0
    },
    "items_count": {
      "type": "integer",
      "title": "Items Count",
      "default": 0
    },
    "items_preview": {
      "items": {
        "$ref": "#/components/schemas/ItemPreviewDto"
      },
      "type": "array",
      "title": "Items Preview"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "is_active",
    "updated_at"
  ],
  "title": "CatalogBrowseCategoryDto"
}
```

### CatalogBrowseItemDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "category_id": {
      "type": "integer",
      "title": "Category Id"
    },
    "category_name": {
      "type": "string",
      "title": "Category Name"
    },
    "unit_id": {
      "type": "integer",
      "title": "Unit Id"
    },
    "unit_symbol": {
      "type": "string",
      "title": "Unit Symbol"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "category_id",
    "category_name",
    "unit_id",
    "unit_symbol",
    "is_active",
    "updated_at"
  ],
  "title": "CatalogBrowseItemDto"
}
```

### CatalogBrowseItemsResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/CatalogBrowseItemDto"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "CatalogBrowseItemsResponse"
}
```

### CatalogCategoriesResponse

```json
{
  "properties": {
    "categories": {
      "items": {
        "$ref": "#/components/schemas/CategoryDto"
      },
      "type": "array",
      "title": "Categories"
    },
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "next_updated_after": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Updated After"
    }
  },
  "type": "object",
  "required": [
    "categories"
  ],
  "title": "CatalogCategoriesResponse"
}
```

### CatalogItemsResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/ItemDto"
      },
      "type": "array",
      "title": "Items"
    },
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "next_updated_after": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Updated After"
    }
  },
  "type": "object",
  "required": [
    "items"
  ],
  "title": "CatalogItemsResponse"
}
```

### CatalogSiteDto

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "code": {
      "type": "string",
      "title": "Code"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "permissions": {
      "additionalProperties": {
        "type": "boolean"
      },
      "type": "object",
      "title": "Permissions"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "code",
    "name",
    "is_active",
    "permissions"
  ],
  "title": "CatalogSiteDto"
}
```

### CatalogSitesResponse

```json
{
  "properties": {
    "sites": {
      "items": {
        "$ref": "#/components/schemas/CatalogSiteDto"
      },
      "type": "array",
      "title": "Sites"
    },
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    }
  },
  "type": "object",
  "required": [
    "sites"
  ],
  "title": "CatalogSitesResponse"
}
```

### CatalogUnitsResponse

```json
{
  "properties": {
    "units": {
      "items": {
        "$ref": "#/components/schemas/UnitDto"
      },
      "type": "array",
      "title": "Units"
    },
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "next_updated_after": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Next Updated After"
    }
  },
  "type": "object",
  "required": [
    "units"
  ],
  "title": "CatalogUnitsResponse"
}
```

### CategoryCreateRequest

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 255,
      "minLength": 1,
      "title": "Name"
    },
    "code": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "default": true
    }
  },
  "type": "object",
  "required": [
    "name"
  ],
  "title": "CategoryCreateRequest"
}
```

### CategoryDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "is_active",
    "updated_at"
  ],
  "title": "CategoryDto"
}
```

### CategoryListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/CategoryResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "CategoryListResponse"
}
```

### CategoryParentChainResponse

```json
{
  "properties": {
    "category_id": {
      "type": "integer",
      "title": "Category Id"
    },
    "parent_chain_summary": {
      "items": {
        "$ref": "#/components/schemas/CategorySummaryDto"
      },
      "type": "array",
      "title": "Parent Chain Summary"
    }
  },
  "type": "object",
  "required": [
    "category_id"
  ],
  "title": "CategoryParentChainResponse"
}
```

### CategoryResponse

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "deleted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted At"
    },
    "deleted_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted By User Id"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "CategoryResponse"
}
```

### CategorySummaryDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name"
  ],
  "title": "CategorySummaryDto"
}
```

### CategoryTreeNode

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "path": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Path"
    },
    "children": {
      "items": {
        "$ref": "#/components/schemas/CategoryTreeNode"
      },
      "type": "array",
      "title": "Children"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "CategoryTreeNode"
}
```

### CategoryUpdateRequest

```json
{
  "properties": {
    "name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "code": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    }
  },
  "type": "object",
  "title": "CategoryUpdateRequest"
}
```

### DeviceCreate

```json
{
  "properties": {
    "device_code": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Device Code"
    },
    "device_name": {
      "type": "string",
      "maxLength": 255,
      "minLength": 1,
      "title": "Device Name"
    },
    "site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Site Id",
      "description": "Nullable if device is not bound to site"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "default": true
    }
  },
  "type": "object",
  "required": [
    "device_name"
  ],
  "title": "DeviceCreate",
  "description": "Schema for creating a device."
}
```

### DeviceListResponse

```json
{
  "properties": {
    "devices": {
      "items": {
        "$ref": "#/components/schemas/DeviceResponse"
      },
      "type": "array",
      "title": "Devices"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "devices",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "DeviceListResponse"
}
```

### DeviceResponse

```json
{
  "properties": {
    "device_id": {
      "type": "integer",
      "title": "Device Id"
    },
    "device_code": {
      "type": "string",
      "title": "Device Code"
    },
    "device_name": {
      "type": "string",
      "title": "Device Name"
    },
    "site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Site Id"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "last_seen_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Seen At"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "device_id",
    "device_code",
    "device_name",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "DeviceResponse",
  "description": "Schema for device response."
}
```

### DeviceTokenResponse

```json
{
  "properties": {
    "device_id": {
      "type": "integer",
      "title": "Device Id"
    },
    "device_token": {
      "type": "string",
      "format": "uuid",
      "title": "Device Token"
    },
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Generated At"
    }
  },
  "type": "object",
  "required": [
    "device_id",
    "device_token",
    "generated_at"
  ],
  "title": "DeviceTokenResponse",
  "description": "Token output schema.\nUse this schema for explicit token read/rotation endpoints only."
}
```

### DeviceUpdate

```json
{
  "properties": {
    "device_code": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Device Code"
    },
    "device_name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Device Name"
    },
    "site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Site Id"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    }
  },
  "type": "object",
  "title": "DeviceUpdate",
  "description": "Schema for updating a device."
}
```

### DeviceWithTokenResponse

```json
{
  "properties": {
    "device_id": {
      "type": "integer",
      "title": "Device Id"
    },
    "device_code": {
      "type": "string",
      "title": "Device Code"
    },
    "device_name": {
      "type": "string",
      "title": "Device Name"
    },
    "site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Site Id"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "last_seen_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Seen At"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "device_token": {
      "type": "string",
      "format": "uuid",
      "title": "Device Token"
    }
  },
  "type": "object",
  "required": [
    "device_id",
    "device_code",
    "device_name",
    "is_active",
    "created_at",
    "updated_at",
    "device_token"
  ],
  "title": "DeviceWithTokenResponse",
  "description": "Schema for device create response including the generated token."
}
```

### DocumentGenerateRequest

```json
{
  "properties": {
    "operation_id": {
      "type": "string",
      "format": "uuid",
      "title": "Operation Id"
    },
    "document_type": {
      "type": "string",
      "enum": [
        "waybill",
        "acceptance_certificate",
        "act",
        "invoice"
      ],
      "title": "Document Type",
      "default": "waybill"
    },
    "template_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Template Name"
    },
    "auto_finalize": {
      "type": "boolean",
      "title": "Auto Finalize",
      "default": false
    },
    "language": {
      "type": "string",
      "title": "Language",
      "description": "Язык документа (например: ru, en)",
      "default": "ru"
    },
    "basis_type": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Basis Type",
      "description": "Тип основания документа (договор, заявка, приказ)"
    },
    "basis_number": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Basis Number",
      "description": "Номер основания документа"
    },
    "basis_date": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Basis Date",
      "description": "Дата основания документа"
    }
  },
  "type": "object",
  "required": [
    "operation_id"
  ],
  "title": "DocumentGenerateRequest",
  "description": "Request to generate a document from an operation."
}
```

### DocumentListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/DocumentResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total": {
      "type": "integer",
      "title": "Total"
    },
    "offset": {
      "type": "integer",
      "title": "Offset"
    },
    "limit": {
      "type": "integer",
      "title": "Limit"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total",
    "offset",
    "limit"
  ],
  "title": "DocumentListResponse",
  "description": "Paginated list of documents."
}
```

### DocumentResponse

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "document_type": {
      "type": "string",
      "enum": [
        "waybill",
        "acceptance_certificate",
        "act",
        "invoice"
      ],
      "title": "Document Type"
    },
    "document_number": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Document Number"
    },
    "revision": {
      "type": "integer",
      "title": "Revision"
    },
    "status": {
      "type": "string",
      "enum": [
        "draft",
        "finalized",
        "void",
        "superseded"
      ],
      "title": "Status"
    },
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "template_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Template Name"
    },
    "template_version": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Template Version"
    },
    "payload_schema_version": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Payload Schema Version"
    },
    "payload": {
      "additionalProperties": true,
      "type": "object",
      "title": "Payload"
    },
    "payload_hash": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Payload Hash"
    },
    "created_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Created By User Id"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "finalized_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Finalized At"
    },
    "supersedes_document_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Supersedes Document Id"
    }
  },
  "type": "object",
  "required": [
    "id",
    "document_type",
    "document_number",
    "revision",
    "status",
    "site_id",
    "template_name",
    "template_version",
    "payload_schema_version",
    "payload",
    "payload_hash",
    "created_by_user_id",
    "created_at",
    "finalized_at",
    "supersedes_document_id"
  ],
  "title": "DocumentResponse",
  "description": "Full document response."
}
```

### DocumentUpdate

```json
{
  "properties": {
    "status": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "draft",
            "finalized",
            "void",
            "superseded"
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Status"
    },
    "finalized_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Finalized At"
    },
    "payload": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Payload"
    },
    "payload_hash": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Payload Hash"
    }
  },
  "type": "object",
  "title": "DocumentUpdate",
  "description": "Input for updating a document (partial)."
}
```

### DuplicateEvent

```json
{
  "properties": {
    "event_uuid": {
      "type": "string",
      "format": "uuid",
      "title": "Event Uuid"
    },
    "server_seq": {
      "type": "integer",
      "title": "Server Seq"
    }
  },
  "type": "object",
  "required": [
    "event_uuid",
    "server_seq"
  ],
  "title": "DuplicateEvent"
}
```

### EventIn

```json
{
  "properties": {
    "event_uuid": {
      "type": "string",
      "format": "uuid",
      "title": "Event Uuid"
    },
    "event_type": {
      "type": "string",
      "title": "Event Type"
    },
    "event_datetime": {
      "type": "string",
      "format": "date-time",
      "title": "Event Datetime"
    },
    "schema_version": {
      "type": "integer",
      "title": "Schema Version",
      "default": 1
    },
    "payload": {
      "$ref": "#/components/schemas/EventPayload-Input"
    }
  },
  "type": "object",
  "required": [
    "event_uuid",
    "event_type",
    "event_datetime",
    "payload"
  ],
  "title": "EventIn"
}
```

### EventLine-Input

```json
{
  "properties": {
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "qty": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,15}|(?=[\\d.]{1,19}0*$)\\d{0,15}\\.\\d{0,3}0*$)"
        }
      ],
      "title": "Qty"
    },
    "batch": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Batch"
    }
  },
  "type": "object",
  "required": [
    "item_id",
    "qty"
  ],
  "title": "EventLine"
}
```

### EventLine-Output

```json
{
  "properties": {
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,15}|(?=[\\d.]{1,19}0*$)\\d{0,15}\\.\\d{0,3}0*$)",
      "title": "Qty"
    },
    "batch": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Batch"
    }
  },
  "type": "object",
  "required": [
    "item_id",
    "qty"
  ],
  "title": "EventLine"
}
```

### EventPayload-Input

```json
{
  "properties": {
    "doc_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Doc Id"
    },
    "doc_type": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Doc Type"
    },
    "comment": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Comment"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/EventLine-Input"
      },
      "type": "array",
      "title": "Lines"
    }
  },
  "type": "object",
  "title": "EventPayload"
}
```

### EventPayload-Output

```json
{
  "properties": {
    "doc_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Doc Id"
    },
    "doc_type": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Doc Type"
    },
    "comment": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Comment"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/EventLine-Output"
      },
      "type": "array",
      "title": "Lines"
    }
  },
  "type": "object",
  "title": "EventPayload"
}
```

### HTTPValidationError

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "type": "array",
      "title": "Detail"
    }
  },
  "type": "object",
  "title": "HTTPValidationError"
}
```

### HealthCheckDetail

```json
{
  "properties": {
    "status": {
      "$ref": "#/components/schemas/HealthStatus",
      "description": "Статус проверки"
    },
    "latency_ms": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Latency Ms",
      "description": "Время выполнения в миллисекундах"
    },
    "details": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Details",
      "description": "Дополнительная информация"
    },
    "error": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Error",
      "description": "Сообщение об ошибке, если есть"
    }
  },
  "type": "object",
  "required": [
    "status"
  ],
  "title": "HealthCheckDetail",
  "description": "Детали одной проверки здоровья.",
  "example": {
    "details": "Connection successful",
    "latency_ms": 12.5,
    "status": "healthy"
  }
}
```

### HealthCheckResponse

```json
{
  "properties": {
    "status": {
      "$ref": "#/components/schemas/HealthStatus",
      "description": "Общий статус системы"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "title": "Timestamp",
      "description": "Время проверки"
    },
    "version": {
      "type": "string",
      "title": "Version",
      "description": "Версия приложения",
      "default": "1.0.0"
    },
    "checks": {
      "additionalProperties": {
        "$ref": "#/components/schemas/HealthCheckDetail"
      },
      "type": "object",
      "title": "Checks",
      "description": "Результаты отдельных проверок"
    }
  },
  "type": "object",
  "required": [
    "status",
    "checks"
  ],
  "title": "HealthCheckResponse",
  "description": "Ответ на запрос проверки здоровья.",
  "example": {
    "checks": {
      "cache": {
        "details": "Connection timeout",
        "error": "Redis connection failed",
        "status": "unhealthy"
      },
      "config": {
        "details": "All required configs present",
        "status": "healthy"
      },
      "database": {
        "details": "Connection successful",
        "latency_ms": 8.2,
        "status": "healthy"
      }
    },
    "status": "degraded",
    "timestamp": "2026-04-06T06:42:52Z",
    "version": "1.0.0"
  }
}
```

### HealthStatus

```json
{
  "type": "string",
  "enum": [
    "healthy",
    "degraded",
    "unhealthy",
    "not_configured"
  ],
  "title": "HealthStatus",
  "description": "Статус проверки здоровья."
}
```

### IssuedAssetListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/IssuedAssetRow"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "IssuedAssetListResponse"
}
```

### IssuedAssetRow

```json
{
  "properties": {
    "recipient_id": {
      "type": "integer",
      "title": "Recipient Id"
    },
    "recipient_name": {
      "type": "string",
      "title": "Recipient Name"
    },
    "recipient_type": {
      "type": "string",
      "title": "Recipient Type"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "item_name": {
      "type": "string",
      "title": "Item Name"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Qty"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "recipient_id",
    "recipient_name",
    "recipient_type",
    "item_id",
    "item_name",
    "qty",
    "updated_at"
  ],
  "title": "IssuedAssetRow"
}
```

### ItemCreateRequest

```json
{
  "properties": {
    "sku": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "name": {
      "type": "string",
      "maxLength": 255,
      "minLength": 1,
      "title": "Name"
    },
    "category_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Category Id"
    },
    "unit_id": {
      "type": "integer",
      "title": "Unit Id"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "hashtags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Hashtags"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "default": true
    }
  },
  "type": "object",
  "required": [
    "name",
    "unit_id"
  ],
  "title": "ItemCreateRequest"
}
```

### ItemDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "category_id": {
      "type": "integer",
      "title": "Category Id"
    },
    "unit_id": {
      "type": "integer",
      "title": "Unit Id"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "hashtags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Hashtags"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "category_id",
    "unit_id",
    "is_active",
    "updated_at"
  ],
  "title": "ItemDto"
}
```

### ItemListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/ItemResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "ItemListResponse"
}
```

### ItemMovementReportResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/ItemMovementRow"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    },
    "date_from": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Date From"
    },
    "date_to": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Date To"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "ItemMovementReportResponse"
}
```

### ItemMovementRow

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "site_name": {
      "type": "string",
      "title": "Site Name"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "item_name": {
      "type": "string",
      "title": "Item Name"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "unit_id": {
      "type": "integer",
      "title": "Unit Id"
    },
    "unit_symbol": {
      "type": "string",
      "title": "Unit Symbol"
    },
    "category_id": {
      "type": "integer",
      "title": "Category Id"
    },
    "category_name": {
      "type": "string",
      "title": "Category Name"
    },
    "incoming_qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Incoming Qty"
    },
    "outgoing_qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Outgoing Qty"
    },
    "net_qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Net Qty"
    },
    "last_operation_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Operation At"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "site_name",
    "item_id",
    "item_name",
    "unit_id",
    "unit_symbol",
    "category_id",
    "category_name",
    "incoming_qty",
    "outgoing_qty",
    "net_qty"
  ],
  "title": "ItemMovementRow"
}
```

### ItemPreviewDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name"
  ],
  "title": "ItemPreviewDto"
}
```

### ItemResponse

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "category_id": {
      "type": "integer",
      "title": "Category Id"
    },
    "unit_id": {
      "type": "integer",
      "title": "Unit Id"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "hashtags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Hashtags"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "deleted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted At"
    },
    "deleted_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted By User Id"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "category_id",
    "unit_id",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "ItemResponse"
}
```

### ItemUpdateRequest

```json
{
  "properties": {
    "sku": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "category_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Category Id"
    },
    "unit_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Unit Id"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "hashtags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Hashtags"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    }
  },
  "type": "object",
  "title": "ItemUpdateRequest"
}
```

### LivenessResponse

```json
{
  "properties": {
    "alive": {
      "type": "boolean",
      "title": "Alive",
      "description": "Жива ли система"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "title": "Timestamp",
      "description": "Время проверки"
    }
  },
  "type": "object",
  "required": [
    "alive"
  ],
  "title": "LivenessResponse",
  "description": "Ответ на запрос живучести системы.",
  "example": {
    "alive": true,
    "timestamp": "2026-04-06T06:42:52Z"
  }
}
```

### LostAssetListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/LostAssetRow"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "LostAssetListResponse"
}
```

### LostAssetResolveRequest

```json
{
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "found_to_destination",
        "return_to_source",
        "write_off"
      ],
      "title": "Action"
    },
    "qty": {
      "anyOf": [
        {
          "type": "number",
          "exclusiveMinimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"
        }
      ],
      "title": "Qty"
    },
    "note": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 500
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "responsible_recipient_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Responsible Recipient Id"
    }
  },
  "type": "object",
  "required": [
    "action",
    "qty"
  ],
  "title": "LostAssetResolveRequest"
}
```

### LostAssetRow

```json
{
  "properties": {
    "operation_id": {
      "type": "string",
      "format": "uuid",
      "title": "Operation Id"
    },
    "operation_line_id": {
      "type": "integer",
      "title": "Operation Line Id"
    },
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "site_name": {
      "type": "string",
      "title": "Site Name"
    },
    "source_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Site Id"
    },
    "source_site_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Site Name"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "item_name": {
      "type": "string",
      "title": "Item Name"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Qty"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "operation_id",
    "operation_line_id",
    "site_id",
    "site_name",
    "item_id",
    "item_name",
    "qty",
    "updated_at"
  ],
  "title": "LostAssetRow"
}
```

### OperationAcceptLinePayload

```json
{
  "properties": {
    "line_id": {
      "type": "integer",
      "title": "Line Id"
    },
    "accepted_qty": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"
        }
      ],
      "title": "Accepted Qty",
      "default": "0"
    },
    "lost_qty": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"
        }
      ],
      "title": "Lost Qty",
      "default": "0"
    },
    "note": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 500
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    }
  },
  "type": "object",
  "required": [
    "line_id"
  ],
  "title": "OperationAcceptLinePayload"
}
```

### OperationAcceptLinesRequest

```json
{
  "properties": {
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OperationAcceptLinePayload"
      },
      "type": "array",
      "minItems": 1,
      "title": "Lines"
    }
  },
  "type": "object",
  "required": [
    "lines"
  ],
  "title": "OperationAcceptLinesRequest"
}
```

### OperationCancel

```json
{
  "properties": {
    "cancel": {
      "type": "boolean",
      "title": "Cancel",
      "default": true
    },
    "reason": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 500
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason"
    }
  },
  "type": "object",
  "title": "OperationCancel"
}
```

### OperationCreate

```json
{
  "properties": {
    "operation_type": {
      "type": "string",
      "enum": [
        "RECEIVE",
        "EXPENSE",
        "WRITE_OFF",
        "MOVE",
        "ADJUSTMENT",
        "ISSUE",
        "ISSUE_RETURN"
      ],
      "title": "Operation Type"
    },
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "effective_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Effective At"
    },
    "source_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Site Id"
    },
    "destination_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Destination Site Id"
    },
    "issued_to_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Issued To User Id"
    },
    "issued_to_name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Issued To Name"
    },
    "recipient_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Id"
    },
    "recipient_name_snapshot": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Name Snapshot"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OperationLineCreate"
      },
      "type": "array",
      "minItems": 1,
      "title": "Lines"
    },
    "notes": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 1000
        },
        {
          "type": "null"
        }
      ],
      "title": "Notes"
    }
  },
  "type": "object",
  "required": [
    "operation_type",
    "site_id",
    "lines"
  ],
  "title": "OperationCreate",
  "description": "Operation create payload aligned to agreed model."
}
```

### OperationEffectiveAtUpdate

```json
{
  "properties": {
    "effective_at": {
      "type": "string",
      "format": "date-time",
      "title": "Effective At"
    }
  },
  "type": "object",
  "required": [
    "effective_at"
  ],
  "title": "OperationEffectiveAtUpdate"
}
```

### OperationLineCreate

```json
{
  "properties": {
    "line_number": {
      "type": "integer",
      "minimum": 1.0,
      "title": "Line Number"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "qty": {
      "type": "integer",
      "title": "Qty"
    },
    "batch": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Batch"
    },
    "comment": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Comment"
    }
  },
  "type": "object",
  "required": [
    "line_number",
    "item_id",
    "qty"
  ],
  "title": "OperationLineCreate",
  "description": "Operation line input aligned to current model."
}
```

### OperationLineResponse

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "line_number": {
      "type": "integer",
      "title": "Line Number"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "qty": {
      "type": "integer",
      "title": "Qty"
    },
    "accepted_qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Accepted Qty",
      "default": "0"
    },
    "lost_qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Lost Qty",
      "default": "0"
    },
    "batch": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Batch"
    },
    "comment": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Comment"
    }
  },
  "type": "object",
  "required": [
    "id",
    "line_number",
    "item_id",
    "qty"
  ],
  "title": "OperationLineResponse"
}
```

### OperationListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/OperationResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "OperationListResponse"
}
```

### OperationResponse

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "operation_type": {
      "type": "string",
      "enum": [
        "RECEIVE",
        "EXPENSE",
        "WRITE_OFF",
        "MOVE",
        "ADJUSTMENT",
        "ISSUE",
        "ISSUE_RETURN"
      ],
      "title": "Operation Type"
    },
    "status": {
      "type": "string",
      "enum": [
        "draft",
        "submitted",
        "cancelled"
      ],
      "title": "Status"
    },
    "effective_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Effective At"
    },
    "source_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Site Id"
    },
    "destination_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Destination Site Id"
    },
    "issued_to_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Issued To User Id"
    },
    "issued_to_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Issued To Name"
    },
    "recipient_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Id"
    },
    "recipient_name_snapshot": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Name Snapshot"
    },
    "acceptance_required": {
      "type": "boolean",
      "title": "Acceptance Required",
      "default": false
    },
    "acceptance_state": {
      "type": "string",
      "enum": [
        "not_required",
        "pending",
        "in_progress",
        "resolved"
      ],
      "title": "Acceptance State",
      "default": "not_required"
    },
    "acceptance_resolved_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Acceptance Resolved At"
    },
    "acceptance_resolved_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Acceptance Resolved By User Id"
    },
    "created_by_user_id": {
      "type": "string",
      "format": "uuid",
      "title": "Created By User Id"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "submitted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Submitted At"
    },
    "submitted_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Submitted By User Id"
    },
    "cancelled_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Cancelled At"
    },
    "cancelled_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Cancelled By User Id"
    },
    "notes": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Notes"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OperationLineResponse"
      },
      "type": "array",
      "title": "Lines"
    }
  },
  "type": "object",
  "required": [
    "id",
    "site_id",
    "operation_type",
    "status",
    "created_by_user_id",
    "created_at",
    "updated_at"
  ],
  "title": "OperationResponse"
}
```

### OperationSubmit

```json
{
  "properties": {
    "submit": {
      "type": "boolean",
      "title": "Submit",
      "default": true
    }
  },
  "type": "object",
  "title": "OperationSubmit"
}
```

### OperationUpdate

```json
{
  "properties": {
    "notes": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 1000
        },
        {
          "type": "null"
        }
      ],
      "title": "Notes"
    },
    "effective_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Effective At"
    },
    "source_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Site Id"
    },
    "destination_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Destination Site Id"
    },
    "issued_to_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Issued To User Id"
    },
    "issued_to_name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Issued To Name"
    },
    "recipient_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Id"
    },
    "recipient_name_snapshot": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Name Snapshot"
    },
    "lines": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/OperationLineCreate"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Lines"
    }
  },
  "type": "object",
  "title": "OperationUpdate"
}
```

### PendingAcceptanceListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/PendingAcceptanceRow"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "PendingAcceptanceListResponse"
}
```

### PendingAcceptanceRow

```json
{
  "properties": {
    "operation_id": {
      "type": "string",
      "format": "uuid",
      "title": "Operation Id"
    },
    "operation_line_id": {
      "type": "integer",
      "title": "Operation Line Id"
    },
    "destination_site_id": {
      "type": "integer",
      "title": "Destination Site Id"
    },
    "destination_site_name": {
      "type": "string",
      "title": "Destination Site Name"
    },
    "source_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Site Id"
    },
    "item_id": {
      "type": "integer",
      "title": "Item Id"
    },
    "item_name": {
      "type": "string",
      "title": "Item Name"
    },
    "sku": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sku"
    },
    "qty": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Qty"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "operation_id",
    "operation_line_id",
    "destination_site_id",
    "destination_site_name",
    "item_id",
    "item_name",
    "qty",
    "updated_at"
  ],
  "title": "PendingAcceptanceRow"
}
```

### PingRequest

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "device_id": {
      "type": "integer",
      "title": "Device Id"
    },
    "last_server_seq": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Server Seq"
    },
    "outbox_count": {
      "type": "integer",
      "title": "Outbox Count",
      "default": 0
    },
    "client_time": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Client Time"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "device_id"
  ],
  "title": "PingRequest"
}
```

### PingResponse

```json
{
  "properties": {
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "server_seq_upto": {
      "type": "integer",
      "title": "Server Seq Upto",
      "default": 0
    },
    "backoff_seconds": {
      "type": "integer",
      "title": "Backoff Seconds",
      "default": 0
    }
  },
  "type": "object",
  "title": "PingResponse"
}
```

### PullEvent

```json
{
  "properties": {
    "event_uuid": {
      "type": "string",
      "format": "uuid",
      "title": "Event Uuid"
    },
    "server_seq": {
      "type": "integer",
      "title": "Server Seq"
    },
    "event_type": {
      "type": "string",
      "title": "Event Type"
    },
    "event_datetime": {
      "type": "string",
      "format": "date-time",
      "title": "Event Datetime"
    },
    "schema_version": {
      "type": "integer",
      "title": "Schema Version"
    },
    "payload": {
      "$ref": "#/components/schemas/EventPayload-Output"
    }
  },
  "type": "object",
  "required": [
    "event_uuid",
    "server_seq",
    "event_type",
    "event_datetime",
    "schema_version",
    "payload"
  ],
  "title": "PullEvent"
}
```

### PullRequest

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "device_id": {
      "type": "integer",
      "title": "Device Id"
    },
    "since_seq": {
      "type": "integer",
      "title": "Since Seq",
      "default": 0
    },
    "limit": {
      "type": "integer",
      "maximum": 1000.0,
      "minimum": 1.0,
      "title": "Limit",
      "default": 200
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "device_id"
  ],
  "title": "PullRequest"
}
```

### PullResponse

```json
{
  "properties": {
    "events": {
      "items": {
        "$ref": "#/components/schemas/PullEvent"
      },
      "type": "array",
      "title": "Events"
    },
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "server_seq_upto": {
      "type": "integer",
      "title": "Server Seq Upto",
      "default": 0
    },
    "next_since_seq": {
      "type": "integer",
      "title": "Next Since Seq",
      "default": 0
    }
  },
  "type": "object",
  "title": "PullResponse"
}
```

### PushRequest

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "device_id": {
      "type": "integer",
      "title": "Device Id"
    },
    "batch_id": {
      "type": "string",
      "format": "uuid",
      "title": "Batch Id"
    },
    "events": {
      "items": {
        "$ref": "#/components/schemas/EventIn"
      },
      "type": "array",
      "title": "Events"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "device_id",
    "batch_id"
  ],
  "title": "PushRequest"
}
```

### PushResponse

```json
{
  "properties": {
    "accepted": {
      "items": {
        "$ref": "#/components/schemas/AcceptedEvent"
      },
      "type": "array",
      "title": "Accepted"
    },
    "duplicates": {
      "items": {
        "$ref": "#/components/schemas/DuplicateEvent"
      },
      "type": "array",
      "title": "Duplicates"
    },
    "rejected": {
      "items": {
        "$ref": "#/components/schemas/RejectedEvent"
      },
      "type": "array",
      "title": "Rejected"
    },
    "server_time": {
      "type": "string",
      "format": "date-time",
      "title": "Server Time"
    },
    "server_seq_upto": {
      "type": "integer",
      "title": "Server Seq Upto",
      "default": 0
    }
  },
  "type": "object",
  "title": "PushResponse"
}
```

### ReadinessResponse

```json
{
  "properties": {
    "ready": {
      "type": "boolean",
      "title": "Ready",
      "description": "Готова ли система к работе"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "title": "Timestamp",
      "description": "Время проверки"
    },
    "details": {
      "additionalProperties": {
        "type": "boolean"
      },
      "type": "object",
      "title": "Details",
      "description": "Статус критических зависимостей"
    }
  },
  "type": "object",
  "required": [
    "ready",
    "details"
  ],
  "title": "ReadinessResponse",
  "description": "Ответ на запрос готовности системы.",
  "example": {
    "details": {
      "config": true,
      "database": true
    },
    "ready": true,
    "timestamp": "2026-04-06T06:42:52Z"
  }
}
```

### RecipientCreate

```json
{
  "properties": {
    "display_name": {
      "type": "string",
      "maxLength": 255,
      "minLength": 1,
      "title": "Display Name"
    },
    "recipient_type": {
      "type": "string",
      "maxLength": 24,
      "title": "Recipient Type",
      "default": "person"
    },
    "personnel_no": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 64
        },
        {
          "type": "null"
        }
      ],
      "title": "Personnel No"
    }
  },
  "type": "object",
  "required": [
    "display_name"
  ],
  "title": "RecipientCreate"
}
```

### RecipientListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/RecipientResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "RecipientListResponse"
}
```

### RecipientMerge

```json
{
  "properties": {
    "source_id": {
      "type": "integer",
      "title": "Source Id"
    },
    "target_id": {
      "type": "integer",
      "title": "Target Id"
    }
  },
  "type": "object",
  "required": [
    "source_id",
    "target_id"
  ],
  "title": "RecipientMerge"
}
```

### RecipientResponse

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "recipient_type": {
      "type": "string",
      "title": "Recipient Type"
    },
    "display_name": {
      "type": "string",
      "title": "Display Name"
    },
    "normalized_key": {
      "type": "string",
      "title": "Normalized Key"
    },
    "personnel_no": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Personnel No"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "merged_into_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Merged Into Id"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "deleted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted At"
    },
    "deleted_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted By User Id"
    }
  },
  "type": "object",
  "required": [
    "id",
    "recipient_type",
    "display_name",
    "normalized_key",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "RecipientResponse"
}
```

### RecipientUpdate

```json
{
  "properties": {
    "display_name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Display Name"
    },
    "recipient_type": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 24
        },
        {
          "type": "null"
        }
      ],
      "title": "Recipient Type"
    },
    "personnel_no": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 64
        },
        {
          "type": "null"
        }
      ],
      "title": "Personnel No"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    }
  },
  "type": "object",
  "title": "RecipientUpdate"
}
```

### RejectedEvent

```json
{
  "properties": {
    "event_uuid": {
      "type": "string",
      "format": "uuid",
      "title": "Event Uuid"
    },
    "reason_code": {
      "type": "string",
      "enum": [
        "uuid_collision",
        "processing_error",
        "validation_error"
      ],
      "title": "Reason Code"
    },
    "message": {
      "type": "string",
      "title": "Message"
    }
  },
  "type": "object",
  "required": [
    "event_uuid",
    "reason_code",
    "message"
  ],
  "title": "RejectedEvent"
}
```

### SiteCreate

```json
{
  "properties": {
    "code": {
      "type": "string",
      "maxLength": 64,
      "minLength": 1,
      "title": "Code",
      "description": "Site code"
    },
    "name": {
      "type": "string",
      "maxLength": 255,
      "minLength": 1,
      "title": "Name",
      "description": "Site name"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "description": "Whether the site is active",
      "default": true
    },
    "description": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 500
        },
        {
          "type": "null"
        }
      ],
      "title": "Description",
      "description": "Optional description"
    }
  },
  "type": "object",
  "required": [
    "code",
    "name"
  ],
  "title": "SiteCreate",
  "description": "Schema for creating a site."
}
```

### SiteListResponse

```json
{
  "properties": {
    "sites": {
      "items": {
        "$ref": "#/components/schemas/SiteResponse"
      },
      "type": "array",
      "title": "Sites"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "sites",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "SiteListResponse"
}
```

### SiteResponse

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "code": {
      "type": "string",
      "title": "Code"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "code",
    "name",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "SiteResponse",
  "description": "Schema for site response (new model: int site_id)."
}
```

### SiteUpdate

```json
{
  "properties": {
    "code": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 64,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    },
    "name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    },
    "description": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 500
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    }
  },
  "type": "object",
  "title": "SiteUpdate",
  "description": "Schema for updating a site."
}
```

### StockSummaryReportResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/StockSummaryRow"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "StockSummaryReportResponse"
}
```

### StockSummaryRow

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "site_name": {
      "type": "string",
      "title": "Site Name"
    },
    "items_count": {
      "type": "integer",
      "title": "Items Count"
    },
    "positive_items_count": {
      "type": "integer",
      "title": "Positive Items Count"
    },
    "total_quantity": {
      "type": "string",
      "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$",
      "title": "Total Quantity"
    },
    "last_balance_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Balance At"
    }
  },
  "type": "object",
  "required": [
    "site_id",
    "site_name",
    "items_count",
    "positive_items_count",
    "total_quantity"
  ],
  "title": "StockSummaryRow"
}
```

### UnitCreateRequest

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Name"
    },
    "symbol": {
      "type": "string",
      "maxLength": 20,
      "minLength": 1,
      "title": "Symbol"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "default": true
    }
  },
  "type": "object",
  "required": [
    "name",
    "symbol"
  ],
  "title": "UnitCreateRequest"
}
```

### UnitDto

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "symbol": {
      "type": "string",
      "title": "Symbol"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "symbol",
    "is_active",
    "updated_at"
  ],
  "title": "UnitDto"
}
```

### UnitListResponse

```json
{
  "properties": {
    "items": {
      "items": {
        "$ref": "#/components/schemas/UnitResponse"
      },
      "type": "array",
      "title": "Items"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "items",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "UnitListResponse"
}
```

### UnitResponse

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "symbol": {
      "type": "string",
      "title": "Symbol"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "deleted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted At"
    },
    "deleted_by_user_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Deleted By User Id"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "symbol",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "UnitResponse"
}
```

### UnitUpdateRequest

```json
{
  "properties": {
    "name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "symbol": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 20,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Symbol"
    },
    "sort_order": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sort Order"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    }
  },
  "type": "object",
  "title": "UnitUpdateRequest"
}
```

### UserAccessScopeCreate

```json
{
  "properties": {
    "user_id": {
      "type": "string",
      "format": "uuid",
      "title": "User Id"
    },
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "can_view": {
      "type": "boolean",
      "title": "Can View",
      "default": true
    },
    "can_operate": {
      "type": "boolean",
      "title": "Can Operate",
      "default": false
    },
    "can_manage_catalog": {
      "type": "boolean",
      "title": "Can Manage Catalog",
      "default": false
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "default": true
    }
  },
  "type": "object",
  "required": [
    "user_id",
    "site_id"
  ],
  "title": "UserAccessScopeCreate"
}
```

### UserAccessScopeReplaceItem

```json
{
  "properties": {
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "can_view": {
      "type": "boolean",
      "title": "Can View",
      "default": true
    },
    "can_operate": {
      "type": "boolean",
      "title": "Can Operate",
      "default": false
    },
    "can_manage_catalog": {
      "type": "boolean",
      "title": "Can Manage Catalog",
      "default": false
    }
  },
  "type": "object",
  "required": [
    "site_id"
  ],
  "title": "UserAccessScopeReplaceItem"
}
```

### UserAccessScopeReplaceRequest

```json
{
  "properties": {
    "scopes": {
      "items": {
        "$ref": "#/components/schemas/UserAccessScopeReplaceItem"
      },
      "type": "array",
      "title": "Scopes"
    }
  },
  "type": "object",
  "required": [
    "scopes"
  ],
  "title": "UserAccessScopeReplaceRequest"
}
```

### UserAccessScopeResponse

```json
{
  "properties": {
    "id": {
      "type": "integer",
      "title": "Id"
    },
    "user_id": {
      "type": "string",
      "format": "uuid",
      "title": "User Id"
    },
    "site_id": {
      "type": "integer",
      "title": "Site Id"
    },
    "can_view": {
      "type": "boolean",
      "title": "Can View"
    },
    "can_operate": {
      "type": "boolean",
      "title": "Can Operate"
    },
    "can_manage_catalog": {
      "type": "boolean",
      "title": "Can Manage Catalog"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "id",
    "user_id",
    "site_id",
    "can_view",
    "can_operate",
    "can_manage_catalog",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "UserAccessScopeResponse"
}
```

### UserAccessScopeUpdate

```json
{
  "properties": {
    "can_view": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Can View"
    },
    "can_operate": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Can Operate"
    },
    "can_manage_catalog": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Can Manage Catalog"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    }
  },
  "type": "object",
  "title": "UserAccessScopeUpdate"
}
```

### UserCreate

```json
{
  "properties": {
    "id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Id"
    },
    "username": {
      "type": "string",
      "maxLength": 150,
      "minLength": 1,
      "title": "Username"
    },
    "email": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Email"
    },
    "full_name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Full Name"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active",
      "default": true
    },
    "is_root": {
      "type": "boolean",
      "title": "Is Root",
      "default": false
    },
    "role": {
      "type": "string",
      "enum": [
        "root",
        "chief_storekeeper",
        "storekeeper",
        "observer"
      ],
      "title": "Role",
      "default": "observer"
    },
    "default_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Site Id"
    }
  },
  "type": "object",
  "required": [
    "username"
  ],
  "title": "UserCreate"
}
```

### UserListResponse

```json
{
  "properties": {
    "users": {
      "items": {
        "$ref": "#/components/schemas/UserResponse"
      },
      "type": "array",
      "title": "Users"
    },
    "total_count": {
      "type": "integer",
      "title": "Total Count"
    },
    "page": {
      "type": "integer",
      "title": "Page"
    },
    "page_size": {
      "type": "integer",
      "title": "Page Size"
    }
  },
  "type": "object",
  "required": [
    "users",
    "total_count",
    "page",
    "page_size"
  ],
  "title": "UserListResponse"
}
```

### UserResponse

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "username": {
      "type": "string",
      "title": "Username"
    },
    "email": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Email"
    },
    "full_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Full Name"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "is_root": {
      "type": "boolean",
      "title": "Is Root",
      "default": false
    },
    "role": {
      "type": "string",
      "enum": [
        "root",
        "chief_storekeeper",
        "storekeeper",
        "observer"
      ],
      "title": "Role",
      "default": "observer"
    },
    "default_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Site Id"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    }
  },
  "type": "object",
  "required": [
    "id",
    "username",
    "email",
    "full_name",
    "is_active",
    "created_at",
    "updated_at"
  ],
  "title": "UserResponse"
}
```

### UserSyncStateResponse

```json
{
  "properties": {
    "user": {
      "$ref": "#/components/schemas/UserWithTokenResponse"
    },
    "scopes": {
      "items": {
        "$ref": "#/components/schemas/UserAccessScopeResponse"
      },
      "type": "array",
      "title": "Scopes"
    }
  },
  "type": "object",
  "required": [
    "user",
    "scopes"
  ],
  "title": "UserSyncStateResponse"
}
```

### UserTokenResponse

```json
{
  "properties": {
    "user_id": {
      "type": "string",
      "format": "uuid",
      "title": "User Id"
    },
    "username": {
      "type": "string",
      "title": "Username"
    },
    "user_token": {
      "type": "string",
      "format": "uuid",
      "title": "User Token"
    },
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Generated At"
    }
  },
  "type": "object",
  "required": [
    "user_id",
    "username",
    "user_token",
    "generated_at"
  ],
  "title": "UserTokenResponse",
  "description": "Token output schema for explicit user token read/rotation endpoints."
}
```

### UserUpdate

```json
{
  "properties": {
    "username": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 150,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Username"
    },
    "email": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Email"
    },
    "full_name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Full Name"
    },
    "is_active": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Active"
    },
    "is_root": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Is Root"
    },
    "role": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "root",
            "chief_storekeeper",
            "storekeeper",
            "observer"
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Role"
    },
    "default_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Site Id"
    }
  },
  "type": "object",
  "title": "UserUpdate"
}
```

### UserWithTokenResponse

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "username": {
      "type": "string",
      "title": "Username"
    },
    "email": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Email"
    },
    "full_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Full Name"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "is_root": {
      "type": "boolean",
      "title": "Is Root",
      "default": false
    },
    "role": {
      "type": "string",
      "enum": [
        "root",
        "chief_storekeeper",
        "storekeeper",
        "observer"
      ],
      "title": "Role",
      "default": "observer"
    },
    "default_site_id": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Site Id"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "title": "Updated At"
    },
    "user_token": {
      "type": "string",
      "format": "uuid",
      "title": "User Token"
    }
  },
  "type": "object",
  "required": [
    "id",
    "username",
    "email",
    "full_name",
    "is_active",
    "created_at",
    "updated_at",
    "user_token"
  ],
  "title": "UserWithTokenResponse"
}
```

### ValidationError

```json
{
  "properties": {
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "type": "array",
      "title": "Location"
    },
    "msg": {
      "type": "string",
      "title": "Message"
    },
    "type": {
      "type": "string",
      "title": "Error Type"
    },
    "input": {
      "title": "Input"
    },
    "ctx": {
      "type": "object",
      "title": "Context"
    }
  },
  "type": "object",
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError"
}
```
