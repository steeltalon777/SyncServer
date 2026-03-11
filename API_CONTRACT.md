# API_CONTRACT

## Notes
- HTTP API is implemented with FastAPI routers.
- No OpenAPI file is stored in repo, but FastAPI exposes generated schema at runtime (`/openapi.json`) and docs (`/docs`) by default.

## Root & health
### `GET /`
- **Response:** service info (`message`, `status`, `env`).

### `GET /db_check`
- **Response:** DB connectivity probe (`db_status`, `result`).

### `GET /health`
- **Response:** `{ "status": "ok" }`.

### `GET /ready`
- **Response:** readiness with DB check.

## Sync API
### `POST /ping`
- **Headers:** `X-Device-Token`.
- **Body:** `site_id`, `device_id`, optional `last_server_seq`, `outbox_count`, `client_time`.
- **Response:** `server_time`, `server_seq_upto`, `backoff_seconds`.

### `POST /push`
- **Headers:** `X-Device-Token`.
- **Body:** `site_id`, `device_id`, `batch_id`, `events[]`.
- **Event shape:** `event_uuid`, `event_type`, `event_datetime`, `schema_version`, `payload` (`doc_id`, `doc_type`, `comment`, `lines[]`).
- **Response:** arrays `accepted`, `duplicates`, `rejected`, plus `server_time`, `server_seq_upto`.

### `POST /pull`
- **Headers:** `X-Device-Token`.
- **Body:** `site_id`, `device_id`, `since_seq`, `limit`.
- **Response:** ordered `events[]`, `server_time`, `server_seq_upto`, `next_since_seq`.

## Catalog read API
### `POST /catalog/items`
### `POST /catalog/categories`
### `POST /catalog/units`
- **Headers:** `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, optional `X-Client-Version`.
- **Body:** `updated_after`, `limit`.
- **Response:** entity list + `server_time` + `next_updated_after`.

### `GET /catalog/categories/tree`
- **Headers:** same as catalog read.
- **Response:** hierarchical category nodes with `children` and `path`.

## Catalog admin API
### `POST /catalog/admin/units`
### `PATCH /catalog/admin/units/{unit_id}`
### `POST /catalog/admin/categories`
### `PATCH /catalog/admin/categories/{category_id}`
### `POST /catalog/admin/items`
### `PATCH /catalog/admin/items/{item_id}`
- **Headers:** `X-Site-Id`, `X-Device-Id`, `X-Device-Token`, optional `X-Client-Version`.
- **Body:** create/update DTOs from `app/schemas/catalog.py`.
- **Response:** created/updated entity DTO.
- **Validation outcomes:** `400` (invalid hierarchy), `404` (missing refs), `409` (uniqueness conflicts).
