# Diagnostics UI Events — TTL Cleanup

**Owner:** SyncServer ops
**Status:** Documented, not implemented in this TZ.

The `diagnostics_ui_events` table is append-only. To prevent unbounded growth, the
table must be cleaned up periodically.

## Strategy

Per `docs/contracts/DIAGNOSTICS_CONTRACTS.md` §10:

- **Retention:** 30 days (`received_at < NOW() - INTERVAL '30 days'`)
- **Schedule:** Once per day, off-peak
- **Batched deletes:** `LIMIT 20000` rows per run to avoid long locks

## SQL

```sql
DELETE FROM diagnostics_ui_events
WHERE id IN (
    SELECT id FROM diagnostics_ui_events
    WHERE received_at < NOW() - INTERVAL '30 days'
    ORDER BY received_at
    LIMIT 20000
);
```

## Scheduling

### Option A: pg_cron (recommended for self-contained ops)

```sql
-- One-time setup
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule daily at 03:00 UTC
SELECT cron.schedule(
    'diagnostics-ui-events-cleanup',
    '0 3 * * *',
    $$ DELETE FROM diagnostics_ui_events
       WHERE id IN (
         SELECT id FROM diagnostics_ui_events
         WHERE received_at < NOW() - INTERVAL '30 days'
         ORDER BY received_at LIMIT 20000
       ); $$
);
```

### Option B: system cron + psql

Add to `/etc/cron.d/warehouse-diag-cleanup`:

```
0 3 * * *  postgres  psql -d warehouse -c "DELETE FROM diagnostics_ui_events WHERE id IN (SELECT id FROM diagnostics_ui_events WHERE received_at < NOW() - INTERVAL '30 days' ORDER BY received_at LIMIT 20000);"
```

## Out of scope (this TZ)

- Setting up pg_cron or system cron in the deployment
- Monitoring the cleanup job
- Alerts on backup growth

These are operational concerns handled by the SRE team.
