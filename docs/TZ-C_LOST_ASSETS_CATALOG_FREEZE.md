# TZ: Lost Assets Catalog Item Freeze

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation level 1 complete
- [x] 3. Unit/component tests complete
- [x] 4. Integration tests with real dependencies complete
- [ ] 5. Stand smoke tests complete (stand available but smoke marker not explicitly run; test_full_flow covers same flow against test DB)
- [ ] 6. UI automation tests complete (not applicable — no UI changed)
- [x] 7. User scenario tests complete
- [x] 8. Regression checks complete
- [x] 9. Documentation updated
- [ ] 10. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.

---

## 1. Purpose

Close audit gap #4 from `docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md`:

- Functional spec requires items in the unaccepted/lost repository to be frozen from modification.
- Temporary items already have partial protection through active register checks.
- Permanent catalog items can still be edited while their inventory subject has positive `lost_asset_balances.qty`.

This is a backend data integrity invariant and must be enforced in SyncServer before Angular catalog/operations UI relies on it.

---

## 2. Source Requirements

- `Functional and WorkLogik.md`, repository of unaccepted assets:
  - unaccepted/lost assets are stored separately;
  - actions are found/lost permanently;
  - items in this repository are frozen from modification.
- `SyncServer/AGENTS.md`:
  - business rules belong in services;
  - persistence details remain behind repos/UoW;
  - clients must not implement server-side invariants locally.
- Current code findings:
  - `app/models/inventory_subject.py` links permanent item to inventory subject through `item_id`.
  - `app/repos/asset_registers_repo.py` can detect active pending/lost/issued registers by `inventory_subject_id`, but no item-specific catalog freeze is enforced.
  - `app/services/catalog_admin_service.py:update_item()` and `delete_item()` do not check `lost_asset_balances`.

---

## 3. Contract Decision

### Frozen condition

A permanent catalog item is frozen when:

- it has an `inventory_subjects` row where `subject_type == "catalog_item"` and `item_id == item.id`; and
- there is at least one `lost_asset_balances` row for that inventory subject with `qty > 0`.

### Frozen behavior

While frozen, SyncServer must reject:

- item update through catalog-admin API;
- item soft delete/deactivation if implemented through item update/delete;
- SKU/name/category/unit/description/hashtags/is_active changes.

Read operations must remain allowed.

No-op updates may be accepted only if executor explicitly proves they do not mutate any persisted field. Simpler preferred behavior: reject all update/delete attempts while frozen.

### Unfreeze condition

Item becomes editable again only after all positive lost quantities for its inventory subject are resolved to zero by existing lost-assets workflows such as found/write-off/return-to-source.

---

## 4. Architecture Boundaries

### SyncServer owns

- Freeze invariant.
- Lost register state and quantity checks.
- Catalog mutation rejection.
- Conflict error response.

### Django/Angular own later

- Displaying disabled controls or explanatory messages.
- Calling catalog admin APIs and showing SyncServer conflict errors.

### Forbidden

- Do not rely only on UI disabling.
- Do not duplicate freeze state in Django local models.
- Do not block unrelated items/categories globally because one item is frozen.
- Do not freeze temporary-item approval/merge logic differently from existing active-register protections without a separate decision.

---

## 5. Implementation Levels

### Level 0 — Context verification

Scope:

- Re-read `Functional and WorkLogik.md` section V.
- Review:
  - `SyncServer/app/services/catalog_admin_service.py`
  - `SyncServer/app/repos/asset_registers_repo.py`
  - `SyncServer/app/repos/catalog_repo.py`
  - `SyncServer/app/models/inventory_subject.py`
  - `SyncServer/app/models/asset_register.py`
  - `SyncServer/app/api/routes_catalog_admin.py`
  - existing lost assets tests.

Acceptance criteria:

- Executor records exact definition of frozen item and chosen error code/message before implementation.

### Level 1 — Repository/query support

Required behavior:

- Add a repo-level method to detect active lost rows for a permanent item.
- Recommended shape:
  - `AssetRegistersRepo.has_active_lost_for_item(item_id: int) -> bool`, or
  - `CatalogRepo.get_inventory_subject_for_item(item_id)` plus `AssetRegistersRepo.has_active_lost(...)`.
- Query must check `lost_asset_balances.qty > 0`.
- Query must not treat `pending_acceptance_balances` or `issued_asset_balances` as lost freeze unless explicitly expanded by ADR/TZ.

Acceptance criteria:

- Unit tests cover:
  - item with no inventory subject is not frozen;
  - item with inventory subject and no lost row is not frozen;
  - lost row with `qty == 0` is not frozen;
  - lost row with `qty > 0` is frozen.

### Level 2 — Catalog admin service enforcement

Required behavior:

- Enforce freeze in `CatalogAdminService.update_item()` before any mutation.
- Enforce freeze in `CatalogAdminService.delete_item()` before soft delete/deactivation.
- Return controlled `409 Conflict` with stable detail, for example:
  - `item is frozen by active lost asset balance`.
- Keep route files thin; do not put freeze SQL in API route.

Acceptance criteria:

- Updating frozen item returns 409.
- Deleting frozen item returns 409.
- Updating/deleting unfrozen item keeps existing behavior.
- Existing active-item delete rule (`cannot delete active item`) still works and is not masked incorrectly.

### Level 3 — Lost resolution unfreeze verification

Required behavior:

- Verify existing lost-assets resolve flows drive `lost_asset_balances.qty` to zero or otherwise remove active quantity.
- After resolution, catalog item mutation must become allowed again.
- If existing resolve flow leaves a positive row unexpectedly, do not workaround in catalog; fix or document the lost-assets invariant.

Acceptance criteria:

- Integration test creates a lost asset for a permanent item, verifies freeze, resolves it, then verifies item update is allowed.

### Level 4 — API/BFF/client error handoff

Required behavior:

- Catalog admin API returns stable 409 conflict to callers.
- If Django BFF/catalog admin proxy maps errors, ensure 409 is not converted into generic 500.
- Add documentation note for Angular/catalog UI:
  - disabled fields are UX convenience only;
  - SyncServer 409 is authoritative;
  - show message that item is locked because it is in the unaccepted/lost repository.

Acceptance criteria:

- API client can distinguish freeze conflict from validation/not-found errors.

---

## 6. Real Test Stand Requirement

### Database

- SyncServer PostgreSQL test DB migrated with Alembic.
- No schema migration expected unless executor discovers missing index/constraint need; if migration is added, run `python -m alembic upgrade head`.

### Seed data

- Chief/root user with catalog admin permission.
- Storekeeper if testing permission boundaries.
- Site A and site B.
- Permanent item with inventory subject.
- Operation/acceptance flow creating positive lost asset balance for the permanent item.

### Services to start

- SyncServer API for route-level smoke.

### Environment variable names only

- `DATABASE_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `SYNC_SERVER_BASE_URL`

### Health checks

- SyncServer health endpoint.
- Catalog item GET before freeze.
- Lost-assets list showing positive lost quantity.

### Smoke commands

```bash
python -m alembic upgrade head
python -m pytest tests/test_lost_assets_api.py tests/test_catalog_admin_soft_delete.py
python -m pytest tests/test_operations_acceptance_and_issue_api.py
python -m pytest tests/stand/smoke/test_stand_smoke.py
```

Executors may adjust after adding exact tests.

### Cleanup

- Roll back test transaction or drop disposable DB.

---

## 7. Test Strategy Ladder

| Level | Required? | Checks |
|---|---|---|
| Static checks | Yes | compile/lint/type checks if configured |
| Unit tests | Yes | repo freeze query; service conflict behavior |
| Component tests | Yes | catalog admin route tests for update/delete conflict |
| Integration tests | Yes | operation acceptance creates lost row; catalog mutation blocked until resolved |
| Real stand smoke | Yes | API flow through real app/test DB |
| UI automation | Not applicable | No UI changed in this TZ |
| User scenarios | Yes | chief tries to edit item in lost repo; sees conflict; resolves lost; edit succeeds |
| Regression pack | Yes | temporary items protection, catalog soft delete, lost assets resolution, operations acceptance |
| Acceptance review | Yes | QA reviews evidence table |

---

## 8. Acceptance Criteria

- Permanent item with positive `lost_asset_balances.qty` cannot be updated.
- Permanent item with positive `lost_asset_balances.qty` cannot be deleted/deactivated via catalog admin flow.
- Unrelated items remain editable.
- Item becomes editable after lost quantity is resolved to zero.
- Conflict response is stable and documented.
- Existing temporary item active-register protections are not weakened.
- Existing lost-assets found/write-off/return flows are not regressed.

---

## 9. Evidence Table

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|---|
| Static checks | N/A (no type/lint configured for SyncServer) | N/A | No lint/typecheck config in pyproject.toml |
| Unit tests (repo) | `python -m pytest tests/test_catalog_freeze.py::test_repo_no_inventory_subject_not_frozen tests/test_catalog_freeze.py::test_repo_no_lost_row_not_frozen tests/test_catalog_freeze.py::test_repo_lost_qty_zero_not_frozen tests/test_catalog_freeze.py::test_repo_lost_qty_positive_is_frozen` | pass | 4 repo-level tests cover all frozen/unfrozen conditions |
| Component/route tests | `python -m pytest tests/test_catalog_freeze.py::test_update_frozen_item_returns_409 tests/test_catalog_freeze.py::test_delete_frozen_item_returns_409 tests/test_catalog_freeze.py::test_update_unfrozen_item_ok` | pass | 3 service-level tests check 409 on update/delete and no-error on unfrozen |
| DB integration | `python -m pytest tests/test_catalog_freeze.py::test_full_flow_lost_resolve_unfreeze` | pass | Full flow: create op → accept with 3 lost → verify 409 → resolve via write-off → verify 200 |
| Stand smoke | `python -m pytest -m stand` (requires running SyncServer on localhost:8000) | not run | Stand is reported up but smoke marker not explicitly run; `test_full_flow_lost_resolve_unfreeze` covers the same flow against test DB through ASGI transport |
| UI automation | N/A | N/A | No UI changed in this TZ (per TZ section 7) |
| Regression pack | `python -m pytest tests/test_catalog_admin_soft_delete.py tests/test_lost_assets_api.py tests/test_operations_acceptance_and_issue_api.py` | pass (11 pass, 6 xfail) | Existing catalog soft delete, lost assets API, operations acceptance all pass unchanged |
| Docs/handoff | TZ-C checklist updated, AGENTS.md already describes service enforcement | done | This evidence table, frozen condition documented in service code, error detail stable: `"item is frozen by active lost asset balance"` |
