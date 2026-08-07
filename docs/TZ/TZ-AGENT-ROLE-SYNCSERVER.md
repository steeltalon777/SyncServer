# TZ: SyncServer — Доменная роль `agent` для LLM и безопасный доступ к каталогу

> Источник задачи: GitHub Issue
> `steeltalon777/warehouse_solution-#18`
> «FEAT: SyncServer — доменная роль agent для LLM и безопасный доступ к каталогу»
> (2026-08-07, status: Ready to Work, repository: `steeltalon777/warehouse_solution-`).

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Implementation level 1 complete — role enum, check constraint, default guard
- [ ] 3. Unit/component tests complete — role/identity/policy unit tests
- [ ] 4. Integration tests with real dependencies complete — DB-backed authz tests
- [ ] 5. Stand smoke tests complete — real SyncServer + Postgres
- [ ] 6. UI automation tests complete — N/A (server-only feature; covered by 5)
- [ ] 7. User scenario tests complete — agent draft→chief submit happy path
- [ ] 8. Regression checks complete — существующие 4 роли без регрессий
- [ ] 9. Documentation updated — DOMAIN_MODEL, Role Matrix, Functional, API_MAP, ADR
- [ ] 10. Final acceptance review complete

## Check Rules

- Architect (этот документ) создаёт чек-лист и критерии приёмки.
- Executor-агенты отмечают пункты 0–9 только после собственной проверки.
- QA-проверяющий отмечает пункт 10 только после рассмотрения evidence.
- Пропущенные проверки остаются `[ ]` с пометкой «стенд недоступен» или «feature not applicable».

---

## 1. Purpose

Добавить в SyncServer самостоятельную доменную роль `agent`,
которая представляет доверенного LLM-агента главного кладовщика.

`agent`:

- читает каталог, единицы, категории, склады, остатки, операции и
  репозитории основного UI;
- создаёт и правит каталог через штатные сервисы (`items`, `categories`,
  `units`), используя только разрешённые бизнес-поля;
- выполняет штатный merge ТМЦ и категорий через существующие
  endpoint'ы `items/merge` и `categories/merge`;
- создаёт и редактирует только `draft`-операции;
- **не** подтверждает операции, **не** отменяет подтверждённые,
  **не** восстанавливает отменённые, **не** управляет
  пользователями / устройствами / токенами / складами;
- **не** изменяет служебные merge/system-поля напрямую.

Все ограничения должны быть **серверными**, а не свойством
skill/system prompt/CLI-обвязки.

`agent` всегда работает под собственным `X-User-Token`. Подмена
его токена на токен главного кладовщика запрещена.

На текущем этапе отдельный human approval/Submission workflow для
каталога **не вводится**: правило «PATCH/MERGE только после явной
команды кладовщика» живёт в agent wrapper / system prompt.

---

## 2. Source Requirements

- Issue `steeltalon777/warehouse_solution-#18` — текст issue, раздел
  «Архитектурное решение» и далее (разрешённые/запрещённые действия,
  audit, поведенческое правило вне SyncServer).
- Корневой `Functional and WorkLogik.md` — канонический источник
  функциональных требований; роль `agent` добавляется как новая роль
  (расширение существующего множества `root/chief_storekeeper/storekeeper/observer`).
  Это требует обновления раздела II и `Role Matrix.md`.
- `Role Matrix.md` — текущая матрица 4×N; роль `agent` добавляется
  отдельной колонкой (см. §10).
- `SyncServer/AGENTS.md` и `SyncServer/AI_CONTEXT.md` — правила
  слоистой архитектуры (API → services → repos → PostgreSQL через
  `UnitOfWork`); бизнес-правила и authz остаются в сервисах и
  политике.
- `SyncServer/docs/adr/0005-token-auth-and-site-scoped-access.md` —
  `X-User-Token` / `X-Device-Token`, `User.is_root`, `User.role`,
  `UserAccessScope`. Роль `agent` не получает site scopes по
  умолчанию (см. §6) и не считается `has_global_business_access`.
- `SyncServer/docs/adr/0002-layered-architecture-with-unit-of-work.md`
  — все мутации через `UnitOfWork`; route остаётся тонким; auth
  логика выносится в политику.
- `SyncServer/docs/adr/0001-syncserver-source-of-truth.md` —
  SyncServer остаётся единственным источником истины для каталога и
  операций; agent не пишет в обход него.
- Существующие политики:
  `SyncServer/app/services/operations_policy.py`,
  `SyncServer/app/services/operations_workflow_policy.py`,
  `SyncServer/app/api/admin_common.py`,
  `SyncServer/app/services/access_service.py`,
  `SyncServer/app/services/access_service_v2.py`,
  `SyncServer/app/services/catalog_admin_service.py`.

### Out of Scope

- Новые сущности `CatalogChangeRequest`, `CatalogMergeRequest`,
  `CatalogApproval`.
- Server-side state machine «submit/approve» для изменений каталога.
- Token impersonation (`agent-token` подменять на `chief_storekeeper-token`).
- Расширение `chief_storekeeper` (выдача его прав агенту).
- Прямой PATCH `merged_into_id`, `deleted_at`, `is_active` через
  обычные PATCH endpoint'ы.
- Прямой `submit` операций агентом.

---

## 3. Current State Snapshot

### 3.1. Auth и role enum

- `SyncServer/app/models/user.py` — `User.role: String(32)`,
  `CheckConstraint("role IN ('root', 'chief_storekeeper', 'storekeeper', 'observer')")`.
  Добавление `agent` требует обновления `Literal[...]` в
  `app/schemas/admin.py:12` и миграции `alembic`.
- `SyncServer/app/schemas/admin.py:12` —
  `UserRole = Literal["root","chief_storekeeper","storekeeper","observer"]`.
  Используется в `UserCreate`, `UserUpdate`, фильтрах.
- `SyncServer/app/services/admin_users_service.py:31` —
  `validate_user_role_payload` уже валидирует `role != "root"` для
  admin API (root создаётся только bootstrap'ом). Расширение enum
  до `agent` совместимо с этим правилом.
- `SyncServer/app/services/identity_service.py` и
  `app/core/identity.py` — `Identity` уже отдаёт
  `role`, `is_root`, `has_global_business_access`, `can_*` методы.
  `agent` должен попадать в `Identity.role`, но **не** в
  `has_global_business_access`.

### 3.2. Authz-решения в коде

- `SyncServer/app/api/admin_common.py:10` —
  `CANONICAL_ROLES = ["root","chief_storekeeper","storekeeper","observer"]`
  подаётся в `GET /api/v1/admin/roles`. Должен включать `agent`.
- `SyncServer/app/api/admin_common.py:18` —
  `require_admin_basic` пропускает только `is_root` или
  `role == "chief_storekeeper"`. `agent` не должен проходить.
- `SyncServer/app/api/routes_catalog_admin.py:39` —
  `_require_catalog_admin` — то же правило, должно остаться
  для back-office admin; agent будет иметь **отдельный guard**.
- `SyncServer/app/services/operations_policy.py`:
  - `READ_ROLES = {"chief_storekeeper","storekeeper","observer"}`
    (operations read).
  - `WRITE_ROLES = {"chief_storekeeper","storekeeper"}` (operations
    create, submit).
  - `CREATE_DRAFT_ROLES = {"chief_storekeeper","storekeeper","observer"}`
    — agent надо явно добавить.
  - `require_operation_submit_permission` —
    `has_global_business_access` или `role == "storekeeper"`.
    Для `agent` должен возвращать 403.
  - `require_operation_cancel_permission` — для submitted → только
    root; для draft → creator, chief, root. agent — не creator
    бизнес-операции, но сам draft создал — должен иметь право
    отменять **свои** draft.
  - `require_root_for_restore` — только root; agent → 403.
  - `require_operation_effective_at_permission` —
    `has_global_business_access` или (draft + creator). agent →
    только свои draft.
  - `require_temporary_item_moderation` — только chief/root;
    agent → 403.
  - `require_lost_resolve_access` — только chief/root;
    agent → 403.

### 3.3. Catalog admin / merge

- `SyncServer/app/services/catalog_admin_service.py` —
  `merge_items`, `merge_categories`, `update_item`,
  `update_category`, `update_unit`, `create_item`,
  `create_category`, `create_unit` принимают `*_by_user_id` и пишут
  audit через `record_audit_event(actor_user_id=...)`.
- `SyncServer/app/api/routes_catalog_admin.py` — все write endpoint'ы
  catalog admin защищены `_require_catalog_admin`. Под `agent` они
  должны открываться частично:
  - POST `/catalog/admin/units`, `/categories`, `/items` —
    разрешить;
  - PATCH `/catalog/admin/units/{id}`, `/categories/{id}`,
    `/items/{id}` — разрешить с фильтром полей;
  - POST `/catalog/admin/items/merge`, `/categories/merge` —
    разрешить;
  - GET `/catalog/admin/units`, `/categories`, `/items` (списки и
    отдельные) — разрешить для чтения;
  - DELETE `/catalog/admin/units/{id}`, `/categories/{id}`,
    `/items/{id}` — запретить (catalog lifecycle обход через soft
    delete + active=false; agent не должен иметь возможности
    удалять/деактивировать).
  - POST `/catalog/admin/batch` — применить allow-list к каждому
    change, запретить delete/deactivate для `agent`.
  - POST `/catalog/admin/units/bulk`, `/categories/bulk` — разрешить
    create только.

### 3.4. Audit

- `SyncServer/app/services/audit_helper.py:17` —
  `record_audit_event(actor_user_id=...)` уже хранит реальный UUID
  актёра. `actor_role` как поле в `audit_events` на текущий момент
  не сохраняется — он восстанавливается через join с `users.role`.
- `SyncServer/app/models/audit_event.py` — таблица `audit_events`.
  В этой TZ роль `agent` хранится в `actor_user_id`; отдельный
  `actor_role` snapshot можно добавить позже отдельным изменением
  (см. §11 риски).

### 3.5. Identity / token

- `SyncServer/app/api/deps.py:104` — `require_user_identity`
  резолвит `X-User-Token` в `Identity(user=...)` независимо от роли.
  Никакой impersonation по `X-User-Token` другого пользователя.
- `SyncServer/app/api/routes_auth.py`:
  - `GET /api/v1/auth/me` — уже возвращает `role` пользователя.
    Поле `role` приходит прямо из `user.role`, поэтому `agent`
    отобразится без изменений.
  - `GET /api/v1/auth/context` — `permissions_summary` строится
    через `access_service.get_user_permissions_uuid`, который
    отдаёт `False` для не-root/non-chief. agent должен видеть
    свой `role`, но `can_manage_catalog` и `can_create_operations`
    должны быть либо **True** (где явно разрешено) либо **False**
    (где запрещено) — см. §6.

---

## 4. Architecture Boundaries

### 4.1. SyncServer owns

- Расширение `users.role` enum (DB check constraint + Pydantic
  literal).
- Серверная authz-политика роли `agent`.
- Поле-allow-list для PATCH каталога (проверяется в сервисах).
- Серверный запрет submit/merge-bypass/restore.
- Audit: actor_user_id остаётся UUID агента (без переименования).
- Документация: `DOMAIN_MODEL.md`, `Role Matrix.md`,
  `Functional and WorkLogik.md` (через ADR-override в этом же TZ),
  `API_MAP.md`.

### 4.2. Warehouse_web (BFF) owns

- Не получает SyncServer-токен агента. Django хранит binding
  Django-user → SyncUser (role=agent) и проксирует запросы от
  своего серверного кода, а не от браузера.
- `apps/sync_client/client.py` уже умеет проксировать
  `X-User-Token`. Никакой клиент-специфичной логики для `agent`
  добавлять не требуется.

### 4.3. warehouse-storekeeper (agent wrapper) owns

- Системный prompt с правилом «PATCH/MERGE только после явной
  команды кладовщика». Это **вне** SyncServer и не считается
  границей безопасности.
- Обновить `syncserver.env.example` и `SKILL.md`, чтобы агент
  использовал токен роли `agent`, а не `chief_storekeeper`.

### 4.4. SyncServer tests owns

- Расширение unit-тестов в `tests/test_operations_permissions.py`,
  `tests/test_auth_routes.py`, `tests/test_user_admin_flow.py`,
  `tests/test_admin_root_permissions.py`, `tests/test_catalog_*`.
- Новый файл `tests/test_agent_role_authz.py` — матрица сценариев
  issue #18.

### 4.5. Functional and WorkLogik (canonical)

- Добавить пункт 2.1.5 «agent» в раздел II с явной ссылкой на
  ADR-0030 (новый, см. §13) и эту TZ.
- `Role Matrix.md` — добавить колонку `agent` и строки «Создать
  черновик», «Подтвердить операцию», «Управлять справочником»,
  «Управлять пользователями», «PATCH/MERGE каталога» и т.д.

---

## 5. Domain Model Changes

### 5.1. `users.role`

- **Column type:** без изменений (`String(32)`).
- **Check constraint:**
  `role IN ('root','chief_storekeeper','storekeeper','observer','agent')`.
- **Pydantic literal:** `UserRole = Literal["root","chief_storekeeper","storekeeper","observer","agent"]`.
- **`CANONICAL_ROLES`** в `app/api/admin_common.py`:
  `["root","chief_storekeeper","storekeeper","observer","agent"]`.
- **Alembic migration** (новая ревизия, `down_revision` =
  последний существующий): `op.drop_constraint("ck_users_role", "users", type_="check")`
  + `op.create_check_constraint("ck_users_role", "users", "role IN ('root','chief_storekeeper','storekeeper','observer','agent')")`.
  Миграция **не** меняет существующие строки; добавление нового
  значения в `IN` обратно совместимо.

### 5.2. `Identity` (`app/core/identity.py`)

Добавить derived-метод (без ломки обратной совместимости):

```python
@property
def is_agent(self) -> bool:
    return self.user is not None and self.user.role == "agent"
```

`agent` не входит в `has_global_business_access`, не имеет
site-scoped прав через `UserAccessScope` (agent не управляет
складами и не оперирует), но при catalog read/operations
read получает доступ ко всем сайтам (catalog global).

### 5.3. `OperationsPolicy` (`app/services/operations_policy.py`)

- Добавить `"agent"` в `CREATE_DRAFT_ROLES`.
- В `require_create_draft(identity, site_id)`:
  - для `agent` — пропускать, **без** проверки site scope.
- `READ_ROLES`: agent уже попадает под существующий
  `{"chief_storekeeper","storekeeper","observer"}` **только** если
  в него добавить. Для read operations agent должен видеть все
  draft + submitted. Решение: agent добавляется в
  `READ_ROLES` (через `has_global_business_access` agent не
  проходит, поэтому нужна явная ветка).
- `require_operation_submit_permission`: для `agent` сразу 403
  (иначе он пройдёт через `has_global_business_access`? нет, не
  пройдёт — но `role == "storekeeper"` тоже False, и функция
  выдаст 403 уже сейчас). Требуется явный fail-closed комментарий
  и unit-тест «agent submit draft → 403».
- `require_operation_cancel_permission`:
  - draft, creator == agent: разрешить (своя draft);
  - draft, creator != agent: 403;
  - submitted: 403 (как у всех не-root);
  - cancelled → no-op: 409.
- `require_operation_effective_at_permission`:
  - draft + creator == agent: разрешить;
  - иначе 403.
- `require_root_for_restore`: agent → 403.
- `require_operation_delete_permission`:
  - draft ещё нельзя удалять (по workflow `cancelled` нужен),
    agent не удаляет чужие; для agent — только свои
    cancelled, либо 403 для draft.
- `require_temporary_item_moderation`: agent → 403.
- `require_lost_resolve_access`: agent → 403.
- `require_assets_read_access`: agent видит `lost-assets`,
  `issued-assets`, `pending-acceptance` (read) — для этого
  добавить `agent` в `READ_ROLES` (см. выше).
- `require_move_access`: agent не управляет операциями, выходящими
  за draft; при попытке создать/обновить MOVE из agent-token →
  403 (`WRITE_ROLES` не включает agent).

### 5.4. Catalog admin policy (новый helper)

Ввести helper в `app/services/access_service.py` (или новый
`app/services/agent_policy.py`):

```python
class AgentPolicy:
    """Server-side authorization for the LLM 'agent' role.

    The server is the only source of truth. Skill/system-prompt
    guards are NOT relied upon.
    """

    AGENT_ITEM_PATCH_FIELDS: frozenset[str] = frozenset(
        {"name", "sku", "description", "category_id", "unit_id"}
    )
    AGENT_CATEGORY_PATCH_FIELDS: frozenset[str] = frozenset(
        {"name", "code", "parent_id", "sort_order"}
    )
    AGENT_UNIT_PATCH_FIELDS: frozenset[str] = frozenset(
        {"name", "symbol", "sort_order"}
    )

    @staticmethod
    def require_agent(identity: Identity) -> None: ...
    @staticmethod
    def filter_item_patch(payload: ItemUpdateRequest) -> ItemUpdateRequest: ...
    @staticmethod
    def filter_category_patch(payload: CategoryUpdateRequest) -> CategoryUpdateRequest: ...
    @staticmethod
    def filter_unit_patch(payload: UnitUpdateRequest) -> UnitUpdateRequest: ...
```

Правила:

- Если в payload присутствует поле **вне** allow-list, service
  выбрасывает `HTTPException(403, "field <X> is not editable for agent")`.
- Если в payload присутствует запрещённое поле, в т.ч.
  `is_active`, `requires_review`, `review_status`,
  `merged_into_id`, `merged_at`, `merged_by_user_id`,
  `merge_comment`, `deleted_at`, `deleted_by_user_id`,
  `created_by_user_id`, `updated_by_user_id` — тот же 403.
- `is_active` всегда запрещено менять агенту (обход lifecycle).
- `create_*` (Item/Category/Unit) разрешает **все** поля
  create-payload'а, кроме `is_active` если оно выставлено
  `False` без явного `?force=` (по умолчанию `True`). Это
  предотвращает случайное создание «неактивных» ТМЦ.
- `merge_items` / `merge_categories` — отдельные endpoint'ы, без
  bypass через PATCH. Метод должен принимать только
  `source_*_id`, `target_*_id`, `comment`. Прямой PATCH
  `merged_into_id` запрещён (см. §5.6).

### 5.5. Catalog admin routes (`app/api/routes_catalog_admin.py`)

Заменить `_require_catalog_admin` на два guard'а:

- `_require_catalog_admin_or_agent(identity)` — открывает
  read/create/patch/merge для agent и chief/root.
- `_require_catalog_admin(identity)` — оставить для delete,
  batch-delete, batch-deactivate (chief/root only).

| Endpoint | root | chief | agent | storekeeper | observer |
|---|---|---|---|---|---|
| `GET /catalog/admin/{units,categories,items}` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `GET /catalog/admin/{units,categories,items}/{id}` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `POST /catalog/admin/{units,categories,items}` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `POST /catalog/admin/{units,categories}/bulk` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `PATCH /catalog/admin/{units,categories,items}/{id}` | ✅ | ✅ | ✅ (allow-list) | ❌ | ❌ |
| `POST /catalog/admin/items/merge` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `POST /catalog/admin/categories/merge` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `POST /catalog/admin/batch` | ✅ | ✅ | ✅ (allow-list) | ❌ | ❌ |
| `DELETE /catalog/admin/{units,categories,items}/{id}` | ✅ | ✅ | ❌ | ❌ | ❌ |

### 5.6. Anti-bypass правила

- В `ItemUpdateRequest` / `CategoryUpdateRequest` /
  `UnitUpdateRequest` оставить текущие поля; **service** отвечает
  за фильтрацию. В `ItemUpdateRequest` уже есть `is_active`,
  `requires_review` и т.д. — `AgentPolicy` отфильтрует их.
- Прямой PATCH `merged_into_id` через `ItemUpdateRequest` не
  предусмотрен схемой; проверить явно в `update_item`, что
  атрибут `merged_into_id` (и `merged_at`, `merged_by_user_id`,
  `merge_comment`) **никогда** не записывается обычным
  `update_item` — это уже так (см.
  `app/services/catalog_admin_service.py:847`). Добавить unit-тест
  «agent не может выставить merged_into_id через PATCH».
- `update_item` для agent: нельзя `is_active` в payload.
- Merge bypass через PATCH `Item.category_id = <target>` без
  вызова `merge_items` — допустимо (это простое перемещение
  одной категории), но `merged_into_id` и `merged_at` НЕ
  выставляются.

### 5.7. Operations routes

- `POST /operations` (create draft) — agent проходит
  `require_create_draft`.
- `POST /operations/from-source-document` — agent проходит
  `require_create_draft`. Дополнительно: schema
  `SourceDocumentOperationCreate` не допускает `temporary_item`
  по построению, поэтому `require_temporary_item_create` не
  нужен.
- `PATCH /operations/{id}` — для agent только свои draft:
  - `require_operate_site(identity, site_id)` сейчас пропускает
    только chief/root/storekeeper. agent не проходит. Нужна
    отдельная ветка: agent → если draft && creator == agent
    && status == draft, разрешить update lines (но не operation_type
    и не site, см. ADR-0025/0027).
  - Рекомендация: добавить в `OperationsPolicy`
    `require_agent_update_own_draft(identity, operation)` —
    fail-closed helper, который заменяет
    `require_operate_site` для agent и принимает только свои
    draft.
- `PATCH /operations/{id}/effective-at` — agent может менять
  effective_at **только** для своих draft (см.
  `require_operation_effective_at_permission`).
- `POST /operations/{id}/submit` — agent 403.
- `POST /operations/{id}/cancel`:
  - draft, creator == agent: 200;
  - draft, creator != agent: 403;
  - submitted: 403.
- `POST /operations/{id}/restore` — agent 403.
- `DELETE /operations/{id}` — agent только свои cancelled.
- `POST /corrections/{op}/{corr}/submit` — corrections submit.
  Текущий код требует 403 для не chief/root. agent → 403.

### 5.8. Admin routes

- `require_admin_basic(identity)` — оставить `is_root` или
  `role == "chief_storekeeper"`. agent не проходит.
- `require_root_admin(identity)` — без изменений.
- Все `/admin/users*`, `/admin/devices*`, `/admin/sites*`,
  `/admin/access/*`, `/admin/audit/*` — agent 403.
- `GET /api/v1/admin/roles` — должен включать `agent` (т.е.
  `CANONICAL_ROLES` уже расширен).

### 5.9. Auth endpoints

- `GET /api/v1/auth/me` — без изменений, отдаёт `role: "agent"`.
- `GET /api/v1/auth/context` — `permissions_summary`:
  - `can_read_operations`: True;
  - `can_create_operations`: True (только draft);
  - `can_read_balances`: True;
  - `can_manage_catalog`: True (с allow-list);
  - `can_manage_root_admin`: False;
  - `is_root`: False.
- `GET /api/v1/auth/sites` — agent получает все активные сайты
  (catalog global). Реализация: добавить ветку `is_agent or
  has_global_business_access` в `routes_auth.py:get_user_sites` и
  `get_auth_context` (или унифицировать через Identity helper).

### 5.10. Audit

- `actor_user_id` = agent user UUID. `actor_role` явно НЕ
  подменяется на `chief_storekeeper`.
- Audit payload для catalog patch: до/после по allow-listed
  полям; `merged_into_id`/`is_active` в payload не пишутся.
- Audit payload для merge: source/target ids.
- Audit payload для operation draft create/patch: agent user id.
- Запись `actor_role` как явного поля в `audit_events` —
  **out of scope** этой TZ. См. §11 risk R-2.

---

## 6. Site Scoping и access

`agent` — глобальная роль для catalog-уровня. Site scopes через
`UserAccessScope` **не используются** для `agent`:

- `UserAccessScope` предназначен для storekeeper/observer
  (per-site `can_view`, `can_operate`, `can_manage_catalog`).
- У `agent` нет складского «физического» контекста; он готовит
  данные для главного кладовщика. Поэтому:
  - Catalog read/CRUD/merge — глобально (catalog global).
  - Operations create/patch — без site-scope проверки
    (`require_create_draft` без `can_operate_at_site`).
  - Operations submit/accept/cancel submitted/restore —
    запрещено.

`Identity.has_global_business_access` остаётся
`(is_root or role == "chief_storekeeper")`. `agent` не попадает
в `has_global_business_access`. Глобальность catalog read для
agent реализуется явной веткой в `routes_auth.py` и в
`routes_catalog.py` (`ALLOWED_CATALOG_READ_ROLES` включает
`agent`).

`ALLOWED_CATALOG_READ_ROLES = {"chief_storekeeper","storekeeper","observer","agent"}`.

---

## 7. Data Model & Migration

Одна новая Alembic-ревизия, например
`SyncServer/alembic/versions/0038_add_agent_role.py` с
`down_revision = "0037_audit_item_effects_effective_at"`:

```python
def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('root','chief_storekeeper','storekeeper','observer','agent')",
    )


def downgrade() -> None:
    # Сначала привести существующие роли 'agent' к 'observer' (безопасный fallback).
    op.execute(
        "UPDATE users SET role = 'observer' WHERE role = 'agent'"
    )
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('root','chief_storekeeper','storekeeper','observer')",
    )
```

Downgrade — defensive: заменяет `agent` на `observer` (наименее
привилегированная существующая роль), потом сужает check.

Поле `is_root` остаётся `False` для agent. Bootstrap agent-user'а
выполняется через существующий `/api/v1/auth/sync-user` (root-only)
или через `scripts/bootstrap_root.py` (расширение). Это часть
этой TZ (см. §9).

---

## 8. API Surface

Существующие endpoint'ы; никаких новых маршрутов не вводится.

| Endpoint | agent | notes |
|---|---|---|
| `GET /api/v1/auth/me` | ✅ | `role=agent` |
| `GET /api/v1/auth/sites` | ✅ | все активные сайты (catalog global) |
| `GET /api/v1/auth/context` | ✅ | `permissions_summary` см. §5.9 |
| `GET /api/v1/admin/roles` | ✅ (read) | массив включает `agent` |
| `GET /api/v1/admin/users*` | ❌ | 403 |
| `GET /api/v1/admin/devices*` | ❌ | 403 |
| `GET /api/v1/admin/sites*` | ❌ | 403 |
| `GET /api/v1/admin/access/*` | ❌ | 403 |
| `GET /api/v1/admin/audit/*` | ❌ | 403 |
| `GET /api/v1/catalog/{units,categories,items,sites}` | ✅ | read |
| `GET /api/v1/catalog/*` (browse) | ✅ | read |
| `GET /api/v1/catalog/admin/{units,categories,items}` | ✅ | read (с фильтрами) |
| `GET /api/v1/catalog/admin/{units,categories,items}/{id}` | ✅ | read |
| `POST /api/v1/catalog/admin/{units,categories,items}` | ✅ | create |
| `POST /api/v1/catalog/admin/{units,categories}/bulk` | ✅ | bulk create |
| `PATCH /api/v1/catalog/admin/{units,categories,items}/{id}` | ✅ | allow-list |
| `POST /api/v1/catalog/admin/items/merge` | ✅ | штатный merge |
| `POST /api/v1/catalog/admin/categories/merge` | ✅ | штатный merge |
| `POST /api/v1/catalog/admin/batch` | ✅ | apply allow-list, запрет delete/deactivate |
| `DELETE /api/v1/catalog/admin/{units,categories,items}/{id}` | ❌ | 403 |
| `GET /api/v1/balances*` | ✅ | read |
| `GET /api/v1/operations*` | ✅ | read |
| `GET /api/v1/operations/{id}` | ✅ | read (без cancelled-list) |
| `POST /api/v1/operations` | ✅ | draft only |
| `POST /api/v1/operations/from-source-document` | ✅ | draft only |
| `PATCH /api/v1/operations/{id}` | ✅ | только свои draft |
| `PATCH /api/v1/operations/{id}/effective-at` | ✅ | только свои draft |
| `POST /api/v1/operations/{id}/submit` | ❌ | 403 |
| `POST /api/v1/operations/{id}/cancel` | ✅ (свои draft) / ❌ submitted | по workflow |
| `POST /api/v1/operations/{id}/restore` | ❌ | 403 |
| `DELETE /api/v1/operations/{id}` | ❌ (draft) / ✅ (свои cancelled) | 403 для draft |
| `POST /api/v1/operations/{id}/corrections/{cid}/submit` | ❌ | 403 |
| `GET /api/v1/documents*` | ✅ | read |
| `GET /api/v1/reports*` | ✅ | read |
| `GET /api/v1/diagnostics/*` | ✅ | read (ui-events) |
| `POST /api/v1/diagnostics/ui-events/batch` | ✅ | agent-as-user |
| `GET /api/v1/review-items/*` | ✅ | read |
| `GET /api/v1/issue-objects/*` | ✅ | read |
| `GET /api/v1/machines/*` | ✅ | read |
| `GET /api/v1/health/*` | ✅ | read |

Agent не получает никаких новых URL. Все изменения — серверные
guard'ы и policy.

---

## 9. Bootstrap & Seeding

`SyncServer/scripts/bootstrap_root.py` расширяется опциональной
секцией `--agent-username` (например `agent_minimax`):
создаёт `User(role="agent", is_root=False, is_active=True, is_actor_for_agent=True)`
с собственным `user_token`, печатает токен, не заменяет
`chief_storekeeper` token и не имперсонирует. По умолчанию
agent-user **не** создаётся, чтобы избежать случайной выдачи
прав. Idempotent: повторный запуск обновляет `is_active` и
печатает существующий токен (без ротации).

`scripts/rotate_tokens.py` не должен трогать agent-token без
явного флага `--agent` (по умолчанию — нет).

---

## 10. Test Ladder

Все уровни применяются в порядке; пропущенные остаются `[ ]` с
блокер-нотой.

### L1 — Static checks

- `python -m pytest` (после изменений) — фактически запускает
  unit-тесты, но не делает type-check отдельно.
- `mypy SyncServer/app` (опционально, если включён в CI).
- `alembic upgrade head` против dev-стенда.

### L2 — Unit tests (syncserver, app/services + app/api)

Новый файл `SyncServer/tests/test_agent_role_authz.py`:

- `test_agent_role_accepted_as_valid_domain_role`
- `test_admin_roles_includes_agent`
- `test_auth_me_returns_role_agent`
- `test_auth_context_returns_role_agent_with_correct_permissions`
- `test_agent_can_read_catalog_items_categories_units_sites`
- `test_agent_can_create_item`
- `test_agent_can_create_category`
- `test_agent_can_create_unit`
- `test_agent_can_patch_item_allowed_fields`
- `test_agent_cannot_patch_item_is_active`
- `test_agent_cannot_patch_item_merged_into_id_via_schema`
- `test_agent_cannot_patch_item_requires_review`
- `test_agent_can_patch_category_allowed_fields`
- `test_agent_can_patch_unit_allowed_fields`
- `test_agent_can_merge_items_through_existing_endpoint`
- `test_agent_can_merge_categories_through_existing_endpoint`
- `test_agent_merge_preserves_all_existing_invariants`
- `test_agent_can_create_draft_operation`
- `test_agent_can_patch_own_draft_operation`
- `test_agent_cannot_submit_draft_403`
- `test_agent_cannot_edit_submitted_operation`
- `test_agent_cannot_restore_cancelled_operation`
- `test_agent_cannot_cancel_submitted_operation`
- `test_agent_cannot_cancel_other_users_draft`
- `test_agent_cannot_manage_users_403`
- `test_agent_cannot_manage_devices_403`
- `test_agent_cannot_manage_sites_403`
- `test_agent_cannot_rotate_user_tokens_403`
- `test_agent_token_is_not_treated_as_chief`
- `test_agent_cannot_use_root_bypass_in_any_endpoint`
- `test_audit_records_actor_agent_for_item_create`
- `test_audit_records_actor_agent_for_item_patch`
- `test_audit_records_actor_agent_for_item_merge`
- `test_audit_records_actor_agent_for_draft_operation_create`
- `test_audit_does_not_record_chief_storekeeper_when_actor_was_agent`
- `test_batch_endpoint_drops_disallowed_changes_for_agent`
- `test_batch_endpoint_rejects_delete_changes_for_agent`
- `test_batch_endpoint_rejects_deactivate_changes_for_agent`
- `test_agent_token_header_does_not_impersonate_chief`
- `test_agent_isolated_from_other_user_drafts`

Расширение существующих файлов:

- `tests/test_user_admin_flow.py` — `test_admin_users_create_with_role_agent_succeeds`
  (через root), `test_admin_users_list_includes_agent`.
- `tests/test_operations_permissions.py` —
  параметризовать существующие тесты на роль `agent`.
- `tests/test_catalog_admin_audit.py`,
  `tests/test_catalog_merge.py`,
  `tests/test_catalog_batch.py` — добавить сценарии с `agent`.
- `tests/test_auth_routes.py` — `test_auth_me_for_agent`,
  `test_auth_context_for_agent`, `test_admin_roles_includes_agent`.
- `tests/test_admin_root_permissions.py` — негативные сценарии
  agent на admin endpoints.

### L3 — Component tests (Django BFF / sync_client)

- `Warehouse_web/tests/` — `test_bff_passes_agent_token` (BFF
  проксирует agent-token без изменений), `test_bff_rejects_browser_agent_token`
  (агент-токен не отдаётся в браузер).

### L4 — Integration tests (DB-backed)

- Существующие `tests/test_alembic_migrations.py` —
  `test_role_agent_in_check_constraint_after_migration`.
- Существующие `tests/test_audit_*` — проверка actor_user_id для
  роли `agent`.

### L5 — Stand smoke tests

- `pytest -m stand` (если включён) или прямой curl против dev-стенда:
  - `GET /api/v1/health` — OK.
  - `GET /api/v1/auth/me` с agent-token — `role: agent`.
  - `POST /catalog/admin/items` с agent-token — создаёт
    (после bootstrap).
  - `POST /catalog/admin/items/merge` с agent-token — выполняет merge.
  - `POST /operations/{id}/submit` с agent-token — 403.
  - `POST /admin/users` с agent-token — 403.
- Фиксация evidence в `tests/stand/...` или в GitHub Project Issue
  comment.

### L6 — UI automation

- Не применимо (server-only feature). `[ ]` с пометкой
  «N/A — server-only authz; covered by L2/L4/L5».

### L7 — User scenario

- Сценарий «агент готовит draft → chief подтверждает»:
  1. Bootstrap agent-user и chief-user.
  2. Agent создаёт Item, Category.
  3. Agent merge двух Items.
  4. Agent создаёт draft operation.
  5. Chief заходит, видит draft, submit'ит.
  6. Audit показывает actor=agent для шагов 2–4 и actor=chief
     для шага 5.

### L8 — Regression

- Прогон всех существующих unit/integration тестов
  (`python -m pytest`) — все 4 роли без регрессий.
- Отдельная выборка `tests/test_root_permissions.py` /
  `tests/test_admin_root_permissions.py` — agent не должен
  влиять.

### L9 — Documentation

- `SyncServer/DOMAIN_MODEL.md` — раздел Roles, раздел Catalog
  lifecycle, раздел Operations.
- `SyncServer/docs/API_REFERENCE.md` — обновить раздел Auth
  (роли), Catalog Admin, Operations.
- `SyncServer/docs/API_MAP.md` (если не помечен STALE) —
  привести к актуальной ролевой модели.
- `Role Matrix.md` (workspace root) — добавить колонку `agent`.
- `Functional and WorkLogik.md` — пункт 2.1.5, плюс явная
  ссылка на ADR-0030 (новый) и эту TZ.
- `warehouse-storekeeper/SKILL.md`,
  `warehouse-storekeeper/references/AUTH.md`,
  `warehouse-storekeeper/templates/syncserver.env.example` —
  agent-tokens и правила.
- Новая `docs/adr/0030-agent-domain-role.md` — описывает
  расширение role enum и серверные границы.

### L10 — Final acceptance

- Все `[ ]` L0–L9 закрыты, evidence-таблица собрана.
- Issue #18 в `Warehouse Solution` Project — перевод в `Done`
  Reviewer'ом.

---

## 11. Risks & Open Questions

- **R-1: agent + cancelled operations visibility.**
  Сейчас `can_view_cancelled_operations` доступно только root.
  agent видит draft, submitted; cancelled — нет. Это
  сознательное ограничение (issue #18 не требует cancelled
  visibility), но стоит подтвердить.
- **R-2: actor_role snapshot в audit.**
  Сейчас `audit_events` хранит только `actor_user_id`. Поиск
  по роли актёра требует join. Это out of scope этой TZ.
  Если в будущем audit UI потребуется фильтровать по
  `actor_role=agent`, добавим отдельной задачей.
- **R-3: bootstrap agent-user.**
  `bootstrap_root.py` сейчас создаёт только root + Django device.
  Расширение под agent-user — часть этой TZ. Альтернатива —
  отдельная TZ для bootstrap. Выбор: оставить в этой TZ (single
  PR, единая ответственность).
- **R-4: agent + TemporaryItem / ReviewItem.**
  `require_temporary_item_moderation` остаётся chief/root. agent
  может видеть review items (read) и temporary items, но не
  модерировать. Подтверждено Issue body.
- **R-5: agent + machines / issue-objects.**
  Issue не упоминает machines/issue-objects как часть запрета,
  но `machine_service` использует `has_global_business_access`
  (chief/root). agent → 403 на write. Read — открыть. Уточнить
  в Issue comment после старта.
- **R-6: agent в Django BFF.**
  BFF должен корректно проксировать agent-token. Существующий
  `apps/sync_client/client.py` это уже делает, если
  `SyncUserBinding` хранит правильный `role=agent`. Подтвердить
  при review.
- **R-7: PATCH /operations/{id} — site/type.**
  Текущая логика `update_operation` через
  `require_operate_site` блокирует agent. Нужна новая ветка
  «agent own draft only». Сложность — обработка `operation_type`
  change, MOVE site changes. Решение: agent не меняет
  `operation_type` и `site_id`; только строки и метаполя
  (notes, effective_at).

---

## 12. Execution Strategy

Последовательная (sequential) стратегия:

1. **M1 — Domain & Migration.**
   - Alembic revision `0038_add_agent_role.py`.
   - Pydantic literal `UserRole`.
   - `CANONICAL_ROLES` + `is_agent` property.
   - `AgentPolicy` module.
   - `require_admin_basic` оставлен без изменений.

2. **M2 — Catalog policy.**
   - Расширение `routes_catalog_admin.py` guards.
   - `AgentPolicy.filter_*_patch` применён в
     `catalog_admin_service.update_*`.
   - `routes_catalog_admin.py:batch` — apply allow-list.
   - delete/deactivate → 403 для agent.

3. **M3 — Operations policy.**
   - Расширение `OperationsPolicy`:
     `agent` в `CREATE_DRAFT_ROLES`, новый
     `require_agent_update_own_draft`, fail-closed submit/cancel
     submitted/restore.
   - Расширение `routes_operations.py` guards.

4. **M4 — Auth & admin.**
   - `routes_auth.py:auth_sites`/`auth_context` —
     `is_agent or has_global_business_access` для sites.
   - `routes_admin.py` (без изменений, но проверить, что
     `/admin/roles` уже включает `agent` после M1).

5. **M5 — Tests.**
   - `test_agent_role_authz.py` (новый).
   - Расширение существующих тестов.

6. **M6 — Bootstrap & scripts.**
   - `scripts/bootstrap_root.py --agent-username`.
   - `scripts/rotate_tokens.py --agent` (опционально).

7. **M7 — Documentation.**
   - DOMAIN_MODEL, API_REFERENCE, API_MAP.
   - `Role Matrix.md`, `Functional and WorkLogik.md`.
   - ADR-0030.
   - warehouse-storekeeper docs.

Каждый milestone — отдельный коммит в `dev` ветке SyncServer.
Параллельная работа между milestone'ами невозможна из-за общего
файла `users` (миграция) и общего `routes_catalog_admin.py`
(guards). Sequential — обязательно.

Для будущего Swarm (если задача разрастётся): independent
shards — M2 (catalog policy) и M3 (operations policy) могут
идти параллельно **после** M1, при условии, что `AgentPolicy`
и `is_agent` уже доступны. M5 (tests) — после M2+M3. M7 (docs)
— после M5. Maximum useful threads: 2 (M2 + M3) в стадии 2, 1
во всех остальных.

---

## 13. Required Follow-up Artifacts

- **ADR-0030** в `SyncServer/docs/adr/0030-agent-domain-role.md` —
  расширение `users.role` enum, серверные границы agent,
  явный отказ от catalog approval workflow.
- **TZ-FUNCTIONAL-agent-role** (если требуется) в
  `workspace/docs/TZ/` — фиксация расширения `Role Matrix.md`
  и `Functional and WorkLogik.md`.
- **Issue comment** в GitHub Issue #18 со ссылкой на эту TZ и
  на ADR-0030 (комментарий architect, не closing).

---

## 14. Definition of Done

1. Alembic revision `0038_add_agent_role.py` применяется на
   dev и prod (после code review) без потери данных.
2. `GET /api/v1/admin/roles` возвращает
   `["root","chief_storekeeper","storekeeper","observer","agent"]`.
3. `GET /api/v1/auth/me` и `/auth/context` с agent-token
   возвращают `role: "agent"` и корректный `permissions_summary`.
4. Agent может читать каталог, единицы, категории, склады,
   остатки, операции; может создавать Item/Category/Unit; может
   PATCH'ить только allow-listed поля; может вызывать
   `items/merge` и `categories/merge`.
5. Agent не может submit/accept/cancel submitted/restore
   операций; не может управлять пользователями/устройствами/
   складами/токенами.
6. Audit `actor_user_id` всегда равен UUID agent-user'а; в
   audit нигде не появляется actor=chief_storekeeper, когда
   HTTP-запрос выполнял agent.
7. Существующие 4 роли (root, chief_storekeeper, storekeeper,
   observer) не получают регрессий; все существующие тесты
   `python -m pytest` проходят.
8. Документация (DOMAIN_MODEL.md, Role Matrix.md,
   Functional and WorkLogik.md, API_MAP.md, ADR-0030,
   warehouse-storekeeper SKILL.md) обновлена.
9. Нет новых catalog approval / submission workflow.
10. `Identity` agent никогда не мапится в `has_global_business_access`;
    `_has_global_business_access` остаётся `(is_root or
    role == "chief_storekeeper")`.
