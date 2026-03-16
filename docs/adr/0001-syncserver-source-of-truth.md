# ADR 0001: SyncServer as Source of Truth

## Status
Accepted

## Context
Multiple clients (web/mobile/offline) consume warehouse data and could diverge if business logic is distributed.

## Decision
All domain logic is centralized in SyncServer. Clients only call APIs.

## Consequences
- Consistent behavior across clients.
- Easier auditing and policy enforcement.
- Backend complexity increases.

## Alternatives considered
- Client-specific logic duplication.
- Shared client-side SDK with embedded business logic.
