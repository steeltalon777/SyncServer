# SyncServer Audit (transport contour)

## Working endpoints
- `POST /ping`: device auth + last seen update + `server_seq_upto` response.
- `POST /push`: idempotent ingest (`accepted`/`duplicates`/`rejected`) with per-site sequence tracking.
- `POST /pull`: incremental events by `(site_id, since_seq, limit)` ordered by `server_seq`.
- `GET /`, `GET /health`, `GET /ready`, `GET /db_check`.

## Gaps found during audit
1. No explicit DB bootstrap schema in repo (readme referenced Django-managed migrations).
2. Docker Compose did not initialize schema automatically, blocking out-of-box startup.
3. `pytest.ini` had UTF-8 BOM and broke `pytest` parsing.
4. `docs/tz-gap-analysis.md` contained stale statement that HTTP API/auth were out of scope, while code implements them.

## DB tables required for sync contour
Minimum required for target flow `ping -> push -> pull` and catalog:
- `sites`
- `devices`
- `events`
- `categories`
- `items`

Additional mapped but not required for transport-only sync loop:
- `balances`
- `user_access_scopes`

## Blocking issues for full flow before fix
- Fresh environment had no schema bootstrap path.
- Automated validation (`pytest`) failed before tests because of BOM in `pytest.ini`.

## Status after fixes
- Added bootstrap SQL (`db/init/001_init_schema.sql`) and Compose mount.
- Updated environment defaults to match Compose DB credentials.
- Fixed `pytest.ini` format.
- Updated docs to match actual API status.
