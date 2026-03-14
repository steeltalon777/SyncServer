# MEMORY

## Core entities
- Users
- Sites
- UserSiteAccess (user-site roles)
- Units, Categories, Items
- Operations, OperationLines
- Balances (item quantity per site)

## Operation workflow
- New operations start as `draft`.
- Only `submitted` operations affect balances.
- `cancelled` means draft cancellation or submitted rollback.

## Balance rules
- RECEIVE: `site += qty`
- WRITE_OFF: `site -= qty` (must have enough stock)
- MOVE: `source -= qty`, `target += qty` (source stock required)

## API design decisions
- Layered routing and service orchestration.
- Paginated list responses use:
  - `items`
  - `total_count`
  - `page`
  - `page_size`
- Entity responses return object fields directly.

## Source-of-truth rule
- Any domain rule change must be implemented in SyncServer services.
- Clients are integration consumers only.
