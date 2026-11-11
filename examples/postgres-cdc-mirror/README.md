# PostgreSQL CDC: keep a mirror of a table up to date from its changes

`shop.orders` is the table of an application. `analytics.orders` is its mirror, for reporting. One Hydra ETL job reads the changes of `shop.orders` (inserts, updates, deletes) from PostgreSQL's logical replication and applies them to the mirror.

- **First run**: Hydra ETL creates the publication and the replication slot, copies the whole table, and creates `analytics.orders` with the same types (`bigint`, `numeric`, `jsonb`, `timestamptz`) and `order_id` as primary key.
- **Next runs**: only the changes since the last run, in the order of the transactions. Inserts and updates are upserted, deletes are applied.
- **A failed run loses nothing**: the load is all or nothing, and the slot only moves on after a successful load. The next run reads the same changes again.

```
jobs/orders_mirror/
  sources.yaml        # type: postgresql_cdc, slot + publication, table public.orders
  destinations.yaml   # PostgreSQL, upsert on order_id, atomic
  pipeline.yaml
workflows/            # sync.yaml + thread.yaml
db/                   # init.sql, changes.sql, break.sql, repair.sql, check.sql
```

## 1. Start a PostgreSQL with logical replication

```bash
docker run --name hydra-pg-cdc -e POSTGRES_PASSWORD=hydra -p 5433:5432 -d postgres:16 -c wal_level=logical
```

On an existing server: `ALTER SYSTEM SET wal_level = logical;` then restart PostgreSQL. The user of the source needs the `REPLICATION` attribute (`ALTER ROLE app_sync REPLICATION;`); `postgres` has it.

## 2. Install and configure

```bash
pip install "hydra-etl[postgres]"
cp .env.example .env
```

`.env` holds the connection of the container above (it is ignored by git).

On PowerShell, `cp` works as is, and each `docker exec -i hydra-pg-cdc psql -U postgres < db/file.sql` below becomes:

```powershell
Get-Content db/file.sql | docker exec -i hydra-pg-cdc psql -U postgres
```

## 3. Create the two databases

```bash
docker exec -i hydra-pg-cdc psql -U postgres < db/init.sql
```

## 4. First run: the whole table

```bash
hdrctl run .
docker exec -i hydra-pg-cdc psql -U postgres < db/check.sql
```

Both tables: 1,000 rows, the same total.

## 5. A day of changes

```bash
docker exec -i hydra-pg-cdc psql -U postgres < db/changes.sql
hdrctl run .
docker exec -i hydra-pg-cdc psql -U postgres < db/check.sql
```

20 new orders, 3 refunds, 1 deleted order: both tables have 1,019 rows, 3 refunded, the same total.

## 6. A failure in the middle of the load

The mirror refuses negative amounts. The shop updates 500 orders and records one order at -15.00:

```bash
docker exec -i hydra-pg-cdc psql -U postgres < db/break.sql
hdrctl run .
docker exec -i hydra-pg-cdc psql -U postgres < db/check.sql
```

The run fails on the negative amount, and the mirror is exactly as before: none of the 500 updates was applied. Fix the order at the source and run again:

```bash
docker exec -i hydra-pg-cdc psql -U postgres < db/repair.sql
hdrctl run .
docker exec -i hydra-pg-cdc psql -U postgres < db/check.sql
```

Both tables have 1,020 rows and the same total: the 500 updates of the failed run were read again, nothing was lost.

## Good to know

- Each row read from the source carries `_op` (`snapshot`, `insert`, `update`, `delete`), `_lsn` and `_commit_time`. In `upsert`, the PostgreSQL destination uses `_op` and does not write these columns; in `append`, it writes them all, which gives a log of the changes.
- A replication slot keeps the server's write-ahead log until the changes are read. A slot that is no longer used must be dropped: `SELECT pg_drop_replication_slot('hydra_orders');`.

## When the load keeps failing: protect the source

The slot only moves on after a successful load. That is what makes a failed run lose nothing, and it has a cost: while the mirror keeps failing, PostgreSQL keeps every WAL segment since the last success. A mirror broken over a weekend can fill the disk of the source.

**Hydra ETL checks the slot before each run** (`pg_replication_slots`):

| State | What Hydra ETL does |
| --- | --- |
| Retained WAL above `lag_warning_mb` (default 1024 MB) | Warning in the logs, the run goes on |
| Less than `lag_warning_mb` left before `max_slot_wal_keep_size` (`safe_wal_size`) | Warning, the run goes on |
| `wal_status = unreserved` | Warning: the slot will be invalidated at the next checkpoint unless this run succeeds |
| `wal_status = lost` (slot invalidated) | **The run fails** and says how to rebuild the mirror |

```yaml
connection:
  slot: hydra_orders
  publication: hydra_orders
  lag_warning_mb: 2048        # 0: never warn
```

**Cap the WAL a slot can hold** (PostgreSQL 13+):

```sql
ALTER SYSTEM SET max_slot_wal_keep_size = '20GB';
SELECT pg_reload_conf();
```

The disk is protected, but this is a trade-off: past the limit PostgreSQL invalidates the slot, and the changes made since the last success can no longer be read. Hydra ETL then stops instead of going on with a gap. To rebuild the mirror:

```sql
SELECT pg_drop_replication_slot('hydra_orders');
TRUNCATE analytics.orders;   -- rows deleted at the source during the gap would stay otherwise
```

Then `hdrctl run .`: a new slot, a full copy, and the changes again.

**Watch the slot** from your monitoring, whatever runs the job:

```sql
SELECT slot_name, active, wal_status, safe_wal_size,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots
WHERE slot_name = 'hydra_orders';
```

Alert on `retained_wal` growing run after run, and on `wal_status` leaving `reserved`.
- The source table needs a primary key, so that deletes and updates can be applied by key.
- A workflow with `rollback: true` cannot read a CDC source: the slot is confirmed at the end of the job and could not be moved back.
