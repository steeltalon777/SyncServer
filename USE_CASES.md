# USE_CASES

## 1) Device heartbeat (`/ping`)
1. Client sends site/device identity and token.
2. Server validates device access.
3. Server returns current `server_seq_upto` and server time.

## 2) Push new offline events (`/push`)
1. Client sends batch of events.
2. Server authenticates device and enforces batch/rate limits.
3. Each event is ingested idempotently:
   - accepted if new UUID,
   - duplicate if same UUID+payload,
   - rejected if UUID collision.
4. Server returns classification and max server sequence.

## 3) Pull incremental events (`/pull`)
1. Client sends `since_seq` cursor.
2. Server returns events for same site with `server_seq > since_seq` ordered ascending.
3. Client stores `next_since_seq` for next pull.

## 4) Sync catalog snapshots (`/catalog/items|categories|units`)
1. Client sends `updated_after` timestamp.
2. Server validates device and returns changed rows up to limit.
3. Client uses `next_updated_after` for incremental sync.

## 5) Read category hierarchy (`/catalog/categories/tree`)
1. Client requests full category tree.
2. Server builds tree and path arrays from adjacency list.
3. Client renders hierarchy.

## 6) Catalog admin create/update
1. Authorized device calls `/catalog/admin/*`.
2. Service validates uniqueness and foreign-key relations.
3. Category operations additionally validate no self-parent and no cycles.
4. Server commits and returns updated entity DTO.
