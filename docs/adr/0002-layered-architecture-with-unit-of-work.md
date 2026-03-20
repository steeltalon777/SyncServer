# ADR-0002: Layered Architecture With Unit Of Work

## Status
Accepted

## Context
The codebase already separates HTTP routes, services, repositories, and ORM models. Request workflows often touch multiple repositories and need a single transaction boundary.

## Decision
Use a layered architecture:
- API routes for transport concerns
- Services for business logic
- Repositories for persistence
- SQLAlchemy ORM models for stored entities

Use `UnitOfWork` as the request-scoped transaction wrapper that exposes repositories over one session.

## Consequences

Pros:
- Clear responsibilities
- Easier reasoning for humans and AI tools
- Safer multi-repository workflows

Cons:
- More files and indirection
- Some simple flows still need multiple layers

## Alternatives Considered

### Option 1
Put business logic directly in route handlers.

Why not chosen:
- Makes handlers heavy and spreads invariants across HTTP code.

### Option 2
Use models as active-record style business objects.

Why not chosen:
- Does not match current SQLAlchemy repository-oriented structure.
