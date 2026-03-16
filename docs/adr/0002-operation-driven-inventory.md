# ADR 0002: Operation-Driven Inventory

## Status
Accepted

## Context
Inventory balances must be deterministic and reconstructible.

## Decision
Balances are derived through operations (`RECEIVE`, `WRITE_OFF`, `MOVE`) and their state transitions.

## Consequences
- Strong audit trail.
- Predictable recalculation model.
- Requires strict operation validation and lifecycle control.

## Alternatives considered
- Direct balance editing endpoints.
- Mixed model of direct edits plus operations.
