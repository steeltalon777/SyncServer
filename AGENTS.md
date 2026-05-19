# SyncServer Agent Contract

## Role

`SyncServer` is the authoritative backend and the only source of truth for warehouse domain data.

## Functional Requirements Authority

- `Functional and WorkLogik.md` at the workspace root is the **canonical functional requirements document** for operation types, user roles, lifecycle rules, and domain behaviour.
- Before implementing any new service, endpoint, or business rule, re-read the relevant section of `Functional and WorkLogik.md` and confirm alignment.
- Deviations require a documented rationale in an ADR.

## Rules

- Keep API routes thin: auth wiring, request parsing, response mapping.
- Put business rules in `app/services/`.
- Put persistence details in `app/repos/` behind `UnitOfWork`.
- Do not bypass `app/services/uow.py` for mutations.
- Do not add client-specific business logic here unless it is a server-side rule that all clients must share.
- Keep `/api/v1` as the primary API surface. Treat `/business/*` compatibility routes as non-primary.

## Git Rules

- Agents may commit completed SyncServer changes after relevant checks/tests pass.
- Commit only from the `dev` branch.
- Switching from `dev` to another branch is forbidden by default.
- If the branch is not `dev`, warn the user and do not commit until the user gives an explicit command.
- If checks/tests fail, are unavailable, or were not run, do not commit and ask the user what to do.
- Git push is completely forbidden; the user pushes manually.

## Sensitive Areas

- `app/services/operations_service.py`
- `app/services/operations_policy.py`
- `app/services/uow.py`
- `app/services/identity_service.py`
- `app/services/catalog_admin_service.py`
- `alembic/versions/`

## Verification

- Default: `python -m pytest`
- Stand tests are opt-in through `pytest.ini` markers and env vars.
- Migration changes require `python -m alembic upgrade head` against a safe database.
