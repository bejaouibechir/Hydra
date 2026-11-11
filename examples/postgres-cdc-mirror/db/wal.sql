-- The shop keeps working: about 30 MB of WAL in a table that is not mirrored.
\connect shop
CREATE TABLE IF NOT EXISTS wal_filler (id bigint, payload text);
INSERT INTO wal_filler SELECT g, md5(g::text) FROM generate_series(1, 300000) g;
SELECT slot_name, wal_status,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots;
