-- Rebuilds the mirror after an invalidated slot: drop the slot, empty the mirror,
-- give the server back its default WAL limit. The next run copies the table again.
SELECT pg_drop_replication_slot('hydra_orders');
ALTER SYSTEM RESET max_slot_wal_keep_size;
SELECT pg_reload_conf();
\connect analytics
TRUNCATE orders;
