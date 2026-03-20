# ADR-0004: Token Auth And Site-Scoped Access

## Status
Accepted

## Context
The service supports user clients, admin clients, and device sync clients. Access is not uniform: some permissions are global, others are site-specific.

## Decision
Use token-based authentication as the primary API contract:
- `X-User-Token` for user/admin requests
- `X-Device-Token` for device sync flows

Use access control based on:
- `User.is_root` for global authority
- `UserAccessScope` for site-scoped permissions with flags:
  - `can_view`
  - `can_operate`
  - `can_manage_catalog`

## Consequences

Pros:
- Simple integration contract for clients
- Clear distinction between global and scoped authority
- Fits current admin and device workflows

Cons:
- Token handling must be treated as sensitive
- Some compatibility auth paths still remain in the codebase

## Alternatives Considered

### Option 1
Use only session-based auth.

Why not chosen:
- Does not match cross-client API integration needs.

### Option 2
Use only role-based access without per-site scopes.

Why not chosen:
- Would not model current warehouse permission requirements.
