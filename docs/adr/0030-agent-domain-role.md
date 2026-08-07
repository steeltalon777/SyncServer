# ADR-0030: SyncServer `agent` role — server-enforced permissions for LLM client

## Status
Accepted (drafted 2026-08-07 alongside Issue #18).

## Context

Quartermaster is being integrated with a trusted LLM agent (initial:
MiniMax) that operates on behalf of the chief storekeeper. The agent
must read warehouse data, prepare catalog changes (CRUD on Items,
Categories, Units), perform catalog merges through the existing
merge endpoints, and prepare draft operations.

The agent must NOT be able to:
- submit or otherwise finalise operations;
- impersonate the chief storekeeper by sharing their token;
- bypass the catalog merge logic by direct PATCH of system fields;
- gain root / system-admin powers.

Today, the role enum is `{root, chief_storekeeper, storekeeper,
observer}` (see `SyncServer/app/models/user.py:85`,
`SyncServer/app/schemas/admin.py:12`,
`SyncServer/app/api/admin_common.py:10`).

A separate catalog approval/submission workflow is intentionally
NOT introduced: there is one chief storekeeper and one agent, and
the agent acts as the chief's trusted business agent. The
behavioural rule "PATCH/MERGE existing catalog only after an
explicit chief command" lives in the agent wrapper / system
prompt, not in the server.

## Decision

1. **New domain role `agent`.** Extend the canonical roles set with
   `agent`. The `users.role` column type is unchanged; the
   `CheckConstraint` and the Pydantic `UserRole` literal are
   widened. Existing rows are not modified. Migration lives in
   `alembic/versions/0038_add_agent_role.py`.

2. **Server is the source of truth for permissions.** No
   `agent` permission may rely on a skill / system prompt /
   client wrapper. Every guard is a server-side check inside
   `app/services/operations_policy.py`,
   `app/services/agent_policy.py`, or a route guard in
   `app/api/routes_*.py`.

3. **Catalog PATCH allow-list.** `AgentPolicy` defines
   `AGENT_ITEM_PATCH_FIELDS`, `AGENT_CATEGORY_PATCH_FIELDS`,
   `AGENT_UNIT_PATCH_FIELDS`. Service-level filters drop
   everything else, including `is_active`, `requires_review`,
   `merged_into_id`, `merged_at`, `merged_by_user_id`,
   `merge_comment`, `deleted_at`, `deleted_by_user_id`,
   `created_by_user_id`, `updated_by_user_id`. The PATCH
   endpoint surface is unchanged; the filter is applied inside
   `catalog_admin_service.update_*`.

4. **Catalog merge goes through existing endpoints only.** No
   agent-side bypass of `items/merge` and `categories/merge` via
   PATCH. The merge service is the only path that sets
   `merged_into_id` / `merged_at` / `merged_by_user_id` /
   `merge_comment`.

5. **Operations: draft only.** `agent` is added to
   `OperationsPolicy.CREATE_DRAFT_ROLES` and to `READ_ROLES`
   (for read access to draft/submitted operations; cancelled
   stays root-only as today). `require_operation_submit_permission`,
   `require_root_for_restore`, and the submitted branch of
   `require_operation_cancel_permission` return 403 for `agent`.
   `require_operation_effective_at_permission` and a new
   `require_agent_update_own_draft` allow `agent` to update
   only drafts created by that same `agent` user.

6. **No site scoping for `agent`.** `UserAccessScope` is the
   per-site mechanism for `storekeeper` / `observer`. The
   `agent` role does not need it: catalog is global, and draft
   operations do not require site-scope checks. `agent` is
   NOT added to `has_global_business_access`; the catalog-read
   global view is provided by an explicit branch in
   `routes_auth.py:auth_sites` and `routes_catalog.py`.

7. **Token separation.** `agent` is a normal `User` with its
   own `user_token` (UUID). No token aliasing, no
   impersonation, no fallback to `chief_storekeeper` token.
   `bootstrap_root.py --agent-username` is the only supported
   creation path (idempotent, optional).

8. **Audit actor is the real agent.** `record_audit_event(
   actor_user_id=...)` receives the agent's UUID. There is no
   rewrite to `chief_storekeeper`. `actor_role` is not
   snapshotted in `audit_events` (out of scope for this ADR —
   see "Consequences").

9. **Admin endpoints stay root/chief-only.** `require_admin_basic`
   is unchanged (`is_root` or `role == "chief_storekeeper"`).
   `/admin/roles` returns the extended `CANONICAL_ROLES` list
   so the agent can see its own role in the inventory.

10. **No catalog approval / submission state machine.** No
    `CatalogChangeRequest`, no `CatalogMergeRequest`, no
    `submit/approve` flow for catalog changes.

## Consequences

### Pros
- Server-side enforcement: even a malicious skill/system prompt
  cannot escalate the agent.
- Existing audit invariant `actor_user_id = real user` is
  preserved.
- Existing merge invariants in
  `catalog_admin_service.merge_items` / `merge_categories`
  (system ADJUSTMENT balance transfer, audit_event_resources
  edges, etc.) are reused.
- Role enum is a single, finite set; Pydantic literal keeps
  OpenAPI / clients honest.

### Cons
- `agent` is a new role: any code that hard-codes a list of
  roles must be updated. Mitigation: introduce role groups
  (e.g. `READ_ROLES`, `WRITE_ROLES`) consistently in policies
  rather than ad-hoc `role == "X"` checks. The new code path
  goes through `AgentPolicy` helpers, not through ad-hoc role
  comparisons.
- Cancel submitted / restore remain root-only; if a future
  requirement asks the agent to assist with corrections, this
  will need a follow-up ADR.

### Out of Scope
- `actor_role` field on `audit_events` (would require schema
  change and backfill). Issue #18 explicitly does not require
  it; query path uses join on `users.role`.
- Offline agent via `Warehouse_client_core` — separate TZ.
- Multi-tenant role scoping — separate ADR.

## Alternatives Considered

### Option 1 — Reuse `chief_storekeeper` with a "device flag"
Why not chosen: violates the explicit "no impersonation" and
"no chief rights for agent" requirements from Issue #18.

### Option 2 — Add a server-side `CatalogChangeRequest` table
Why not chosen: Issue #18 explicitly says "no separate
approval/submission workflow for catalog". The chief and the
agent are 1:1 for now; trust is implicit.

### Option 3 — Use a per-resource capability claim
Why not chosen: over-engineered for the current single-agent
case; the role + allow-list + service-level filter model
already provides defence in depth.

## Evidence

- `SyncServer/app/models/user.py:42-88` — role column and check
  constraint.
- `SyncServer/app/schemas/admin.py:12` — `UserRole` literal.
- `SyncServer/app/api/admin_common.py:10` — `CANONICAL_ROLES`.
- `SyncServer/app/services/operations_policy.py` — role groups
  and helpers.
- `SyncServer/app/services/catalog_admin_service.py` — merge
  logic and audit hooks.
- `SyncServer/app/api/routes_catalog_admin.py:39-47` — current
  catalog admin guard.
- `SyncServer/app/api/routes_auth.py` — `/auth/me`,
  `/auth/context`, `/auth/sites`.
- `SyncServer/app/api/routes_operations.py:294-402` — submit,
  cancel, restore endpoints.
- `SyncServer/docs/adr/0005-token-auth-and-site-scoped-access.md`
  — token auth model and site scopes.
- `SyncServer/docs/TZ/TZ-AGENT-ROLE-SYNCSERVER.md` — execution
  checklist and test ladder for this ADR.

## Confidence

- **Confirmed by code** — every guard described here has a
  concrete, named location in the codebase.
- **Confirmed by Issue #18** — scope, role list, forbidden
  actions, and audit requirements are explicit.
- **Pending verification** — actual behavior in stand tests
  and the per-test evidence table that the executor agent
  builds during implementation.
