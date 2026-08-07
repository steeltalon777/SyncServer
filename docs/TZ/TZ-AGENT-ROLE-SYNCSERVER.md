# TZ: SyncServer — доменная роль `agent` для LLM

> Revision: 2 — executor-ready
> Проверено по `steeltalon777/SyncServer`, ветка `dev`, commit `88458d667da3ddb97c2d2e1a59122cdefa0b9a58` (`3.3 pre ready`), 2026-08-07.
> Источник продуктового требования: `steeltalon777/warehouse_solution-#18`.
> Архитектурное решение: `docs/adr/0030-agent-domain-role.md`.

## 0. Executive summary

Добавить в SyncServer пятую доменную роль `agent` для доверенного LLM-агента главного кладовщика.

Ключевой принцип:

- SyncServer является единственной границей реальных полномочий;
- agent работает только под собственным `X-User-Token`;
- agent имеет широкий read-доступ к бизнес-данным;
- agent может создавать и изменять каталог в ограниченном сервером наборе действий;
- agent может создавать и редактировать только собственные `draft`-операции;
- agent не может `submit`-ить операции и не может самостоятельно изменить подтверждённое складское состояние;
- отдельный catalog approval/submit workflow не вводится;
- токен `chief_storekeeper` агенту не передаётся и не подменяется.

Поведенческое правило «PATCH/MERGE существующего каталога только после явной команды кладовщика» остаётся в agent wrapper/system prompt. Это UX/behaviour rule, а не security boundary SyncServer.

---

## Execution checklist

- [ ] 0. Context verified against commit `88458d6`
- [ ] 1. ADR-0030 принят как архитектурная граница
- [ ] 2. Role enum + DB constraint + migration реализованы
- [ ] 3. Read permissions для `agent` реализованы и repository-wide role audit выполнен
- [ ] 4. Catalog create/PATCH/merge permissions реализованы
- [ ] 5. Draft operation create/PATCH/cancel-own-draft реализованы
- [ ] 6. Submit/admin/lifecycle negative guards подтверждены тестами
- [ ] 7. Audit actor и catalog change payload подтверждены тестами
- [ ] 8. Integration + stand smoke пройдены
- [ ] 9. Regression suite существующих ролей пройдена
- [ ] 10. Документация обновлена
- [ ] 11. Final acceptance review завершён

Пункт отмечается только после фактической проверки. Если проверка неприменима или стенд недоступен, это явно фиксируется рядом с пунктом.

---

## 1. Scope

### 1.1. Разрешено роли `agent`

#### Business read

`agent` должен иметь как минимум тот же read-доступ к обычным бизнес-данным, который сейчас имеет `observer`.

Обязательные поверхности:

- каталог Items / Categories / Units;
- дерево и browse/read catalog endpoints;
- Sites как бизнес-справочник;
- balances;
- operations, кроме текущих root-only ограничений на cancelled;
- бизнес-read endpoints основного UI, если они уже разрешены `observer`.

Правило для исполнителя: выполнить repository-wide audit всех hard-coded role lists/comparisons. Если endpoint является обычным бизнес-read и сейчас разрешён `observer`, `agent` также должен получить read. Технические, machine/sync и admin endpoints автоматически не расширять.

#### Catalog mutations

Разрешить через существующие специализированные API/service paths:

- `POST /api/v1/catalog/admin/items`;
- `POST /api/v1/catalog/admin/categories`;
- `POST /api/v1/catalog/admin/units`;
- `PATCH /api/v1/catalog/admin/items/{id}` с allow-list полей;
- `PATCH /api/v1/catalog/admin/categories/{id}` с allow-list полей;
- `PATCH /api/v1/catalog/admin/units/{id}` с allow-list полей;
- `POST /api/v1/catalog/admin/items/merge`;
- `POST /api/v1/catalog/admin/categories/merge`.

Допускается открыть для agent GET list/detail endpoints внутри `/catalog/admin/*`, если они нужны для чтения inactive/deleted сущностей. Они read-only и не дают lifecycle authority.

#### Draft operations

Разрешить:

- `POST /api/v1/operations`;
- `POST /api/v1/operations/from-source-document`;
- `PATCH /api/v1/operations/{id}` только для draft, созданного этим же agent-user;
- `PATCH /api/v1/operations/{id}/effective-at` только для собственного draft;
- `POST /api/v1/operations/{id}/cancel` только для собственного draft.

PATCH собственного draft использует существующий `OperationUpdate` contract. Не вводить отдельное искусственное ограничение «agent не меняет operation_type/source_site_id/destination_site_id»: draft не имеет складского эффекта, а текущий `OperationsService.update_operation` уже валидирует допустимые комбинации типа и реквизитов. Agent не получает права обходить эти проверки.

### 1.2. Запрещено роли `agent`

- submit/finalize операции;
- acceptance (`accept-lines`) и другие действия, создающие/подтверждающие складской эффект;
- cancel submitted operation;
- restore cancelled operation;
- corrections submit;
- изменение submitted operation;
- temporary item moderation;
- lost asset resolution;
- удаление/деактивация существующих Item/Category/Unit;
- управление users;
- user token read/rotation;
- управление devices и device tokens;
- создание/изменение sites;
- access scopes;
- admin audit/configuration;
- root/system-admin bypass;
- token impersonation;
- прямое изменение merge/system полей в обход merge service.

`DELETE /operations/{id}` в первой реализации роли agent не открывать. Это не требуется Issue #18 и не нужно для основного сценария «подготовил draft → chief submit».

### 1.3. Явно out of scope

- `CatalogChangeRequest`, `CatalogMergeRequest`, `CatalogApproval`;
- catalog submit/approve state machine;
- capability token/grant framework;
- impersonation chief token;
- отдельная agent-device модель;
- `actor_role` snapshot column в audit;
- offline-agent через client core;
- новые batch semantics;
- изменения `bootstrap_root.py` и `rotate_tokens.py`;
- изменения Warehouse_web/BFF только ради роли agent.

---

## 2. Verified current state

Проверено на `dev@88458d6`.

### 2.1. Role model

Текущее состояние:

- `app/models/user.py`: `role` — `String(32)` с DB `CheckConstraint` на `root/chief_storekeeper/storekeeper/observer`;
- `app/schemas/admin.py`: `UserRole = Literal["root", "chief_storekeeper", "storekeeper", "observer"]`;
- `app/api/admin_common.py`: `CANONICAL_ROLES` содержит четыре роли;
- `Identity.has_global_business_access` возвращает `is_root or role == "chief_storekeeper"`.

После изменения `agent` добавляется в enum/constraint, но **не** добавляется в `has_global_business_access`.

### 2.2. Existing user creation path

Новый bootstrap path не нужен.

После расширения `UserRole` существующие root-only потоки уже подходят для создания agent-user:

- `POST /api/v1/auth/sync-user`;
- `POST /api/v1/admin/users`.

`AdminUsersService.validate_user_role_payload` запрещает только создание root через admin API, поэтому `role=agent, is_root=false` естественно вписывается в текущий flow.

Токен agent-user генерируется штатной моделью `User.user_token`. Существующий root-only token management применяется к нему как к обычному non-root user.

### 2.3. Operations policy

В `app/services/operations_policy.py`:

```python
READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
WRITE_ROLES = {"chief_storekeeper", "storekeeper"}
CREATE_DRAFT_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
```

`require_operation_submit_permission` уже fail-closed для любой роли кроме root/chief/storekeeper.

`require_operation_cancel_permission` уже разрешает cancel draft его creator и запрещает submitted всем, кроме root.

`require_operation_effective_at_permission` уже разрешает изменение собственного draft.

Главный технический разрыв: route `PATCH /operations/{id}` и `POST /operations/{id}/cancel` вызывают `require_operate_site` раньше owner/cancel policy. Поэтому agent, несмотря на ownership draft, сейчас будет остановлен 403. Для agent нужен отдельный own-draft path без выдачи site operate permission.

### 2.4. Operation service

`OperationsService.update_operation` уже:

- требует существование operation;
- требует `draft` через workflow policy;
- валидирует MOVE source/destination;
- валидирует смену operation type;
- валидирует строки;
- пишет `operation.update` audit с реальным `actor_user_id`.

Не дублировать эти бизнес-инварианты в agent policy.

### 2.5. Catalog schemas/service

Текущий `ItemUpdateRequest` содержит:

- `sku`;
- `name`;
- `category_id`;
- `unit_id`;
- `description`;
- `hashtags`;
- `is_active`.

`requires_review` и merge/system fields в `ItemUpdateRequest` **не входят**. Не описывать их как существующие PATCH-поля.

`CategoryUpdateRequest` содержит `name/code/parent_id/sort_order/is_active`.

`UnitUpdateRequest` содержит `name/symbol/sort_order/is_active`.

`CatalogAdminService.update_*` уже пишет audit `changes={old,new}`. `merge_items` и `merge_categories` являются существующей доменной merge-логикой и должны переиспользоваться без копирования.

### 2.6. `/admin/roles`

`GET /api/v1/admin/roles` сейчас защищён `require_admin_basic`, то есть доступен root/chief, а не обычным пользователям.

Требование: response должен содержать `agent` для админского UI. **Самому agent открывать `/admin/roles` не нужно.** Собственную роль он видит через `/auth/me` и `/auth/context`.

### 2.7. Read role sets

Как минимум отдельные hard-coded read role sets подтверждены в:

- `app/services/operations_policy.py`;
- `app/api/routes_catalog.py`;
- `app/api/routes_balances.py`.

Исполнитель обязан сделать repo-wide поиск `root`, `chief_storekeeper`, `storekeeper`, `observer`, `READ_ROLES`, `ALLOWED_*_ROLES` и классифицировать каждое совпадение. Не добавлять `agent` механически во все наборы.

---

## 3. Domain model and migration

### 3.1. Role enum

Обновить:

```python
UserRole = Literal[
    "root",
    "chief_storekeeper",
    "storekeeper",
    "observer",
    "agent",
]
```

`CANONICAL_ROLES`:

```python
[
    "root",
    "chief_storekeeper",
    "storekeeper",
    "observer",
    "agent",
]
```

`User.role` comment также привести к пяти ролям.

### 3.2. Alembic

Текущий head на проверенном commit: `0037_audit_item_effects_effective_at`.

Создать следующую ревизию, если head не изменился к моменту исполнения. Исполнитель **обязан повторно проверить Alembic head перед созданием файла**, а не слепо использовать номер из TZ.

Upgrade:

1. drop `ck_users_role`;
2. recreate constraint с `agent`.

Existing rows не изменять.

Downgrade не должен молча превращать agent-users в observer. Перед сужением constraint:

- проверить наличие `users.role='agent'`;
- если такие строки есть — завершить downgrade явной ошибкой с инструкцией оператору сначала вручную переназначить роль;
- если agent rows нет — вернуть старый constraint.

Так rollback не меняет доменную идентичность пользователей скрыто.

### 3.3. Identity

Допустимо добавить convenience property:

```python
@property
def is_agent(self) -> bool:
    return self.user is not None and self.user.role == "agent"
```

Это не является новым authority flag.

Не менять:

```python
has_global_business_access == (is_root or role == "chief_storekeeper")
```

---

## 4. Read permissions

### 4.1. Принцип

Для обычного business read:

```text
agent read >= observer read
```

Исключения сохраняют существующую политику:

- cancelled operations остаются root-only;
- admin endpoints остаются admin-only;
- device sync / machine integration / технические endpoints не открываются только из-за появления роли agent.

### 4.2. Обязательные изменения

Добавить `agent`:

- в `OperationsPolicy.READ_ROLES`;
- в `routes_catalog.py::ALLOWED_CATALOG_READ_ROLES`;
- в `routes_balances.py::READ_ROLES`.

После repo-wide audit добавить agent в аналогичные **business-read** sets, где сейчас присутствует observer.

### 4.3. Sites/auth context

Agent не использует `UserAccessScope` для глобального business read и draft preparation.

`GET /auth/sites` для agent должен вернуть активные sites с permissions:

```json
{
  "can_view": true,
  "can_operate": false,
  "can_manage_catalog": true
}
```

`can_operate=false` важно: agent не имеет submit/site-operation authority.

`GET /auth/context`:

```json
{
  "can_read_operations": true,
  "can_create_operations": true,
  "can_read_balances": true,
  "can_manage_catalog": true,
  "can_manage_root_admin": false,
  "is_root": false
}
```

`can_create_operations=true` здесь означает создание draft, а не submit.

Предпочтительно реализовать agent branch централизованно в `AccessService.get_user_permissions_uuid` и auth sites/context logic, не добавляя agent в global-business helper.

---

## 5. Catalog authorization

### 5.1. Guard model

Сохранить существующий `_require_catalog_admin` для root/chief-only действий.

Добавить небольшой server-side policy/helper для разрешённых agent catalog действий. Название не принципиально (`AgentPolicy`, `CatalogAgentPolicy`, `CatalogPermissionsPolicy`), но правила должны быть централизованы, а routes не должны содержать россыпь ad-hoc сравнений ролей.

Policy не «фильтрует и молча выбрасывает» запрещённые поля. Если agent прислал известное PATCH-поле вне allow-list, запрос должен быть отклонён 403 до вызова mutation service.

### 5.2. PATCH allow-list

#### Item

```text
name
sku
description
category_id
unit_id
hashtags
```

`hashtags` является обычным business-полем текущего `ItemUpdateRequest` и должно быть доступно agent.

Запрещённое существующее PATCH-поле:

```text
is_active
```

Merge/system fields (`merged_into_id`, `merged_at`, `deleted_at` и т.д.) текущим `ItemUpdateRequest` не экспонируются и не должны добавляться.

#### Category

```text
name
code
parent_id
sort_order
```

Запрещено:

```text
is_active
```

#### Unit

```text
name
symbol
sort_order
```

Запрещено:

```text
is_active
```

### 5.3. Create

Agent использует существующие create schemas без отдельного agent DTO:

- `ItemCreateRequest`;
- `CategoryCreateRequest`;
- `UnitCreateRequest`.

Не вводить отдельную approval/state machine.

Все текущие CatalogAdminService validations сохраняются. `requires_review` на create Item остаётся частью существующего create contract; эта TZ не добавляет agent право модерировать review items.

### 5.4. Merge

Разрешить agent только через:

- `CatalogAdminService.merge_items`;
- `CatalogAdminService.merge_categories`.

Не дублировать merge code и не разрешать прямое выставление merge fields.

Все текущие freeze/balance/audit/inventory-subject/ADJUSTMENT invariants merge должны пройти существующие regression tests плюс agent-specific tests.

### 5.5. Catalog endpoints matrix

| Endpoint class | agent |
|---|---|
| primary `/catalog/*` read | YES |
| `/catalog/read/*` browse | YES |
| `/catalog/admin/*` GET list/detail | MAY/YES, read-only |
| POST item/category/unit | YES |
| PATCH item/category/unit | YES, allow-list |
| item/category merge | YES |
| DELETE item/category/unit | NO |
| deactivate existing entity | NO |
| `/catalog/admin/batch` | NO in v1 |
| bulk create | NO in v1 unless executor proves required by current agent client |

`/catalog/admin/batch` намеренно остаётся root/chief-only: он смешивает create/update/deactivate/delete/merge и не нужен для выполнения Issue #18. Agent может выполнить требуемые операции через специализированные endpoints. Это уменьшает authz surface и количество новых веток.

---

## 6. Operations authorization

### 6.1. Role groups

Изменить:

```python
READ_ROLES = {"chief_storekeeper", "storekeeper", "observer", "agent"}
CREATE_DRAFT_ROLES = {"chief_storekeeper", "storekeeper", "observer", "agent"}
```

Не менять:

```python
WRITE_ROLES = {"chief_storekeeper", "storekeeper"}
TEMPORARY_ITEM_CREATE_ROLES = {"chief_storekeeper", "storekeeper"}
```

Agent не получает site operate permission.

### 6.2. Create draft

`require_create_draft` уже не проверяет scopes. После добавления роли agent создание draft работает через существующий flow.

Если `OperationCreate.lines` содержит `temporary_item`, `require_temporary_item_create` должен вернуть agent 403. Agent имеет отдельное право создавать постоянный catalog Item и не должен получать legacy temporary-item authority.

### 6.3. PATCH own draft

Текущий route сначала вызывает `require_operate_site`, из-за чего agent не сможет PATCH собственного draft.

Добавить явный own-draft auth path:

```text
if identity.role == "agent":
    require operation.status == draft
    require operation.created_by_user_id == identity.user_id
else:
    existing require_operate_site + owner/supervisor flow
```

Workflow/business validation остаётся в `OperationsService.update_operation`.

Agent может использовать весь существующий `OperationUpdate` contract для собственного draft. Не создавать agent-specific урезанный contract.

Agent не может добавлять `temporary_item` lines: существующий `require_temporary_item_create` остаётся обязательным.

### 6.4. MOVE draft

Не использовать `require_move_access` как auth gate для agent-owned draft, потому что этот helper включает `require_operate_site` и тем самым выдаёт/требует site-operation semantics.

Для agent-owned draft структурные MOVE invariants проверяет `OperationsService.update_operation`:

- source/destination required;
- source != destination;
- operation `site_id` соответствует source;
- referenced sites exist там, где это уже проверяется текущим service flow.

Если executor вынесет structural validation в отдельный helper, этот helper не должен выдавать agent право submit/operate.

### 6.5. effective_at

После добавления agent в READ_ROLES существующий `require_operation_effective_at_permission` уже корректно разрешает изменение `effective_at` creator'у draft.

### 6.6. Cancel own draft

Для `POST /operations/{id}/cancel` agent-owned draft должен быть разрешён.

Как и PATCH, route не должен сначала требовать `require_operate_site` для agent. После bypass site-operate guard использовать существующий `require_operation_cancel_permission`, который уже разрешает creator'у draft и запрещает submitted non-root.

### 6.7. Submit and irreversible actions

Agent должен fail closed:

- `/operations/{id}/submit` → 403/domain `RoleNotPermitted` envelope;
- submitted cancel → 403;
- restore → 403;
- acceptance → 403;
- correction submit → 403;
- lost resolve → 403;
- temporary moderation → 403.

Не добавлять agent в `WRITE_ROLES`, `can_accept_at_site`, `has_global_business_access` или root/chief checks ради обхода конкретного теста.

---

## 7. Admin and token management

### 7.1. Admin access

`require_admin_basic` и `require_root_admin` не менять.

Agent не получает `/admin/*` authority.

`GET /admin/roles` остаётся root/chief-only; `CANONICAL_ROLES` просто начинает возвращать пятое значение `agent` администратору.

### 7.2. Agent user provisioning

Новый CLI/bootstrap не создавать.

Provisioning procedure:

1. root создаёт/sync'ит non-root user `role=agent` через существующий admin/sync-user flow;
2. сервер выдаёт/хранит собственный `user_token`;
3. этот token помещается в конфигурацию agent wrapper;
4. agent вызывает SyncServer с `X-User-Token: <agent token>`.

Никаких fallback/alias к chief token.

---

## 8. Audit

### 8.1. Actor

Для всех agent mutations:

```text
actor_user_id = agent user UUID
```

Не подменять actor на chief.

Текущая audit schema не хранит `actor_role` snapshot. Это не требуется этой задачей.

### 8.2. Existing audit reuse

Подтвердить тестами, что существующий код уже даёт требуемую evidence:

- catalog create: entity id + actor;
- catalog update: `changes` old/new + actor;
- catalog merge: source/target + actor;
- operation draft create/update/cancel: actor = agent.

Если существующий merge audit не содержит source/target в достаточной форме, исправить только payload/resource evidence, не создавать новый audit subsystem.

---

## 9. Repository-wide role audit

Перед кодированием executor выполняет поиск минимум по:

```text
"observer"
"storekeeper"
"chief_storekeeper"
CANONICAL_ROLES
READ_ROLES
WRITE_ROLES
ALLOWED_*_ROLES
has_global_business_access
can_manage_catalog
require_admin_basic
require_operate_site
```

Каждое совпадение классифицируется:

1. business read → добавить agent, если observer уже имеет read;
2. draft preparation → добавить agent только где требуется этой TZ;
3. submit/accept/lifecycle/admin → agent не добавлять;
4. technical/machine/device sync → не менять без отдельного требования.

В финальном evidence приложить список изменённых role sets/guards. Это защита от ситуации «роль добавили в три файла, четвёртый забыли».

---

## 10. Tests

### 10.1. Role and provisioning

- [ ] DB accepts `role=agent` after migration
- [ ] Pydantic `UserRole` accepts `agent`
- [ ] root `POST /auth/sync-user` can create/update `role=agent`
- [ ] root admin user create can create `role=agent`
- [ ] `/admin/roles`, called by authorized admin, contains `agent`
- [ ] agent itself still gets 403 on `/admin/roles`
- [ ] `/auth/me` returns `role=agent`
- [ ] `/auth/context` returns correct agent summary
- [ ] `/auth/sites` returns all active business sites with `can_operate=false`, `can_manage_catalog=true`

### 10.2. Business read

- [ ] agent reads catalog items/categories/units/tree/browse
- [ ] agent reads balances globally
- [ ] agent reads operations globally subject to existing cancelled rule
- [ ] repository-wide observer business-read parity audit has no missed role gate

### 10.3. Catalog create

- [ ] agent creates Item
- [ ] agent creates Category
- [ ] agent creates Unit
- [ ] existing uniqueness/FK/category-cycle validations still apply

### 10.4. Catalog PATCH

- [ ] Item: name allowed
- [ ] Item: sku allowed
- [ ] Item: description allowed
- [ ] Item: category_id allowed
- [ ] Item: unit_id allowed
- [ ] Item: hashtags allowed
- [ ] Item: is_active rejected for agent
- [ ] Category allowed fields succeed
- [ ] Category is_active rejected
- [ ] Unit allowed fields succeed
- [ ] Unit is_active rejected
- [ ] merge/system fields cannot be mutated through ordinary PATCH
- [ ] chief/root existing PATCH abilities do not regress

### 10.5. Merge

- [ ] agent item merge succeeds through existing merge endpoint
- [ ] agent category merge succeeds through existing merge endpoint
- [ ] freeze/inventory/balance/audit invariants of existing merge remain green
- [ ] direct merge-field mutation remains impossible

### 10.6. Operations

- [ ] agent creates draft
- [ ] agent creates source-document draft
- [ ] agent can PATCH own draft lines
- [ ] agent can PATCH own draft notes/effective_at
- [ ] agent can change operation_type/relevant MOVE fields of own draft subject to existing domain validation
- [ ] agent cannot PATCH another user's draft
- [ ] agent cannot PATCH submitted operation
- [ ] agent cannot create/use temporary_item through draft flow
- [ ] agent can cancel own draft
- [ ] agent cannot cancel another user's draft
- [ ] agent cannot cancel submitted operation
- [ ] agent submit → 403/domain RoleNotPermitted
- [ ] agent restore → 403
- [ ] agent acceptance → 403
- [ ] agent correction submit → 403
- [ ] agent delete operation → 403 in v1

### 10.7. Admin/security

- [ ] agent cannot manage users
- [ ] agent cannot read/rotate user tokens
- [ ] agent cannot manage devices/device tokens
- [ ] agent cannot create/update sites
- [ ] agent cannot manage access scopes
- [ ] agent cannot gain root/chief bypass
- [ ] agent never uses chief token in tests/fixtures

### 10.8. Audit

- [ ] item create actor_user_id = agent
- [ ] item patch actor_user_id = agent and changes old/new preserved
- [ ] merge actor_user_id = agent with source/target evidence
- [ ] operation draft create/update/cancel actor_user_id = agent
- [ ] no event rewrites actor to chief

### 10.9. Regression

Run full existing SyncServer test suite. Existing behavior of root/chief/storekeeper/observer must remain green.

Particularly re-run:

- auth/admin tests;
- catalog CRUD/merge/batch tests;
- operations permissions/workflow/submit tests;
- balances/read tests;
- audit tests;
- migration tests.

`/catalog/admin/batch` must remain unchanged for existing authorized roles.

---

## 11. Stand smoke

Against real SyncServer + Postgres:

1. migrate to head;
2. create agent-user via existing root API;
3. capture agent token through authorized provisioning flow;
4. `GET /auth/me` → role agent;
5. read catalog + balances + operations;
6. create category/unit/item;
7. PATCH item allowed field;
8. PATCH item `is_active` → 403;
9. merge two test items;
10. create draft operation;
11. PATCH own draft;
12. submit same draft with agent token → 403;
13. submit same draft with chief token → success, if domain data allows;
14. verify audit actor separation: catalog/draft = agent, submit = chief;
15. agent `/admin/users` → 403.

Smoke test data must use dedicated test entities and be cleaned using existing test/stand procedure. Не добавлять production repair scripts ради smoke.

---

## 12. Documentation changes

В SyncServer обновить:

- `DOMAIN_MODEL.md`;
- role/auth sections in `docs/API_REFERENCE.md`;
- `API_MAP.md` if present/authoritative in this repo;
- `AI_CONTEXT.md` / `MEMORY.md` only where role model is enumerated;
- `docs/adr/0030-agent-domain-role.md`;
- role comments/constants in code.

В workspace-level документации обновить, если executor работает из общего workspace:

- `Role Matrix.md`;
- `Functional and WorkLogik.md` — добавить `agent` как отдельную роль и зафиксировать draft-only operation authority.

Agent wrapper/skill configuration является отдельной клиентской частью. Она должна использовать новый agent token и содержать behavioural rule о явной команде на PATCH/MERGE, но изменение wrapper не должно требовать правок Warehouse_web и не должно расширять SyncServer scope.

---

## 13. Implementation strategy

### M1 — Domain role

- migration;
- `UserRole`;
- `CANONICAL_ROLES`;
- optional `Identity.is_agent`;
- unit tests role/provisioning.

### M2 — Read/auth context

- catalog read roles;
- balances read roles;
- operations read roles;
- `/auth/sites` + `/auth/context`;
- repo-wide role audit.

### M3 — Catalog mutations

- centralized catalog agent policy/helper;
- selected create/PATCH/merge route guards;
- PATCH allow-list;
- keep delete/batch denied;
- catalog tests/audit tests.

### M4 — Draft operations

- own-draft route path for PATCH;
- own-draft cancel path;
- preserve submit fail-closed;
- tests.

### M5 — Integration/regression

- DB-backed authz tests;
- full suite;
- stand smoke;
- evidence table.

### M6 — Docs/final review

- update domain/API docs;
- ADR final wording;
- workspace role docs if available;
- final acceptance.

M2 and M3 may be parallelized only after M1 if agents do not edit the same policy files. Otherwise execute sequentially. Не создавать искусственные milestones/commits только ради соответствия этому документу; commit granularity определяется реальными cohesive changes.

---

## 14. Definition of Done

Feature считается готовой, когда одновременно выполнено:

1. `agent` является валидной пятой доменной ролью DB + schemas.
2. Agent-user создаётся штатным root admin/sync-user flow; bootstrap не менялся.
3. Agent использует собственный user token; impersonation отсутствует.
4. Agent имеет business-read не уже observer и видит нужные глобальные warehouse данные.
5. Agent может create Item/Category/Unit.
6. Agent может PATCH разрешённые business fields существующего каталога, включая `hashtags` Item, но не `is_active`.
7. Agent может merge Items/Categories только через существующие merge services.
8. `/catalog/admin/batch`, delete/deactivate и admin authority agent не получили.
9. Agent может create/PATCH/cancel собственный draft, включая существующие draft-edit поля, но не temporary item flow.
10. Agent не может submit/accept/restore/cancel submitted или изменить submitted operation.
11. `has_global_business_access` остаётся только root/chief.
12. Audit сохраняет реальный agent `actor_user_id`; chief submit остаётся отдельным actor.
13. Full regression suite существующих ролей зелёный.
14. Stand smoke подтверждает `agent draft -> chief submit` end-to-end.
15. Не добавлены catalog approval/submission workflow, agent bootstrap path или token impersonation.
