-- Caps the WAL a slot may hold (1 MB: demo only), then the shop keeps writing.
-- The slot falls behind more than the limit: PostgreSQL invalidates it.
ALTER SYSTEM SET max_slot_wal_keep_size = '1MB';
SELECT pg_reload_conf();
\connect shop
INSERT INTO wal_filler SELECT g, md5(g::text) FROM generate_series(1, 300000) g;
SELECT pg_switch_wal();
CHECKPOINT;
INSERT INTO wal_filler SELECT g, md5(g::text) FROM generate_series(1, 300000) g;
SELECT pg_switch_wal();
CHECKPOINT;
SELECT slot_name, wal_status, safe_wal_size FROM pg_replication_slots;
