# ADR 0004: Balance Calculation Strategy

## Status
Accepted

## Context
Balance changes must align with operation semantics and support rollback.

## Decision
Apply deterministic deltas on submit:
- RECEIVE: `+qty` at operation site
- WRITE_OFF: `-qty` at operation site
- MOVE: `-qty` source, `+qty` target
Rollback inverse deltas on cancellation of submitted operations.

## Consequences
- Consistent stock movement model.
- Easy rollback behavior.
- Requires transaction safety and row locking.

## Alternatives considered
- Snapshot-only balances without movement deltas.
- Eventual async rebalance job as primary source.
