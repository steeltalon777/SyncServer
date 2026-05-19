# TZ: SyncServer Bootstrap And Root Token Recovery

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Implementation level 1 complete
- [ ] 3. Unit/component tests complete
- [ ] 4. Integration tests with real dependencies complete
- [ ] 5. Stand smoke tests complete
- [ ] 6. UI automation tests complete
- [ ] 7. User scenario tests complete
- [ ] 8. Regression checks complete
- [ ] 9. Documentation updated
- [ ] 10. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.

---

## 1. Purpose

Close audit gaps #1 and #2 from `docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md`:

- `bootstrap_root.py` must be a current, idempotent, documented way to initialize SyncServer from a safe empty database.
- Operators must have an explicit local recovery path for rotating root and Django device tokens after compromise.

This is a pre-Angular blocker because Angular, Django BFF tests, Rust core stand tests, and mobile/client work all need reproducible SyncServer stands.

---

## 2. Source Requirements

- `Functional and WorkLogik.md`, section I.1.1:
  - root and Django device tokens are created during bootstrap;
  - bootstrap creates/initializes the database;
  - bootstrap prints root user and Django device tokens;
  - token regeneration must be available.
- `SyncServer/AGENTS.md`:
  - SyncServer is the authoritative backend;
  - mutations go through services/repos/UoW;
  - migrations require `python -m alembic upgrade head` against a safe DB.
- Current restored file: `SyncServer/scripts/bootstrap_root.py`.

---

## 3. Current State Snapshot

The restored `scripts/bootstrap_root.py` currently:

- imports SyncServer app modules directly;
- calls `Base.metadata.create_all`;
- creates or repairs:
  - root user `root`;
  - Django device `DJANGO_WEB`;
  - uncategorized category;
- prints root and Django device tokens;
- is idempotent for duplicate root/device/category creation;
- does **not** provide explicit token rotation/recovery;
- does **not** clearly integrate with Alembic migration flow;
- has no dedicated tests proving idempotency, no-rotation-by-default, or safe recovery.

---

## 4. Architecture Boundaries

### SyncServer owns

- Root user and device records.
- Root/Django device token generation and rotation.
- Database schema migration/initialization procedure.
- Idempotency and uniqueness guarantees for system records.

### Django owns

- Storing resulting token values in `.env` or deployment secret storage via environment variables:
  - `SYNC_ROOT_USER_TOKEN`
  - `SYNC_DEVICE_TOKEN`

### Forbidden

- Do not add a public unauthenticated token recovery endpoint.
- Do not log token values in ordinary app logs.
- Do not rotate existing root/Django device tokens during normal bootstrap unless an explicit rotate command/flag is used.
- Do not make Django or Angular create SyncServer root/device rows.

---

## 5. Implementation Levels

### Level 0 — Context and policy verification

Scope:

- Re-read `Functional and WorkLogik.md` section I.1.1.
- Review current models/services for users/devices and root restrictions:
  - `app/models/user.py`
  - `app/models/device.py`
  - `app/services/admin_users_service.py`
  - `app/services/admin_devices_service.py` if present
  - `scripts/bootstrap_root.py`

Acceptance criteria:

- Executor records whether bootstrap uses Alembic, `create_all`, or both.
- Executor records token output policy: normal bootstrap vs explicit recovery/rotation.
- No application code is changed before this decision is noted in the completion report.

### Level 1 — Bootstrap script made current and safe

Required behavior:

- Keep `SyncServer/scripts/bootstrap_root.py` as the canonical script.
- Script must run from repository root and from `SyncServer/` workdir.
- Script must support a documented safe DB lifecycle:
  - prefer running Alembic migrations before creating/repairing data;
  - if `Base.metadata.create_all` remains as fallback, explain why and test it.
- Script must be idempotent:
  - second run creates no duplicates;
  - second run does not rotate tokens;
  - root user remains active/root/role `root`;
  - Django device remains active with stable `device_code`.
- Script must create/repair required system category using the existing catalog defaults.
- Script output must provide operator-friendly `.env` names:
  - `SYNC_ROOT_USER_TOKEN=...`
  - `SYNC_DEVICE_TOKEN=...`

Acceptance criteria:

- Empty safe DB can be migrated and bootstrapped.
- Re-running the script leaves the same root token and device token unless an explicit rotate flow is used.
- Script exits non-zero on unrecoverable duplicate system category or invalid DB state.

### Level 2 — Explicit root/Django device token recovery

Required behavior:

- Add an explicit local ops path for token recovery. Recommended implementation:
  - `SyncServer/scripts/rotate_tokens.py`, or
  - explicit flags on `bootstrap_root.py` such as `--rotate-root-token` and `--rotate-django-device-token`.
- The recovery path must be intentionally invoked; default bootstrap must never rotate.
- Root token rotation may remain forbidden through normal admin API. Local script recovery is acceptable because it requires DB/deployment access.
- Rotating root token must update exactly the canonical root user.
- Rotating Django device token must update exactly the canonical Django device.
- Output must clearly state which token changed and which Django env var must be updated.

Acceptance criteria:

- Root token can be rotated by local ops command.
- Django device token can be rotated by local ops command.
- Non-root users are not affected.
- Non-Django devices are not affected.
- Tests prove old token no longer authenticates after rotation if auth tests can run against the same DB.

### Level 3 — Tests

Required tests:

- Unit or script-level tests for:
  - first bootstrap creates root user;
  - first bootstrap creates Django device;
  - second bootstrap is idempotent;
  - default bootstrap does not rotate tokens;
  - explicit root rotation changes only root token;
  - explicit Django device rotation changes only Django device token.
- Integration tests against a migrated test DB for:
  - root token authenticates as root;
  - Django device token is accepted where device audit context is expected;
  - old rotated token fails after recovery if the auth route is available in test.

Acceptance criteria:

- Tests are committed near the existing SyncServer test suite.
- No test prints real token values from developer environments.

### Level 4 — Documentation and operator handoff

Required documentation updates:

- Update or create a SyncServer document explaining:
  - first-time bootstrap command;
  - idempotent re-run behavior;
  - token rotation/recovery command;
  - env var names for Django;
  - safe DB/reset warning.
- Cross-link from `SyncServer/docs/TEST_STAND_GUIDE.md` or equivalent stand guide if applicable.

Acceptance criteria:

- A new operator can initialize a clean test stand from the documented commands without reading source code.

---

## 6. Real Test Stand Requirement

### Database

- PostgreSQL test database dedicated to SyncServer.
- Lifecycle:
  1. create/drop safe test DB;
  2. run `python -m alembic upgrade head`;
  3. run bootstrap script;
  4. optionally run token rotation script;
  5. clean up DB after smoke.

### Required seed data

- Root user created by bootstrap.
- Django device created by bootstrap.
- Uncategorized category created by bootstrap.

### Services to start

- SyncServer FastAPI app for auth/health smoke after bootstrap.

### Environment variable names only

- `DATABASE_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `PYTHONPATH`
- `SYNC_SERVER_BASE_URL`

### Health checks

- SyncServer health endpoint.
- An authenticated root/admin endpoint using the newly printed root token.
- A device-aware endpoint if available.

### Smoke commands

Recommended command shapes; executors must adapt to project scripts:

```bash
python -m alembic upgrade head
python scripts/bootstrap_root.py
python scripts/bootstrap_root.py
python scripts/rotate_tokens.py --root
python scripts/rotate_tokens.py --django-device
python -m pytest tests/test_auth_smoke.py tests/test_auth_unified.py
```

### Cleanup

- Drop safe test DB or restore from disposable container volume.
- Remove any generated local `.env` fragments from test output.

---

## 7. Test Strategy Ladder

| Level | Required? | Checks |
|---|---|---|
| Static checks | Yes | `python -m compileall scripts app tests` or project equivalent; lint if configured |
| Unit tests | Yes | bootstrap/rotation idempotency with isolated DB/session fixtures |
| Component tests | Yes | service/script function tests for user/device/category creation |
| Integration tests | Yes | migrated PostgreSQL or project test DB; auth validates rotated tokens |
| Real stand smoke | Yes | clean DB bootstrap + app health/auth smoke |
| UI automation | Not applicable | No UI touched |
| User scenarios | Yes | operator initializes clean stand; operator rotates compromised root token |
| Regression pack | Yes | existing auth/admin/device tests must still pass |
| Acceptance review | Yes | evidence table reviewed by QA/verifier |

---

## 8. Acceptance Criteria

- `bootstrap_root.py` exists, is current, documented, and idempotent.
- Bootstrap creates/repairs root user, Django device, and system category.
- Bootstrap does not rotate existing tokens unless explicitly requested.
- Root token recovery exists through an intentional local ops command/flag.
- Django device token recovery exists through an intentional local ops command/flag.
- Output uses Django env var names and does not require operators to inspect DB rows manually.
- Tests cover first run, second run, and rotation scenarios.
- Stand smoke proves clean DB bootstrap works.

---

## 9. Evidence Table

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static checks |  |  |  |
| Unit/script tests |  |  |  |
| DB integration |  |  |  |
| Stand smoke |  |  |  |
| Regression auth/admin |  |  |  |
| Documentation |  |  |  |
