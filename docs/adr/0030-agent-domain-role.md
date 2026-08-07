# ADR-0030: SyncServer domain role `agent` for LLM clients

## Status

Accepted

Decision date: 2026-08-07.
Verified against `steeltalon777/SyncServer` `dev@88458d667da3ddb97c2d2e1a59122cdefa0b9a58`.
Implementation specification: `docs/TZ/TZ-AGENT-ROLE-SYNCSERVER.md` rev.2.
Implemented: 2026-08-07 (migration `0038_add_agent_role`, `agent` in `UserRole`/`CANONICAL_ROLES`/`Identity.is_agent`, observer-parity business read, catalog create/PATCH allow-list/merge policy in `app/services/catalog_agent_policy.py`, agent own-draft operations path, agent branch in `/auth/sites` and `/auth/context`).

## Context

Quartermaster получает доверенного LLM-агента (первоначально MiniMax), который работает по поручению главного кладовщика.

Агенту нужен собственный доменный identity и прямой API-доступ к SyncServer. Skill/system prompt не должен быть security boundary: реальный набор разрешённых действий обязан обеспечивать SyncServer.

Целевые сценарии агента:

- читать обычные warehouse business data;
- анализировать каталог и находить дубли;
- создавать Item/Category/Unit;
- исправлять business-поля существующих Item/Category/Unit;
- выполнять штатный merge Item/Category после команды кладовщика;
- создавать и редактировать draft operations для последующего submit человеком.

Agent не должен самостоятельно менять подтверждённое складское состояние и не должен получать system-admin authority.

При текущей организации один главный кладовщик работает с одним доверенным агентом. Отдельный catalog approval/submission workflow создаст дополнительную state machine без достаточной продуктовой пользы. Поэтому команда человека на PATCH/MERGE остаётся behavioural rule agent wrapper, а не новой серверной сущностью.

## Decision

### 1. Add a fifth domain role `agent`

Canonical roles become:

```text
root
chief_storekeeper
storekeeper
observer
agent
```

`users.role` remains `String(32)`. DB check constraint and Pydantic `UserRole` literal are widened.

`agent` is a normal non-root `User` with its own UUID `user_token`.

### 2. SyncServer remains the permission authority

All effective restrictions are enforced on the server.

Agent wrapper/system prompt may impose stricter behavioural rules, but those rules are not trusted for authorization.

In particular, the behavioural rule:

> PATCH/MERGE an existing catalog entity only after an explicit chief-storekeeper command

lives outside SyncServer and does not introduce an approval entity or approval state machine.

### 3. Agent is not global business authority

Do not add agent to:

```python
Identity.has_global_business_access
```

That helper remains equivalent to:

```text
is_root OR role == chief_storekeeper
```

Agent receives explicit capabilities for read/catalog/draft preparation only.

### 4. Business read follows observer parity

For normal business-read surfaces:

```text
agent read >= observer read
```

Agent can read catalog, sites, balances, operations and other ordinary business data available to observer.

Existing special restrictions remain special restrictions. For example cancelled operations remain root-only if that is the current policy.

This rule does not automatically open admin, device-sync, machine-integration or other technical endpoints.

### 5. Catalog create is allowed

Agent may create:

- Item;
- Category;
- Unit.

Existing create schemas and CatalogAdminService validations are reused. No new catalog workflow is introduced.

### 6. Catalog PATCH uses a server-side allow-list

Agent may PATCH existing catalog entities only through the existing update services.

Allowed Item fields:

```text
name
sku
description
category_id
unit_id
hashtags
```

Allowed Category fields:

```text
name
code
parent_id
sort_order
```

Allowed Unit fields:

```text
name
symbol
sort_order
```

`is_active` is not editable by agent on existing entities because it changes lifecycle state.

System/merge/delete fields are not added to public update schemas. If a known PATCH field is outside the agent allow-list, the server rejects the request rather than silently applying a partial payload.

### 7. Catalog merge reuses the existing merge domain path

Agent may call the existing Item and Category merge endpoints/services.

Only those services may perform merge semantics. Agent receives no direct path to set `merged_into_id`, `merged_at`, `merged_by_user_id`, delete markers or equivalent internal state.

Existing merge invariants, including inventory/balance/audit behavior, remain authoritative.

### 8. Batch/delete/deactivate stay outside agent v1

Agent does not receive:

- catalog DELETE;
- deactivation of an existing entity;
- `/catalog/admin/batch`.

The batch endpoint mixes create/update/deactivate/delete/merge and unnecessarily increases the authorization surface. Required agent use cases are already covered by specialized endpoints.

Bulk create is not required by this ADR and may remain chief/root-only in v1.

### 9. Operations are draft-preparation only

Agent is added to operation READ and CREATE_DRAFT role groups.

Agent may:

- create draft operations;
- create source-document drafts;
- PATCH only drafts created by the same agent-user;
- change fields already present in the existing `OperationUpdate` contract, subject to existing domain validation;
- change `effective_at` of its own draft;
- cancel its own draft.

Agent is not given site operate authority merely to edit its own draft. Routes that currently call `require_operate_site` before creator/workflow checks need an explicit own-agent-draft path.

The agent-specific authorization layer must not duplicate the existing structural/business validation already implemented by `OperationsService.update_operation`.

### 10. Agent cannot create warehouse effects

Agent may not:

- submit/finalize an operation;
- accept incoming lines;
- cancel a submitted operation;
- restore a cancelled operation;
- submit corrections;
- resolve lost assets;
- moderate legacy temporary items;
- use any other path that creates or finalizes warehouse balance effects.

`WRITE_ROLES`, acceptance authority and root/chief checks are not widened for agent.

### 11. Site scopes are not agent authority

`UserAccessScope` remains the scoped mechanism for human scoped roles.

Agent's global business read and catalog access are explicit role capabilities. Agent does not become `has_global_business_access`, and `can_operate` remains false for agent in auth/site permission summaries.

Draft creation/editing is allowed because drafts have no warehouse effect and are authorized by role + ownership, not by site-operation authority.

### 12. Provisioning uses existing user flows

No `bootstrap_root.py --agent-*` extension is introduced.

Agent-user is created through existing root-authorized mechanisms after `UserRole` accepts `agent`:

- `/auth/sync-user`; or
- `/admin/users`.

Existing token management handles the agent as a normal non-root user.

### 13. No token impersonation

Agent requests always use the agent's own `X-User-Token`.

There is no alias, fallback or token substitution to a `chief_storekeeper` token.

### 14. Audit records the real actor

Existing audit infrastructure continues to receive:

```text
actor_user_id = agent user UUID
```

No event is rewritten as if the chief storekeeper performed it.

Current `audit_events` does not snapshot `actor_role`; adding such a column is outside this ADR. Role can be resolved through the actor user relation when required.

### 15. `/admin/roles` remains an admin endpoint

`CANONICAL_ROLES` includes `agent`, so authorized admin clients can enumerate it.

The endpoint itself remains protected by the existing admin guard. Agent does not need `/admin/roles` access because its own role is available through `/auth/me` and `/auth/context`.

### 16. No catalog approval state machine

Do not add:

- `CatalogChangeRequest`;
- `CatalogMergeRequest`;
- `CatalogApproval`;
- catalog `submit/approve` transitions.

If the trust model changes later (multiple agents, multiple approvers, autonomous agents, external tenants), this decision can be revisited in a new ADR.

## Consequences

### Positive

- SyncServer, not an LLM prompt, remains the security boundary.
- The agent can perform useful catalog work without receiving chief/root authority.
- Human confirmation can remain a natural-language UX rule without adding a second workflow engine.
- Existing merge and operation domain services are reused.
- Draft preparation is useful but cannot directly change stock.
- Audit attribution remains truthful because agent uses its own identity.
- Excluding batch/delete/deactivate keeps the first implementation surface small.

### Negative / trade-offs

- Adding a fifth role requires auditing hard-coded role sets across the repository.
- Agent needs explicit branches in auth/read/draft policies instead of being folded into `has_global_business_access`.
- Agent-created draft cancellation/editing needs route changes because current routes conflate site operate authority with draft ownership.
- If a future agent must autonomously submit operations, the current role is intentionally insufficient and a separate architectural decision is required.

## Alternatives considered

### A. Give the agent a `chief_storekeeper` token

Rejected. It destroys actor attribution and gives the LLM authority far beyond its intended role.

### B. Token substitution in the wrapper after a human command

Rejected. SyncServer would observe the human as actor although the API action was executed by the agent, and compromise of the wrapper would expose chief authority.

### C. Server-side catalog approval requests

Rejected for the current one-chief/one-agent trust model. It adds persistence, states, endpoints, UI and recovery rules for a workflow that is not currently required.

### D. Per-resource capability grants

Rejected for v1 as unnecessary complexity. A finite role plus narrow action/field policies satisfies current requirements.

### E. Let agent use `/catalog/admin/batch` with per-change filtering

Rejected for v1. Batch mixes safe and lifecycle-changing actions and offers no unique capability required by Issue #18.

### F. Add agent creation to bootstrap

Rejected. Existing root-only user provisioning already creates non-root roles and generates tokens once the enum is widened. Bootstrap should remain responsible for root/system seed data.

## Implementation constraints

- Re-check current Alembic head before creating the migration.
- Do not silently downgrade existing agent-users to observer in Alembic downgrade; fail with an explicit operator action requirement if agent rows exist.
- Do not silently drop forbidden PATCH fields for agent.
- Do not add agent to `WRITE_ROLES`, `has_global_business_access`, acceptance permissions or admin guards.
- Do not create Warehouse_web-specific logic solely for agent identity.
- Perform a repository-wide role audit; add agent only to intended business-read and draft-preparation paths.

## Evidence from verified code snapshot

At `dev@88458d6`:

- `app/models/user.py` has four-role `ck_users_role`;
- `app/schemas/admin.py` has four-role `UserRole`;
- `app/api/admin_common.py` has four-role `CANONICAL_ROLES` and root/chief `require_admin_basic`;
- `app/core/identity.py` defines `has_global_business_access` as root/chief;
- `app/services/operations_policy.py` separates `READ_ROLES`, `WRITE_ROLES`, and `CREATE_DRAFT_ROLES`;
- `app/api/routes_operations.py` currently requires site operate permission before PATCH/cancel, which is the main draft-owner integration point for agent;
- `app/services/operations_service.py` already enforces draft workflow and operation update invariants;
- `app/schemas/catalog.py` exposes `hashtags` and `is_active` in Item PATCH but does not expose merge/system fields;
- `app/services/catalog_admin_service.py` already records catalog update diffs and owns merge logic;
- `app/api/routes_admin.py` keeps `/admin/roles` behind `require_admin_basic`;
- `app/services/admin_users_service.py` already supports creation of any non-root role accepted by `UserRole`;
- current migration head is `0037_audit_item_effects_effective_at` on the verified snapshot.

## Follow-up boundary

Agent wrapper configuration must switch to the agent's own token and retain the behavioural explicit-command rule for existing-catalog PATCH/MERGE. That client configuration is separate from SyncServer authorization and must not be used as evidence that server permissions are safe.
