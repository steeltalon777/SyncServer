# Memory

## System Architecture

- `SyncServer` is an async FastAPI backend
- Request flow is `route -> service -> UnitOfWork / repos -> PostgreSQL`
- The service is the authoritative source of warehouse data and business rules

## Core Entities

- `User`, `UserAccessScope`, `Site`, `Device`
- `Category`, `Unit`, `Item`, `TemporaryItem`, `InventorySubject`
- `Operation`, `OperationLine`
- `Balance`, `PendingAcceptanceBalance`, `LostAssetBalance`, `IssuedAssetBalance`, `OperationAcceptanceAction`
- `Recipient`, `RecipientAlias`
- `Document`, `DocumentOperation`, `DocumentSource`
- `Event`

## Data Model Decisions

- Inventory state is derived from operations and inventory subjects
- Balances are stored per `(site_id, inventory_subject_id)`
- Temporary items receive their own `InventorySubject` and can later be resolved to catalog items
- Documents store versioned payload snapshots with hashes
- Sync events are stored by `event_uuid` and ordered by `server_seq`

## API Design

- One versioned API surface under `/api/v1`
- User auth via `X-User-Token`; device auth via `X-Device-Token`
- Routes stay thin; services enforce invariants
- Root/admin flows and business/user flows share the same API surface with permission checks

## Business Rules

- Root users have global access; non-root users are constrained by `UserAccessScope`
- Operations follow a restricted lifecycle and may drive acceptance workflows
- Stock mutations happen through operation service logic, not direct balance editing
- Catalog master data is global and protected by access checks

## Known Pitfalls

- Some catalog reads accept `site_id` as access context rather than true data partition
- Device token can be optional for some user-authenticated flows but still influences audit context
- Acceptance and lost-asset workflows create extra derived state that must stay consistent with operations
- Existing databases require migrations before startup; the web process does not run Alembic automatically

## Future Architecture

- Expand client-facing integration docs and stand validation
- Continue hardening read models, sync workflows, and acceptance workflows
- Keep new integrations on the same service/repository/UnitOfWork architecture
