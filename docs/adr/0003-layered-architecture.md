# ADR 0003: Layered Architecture (API -> Service -> Repository)

## Status
Accepted

## Context
Business logic and data access were at risk of mixing in route handlers.

## Decision
Enforce separation:
- API: validation/auth/request mapping
- Service: business rules/orchestration
- Repository: persistence/query logic

## Consequences
- Better maintainability/testability.
- Clear ownership boundaries.
- Slightly more boilerplate.

## Alternatives considered
- Fat route handlers.
- ActiveRecord-style logic inside models.
