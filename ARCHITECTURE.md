# ARCHITECTURE

## Layered architecture

Clients
↓
SyncServer API (FastAPI routes)
↓
Service layer (business rules + orchestration)
↓
Repository layer (SQLAlchemy queries only)
↓
PostgreSQL

## Layer responsibilities

### API layer
- Authentication/authorization checks
- Request parsing and validation
- Mapping API contracts to service calls
- HTTP status and response serialization

### Service layer
- Warehouse business logic
- Operation workflow and invariants
- Balance update rules
- Cross-repository orchestration

### Repository layer
- ORM query composition and persistence
- Row locking and data retrieval
- No business rules

### Models
- SQLAlchemy ORM entities
- DB constraints and relationships

## Inventory model
- Inventory state is operation-driven.
- Operation statuses: `draft -> submitted -> cancelled`.
- Balances are updated only on submit.
- Cancelling a submitted operation applies reverse deltas.
