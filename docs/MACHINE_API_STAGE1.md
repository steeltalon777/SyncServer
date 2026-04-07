# Machine API Stage 1

Base prefix: `/api/v1/machine`

## Auth and Access
- Uses existing SyncServer auth model:
  - `X-User-Token`
  - `X-Device-Token`
- No separate auth contour was introduced.
- Roles and permissions are reused from existing access model.

## Snapshot Endpoints
- `GET /snapshots/latest`
- `GET /snapshots/{snapshot_id}`

Snapshots are persisted in `machine_snapshots` and used as read/analysis anchors.

## Read Endpoints
- `GET /read/catalog/items`
- `GET /read/catalog/categories`
- `GET /read/catalog/units`
- `GET /read/operations`
- `GET /read/operations/{operation_id}`

Supported read query params:
- `snapshot_id`
- `cursor`
- `limit`
- `fields`
- `format=json|jsonl`

Each JSON response contains:
- `request_id`
- `schema_version`
- `snapshot_id`

## Analysis Endpoints
- `GET /analysis/duplicate-candidates/items`
- `GET /analysis/duplicate-candidates/categories`
- `GET /analysis/integrity-issues`

## Reports Endpoints
- `POST /reports`
- `GET /reports/{report_id}`
- `GET /reports/{report_id}/result`

Reports are persisted in `machine_reports` and tied to a snapshot.

## Batch Endpoints
Catalog:
- `POST /batches/catalog/preview`
- `POST /batches/catalog/apply`

Operations:
- `POST /batches/operations/preview`
- `POST /batches/operations/apply`

Batch model:
- `idempotency_key` on preview
- saved `batch_id` + `plan_id`
- apply from saved plan only
- atomic apply mode

Allowed operations actions in stage 1:
- `operation.create_draft`
- `operation.update_draft`
- `operation.submit`
- `operation.cancel`

For update/submit/cancel actions, `expected_version` is required.

## Storage / Audit Foundation
Added tables:
- `machine_snapshots`
- `machine_reports`
- `machine_batches`

Added machine/audit fields:
- `items`: `normalized_name`, `source_system`, `source_ref`, `import_batch_id`, `machine_last_batch_id`
- `categories`: `normalized_name`, `machine_last_batch_id`
- `units`: `code`, `machine_last_batch_id`
- `operations`: `version`, `machine_last_batch_id`

## Notes
- Implemented inside existing FastAPI app and `/api/v1` routing.
- Existing Django/SSR/admin consumers can call these endpoints directly without a parallel backend.
