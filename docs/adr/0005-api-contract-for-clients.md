# ADR 0005: API Contract for Clients

## Status
Accepted

## Context
Different clients require stable and predictable API responses.

## Decision
Standardize list responses as:
```json
{
  "items": [],
  "total_count": 0,
  "page": 1,
  "page_size": 50
}
```
Entity responses return direct entity fields.

## Consequences
- Simplifies client integrations.
- Uniform pagination handling.
- Requires migration for older response shapes.

## Alternatives considered
- Route-specific custom list formats.
- Cursor-only pagination with no counts.
