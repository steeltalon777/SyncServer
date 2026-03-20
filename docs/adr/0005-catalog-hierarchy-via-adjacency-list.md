# ADR-0005: Catalog Hierarchy Via Adjacency List

## Status
Accepted

## Context
Categories form a hierarchy and must support parent-child relationships, tree reads, and validation against cycles.

## Decision
Represent the category hierarchy with an adjacency-list model using `parent_id`, then build the tree in application code and validate parent changes to prevent cycles.

## Consequences

Pros:
- Simple relational model
- Easy CRUD behavior
- Straightforward tree materialization in code

Cons:
- Tree assembly happens outside the database
- Cycle checks require explicit application logic

## Alternatives Considered

### Option 1
Store denormalized nested tree blobs.

Why not chosen:
- Harder to update incrementally and validate safely.

### Option 2
Use a more complex tree storage strategy from the start.

Why not chosen:
- Not necessary for the current repository size and use cases.
