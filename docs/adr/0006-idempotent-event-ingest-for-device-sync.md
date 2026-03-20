# ADR-0006: Idempotent Event Ingest For Device Sync

## Status
Accepted

## Context
Device sync can resend batches or replay events. The service must accept safe retries while protecting server state from duplicate or colliding event writes.

## Decision
Treat sync ingest as idempotent at the event level. Event identity is tied to event UUID, with collision handling that distinguishes valid duplicates from conflicting payload reuse.

## Consequences

Pros:
- Safe client retries
- Clear duplicate handling semantics
- Better resilience for unstable device connectivity

Cons:
- Ingest logic is more complex than naive append-only writes
- Requires careful tests around duplicates and collisions

## Alternatives Considered

### Option 1
Blindly insert every event submission.

Why not chosen:
- Would create duplicate state and break sync correctness.

### Option 2
Make clients guarantee exactly-once delivery.

Why not chosen:
- Unrealistic for device sync and network retry scenarios.
