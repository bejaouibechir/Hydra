-- Source database (shop) and mirror database (analytics), on the same PostgreSQL.
CREATE DATABASE shop;
CREATE DATABASE analytics;
\connect shop
CREATE TABLE orders (
  order_id    bigint PRIMARY KEY,
  customer_id bigint NOT NULL,
  amount      numeric(12,2) NOT NULL,
  status      text NOT NULL,
  details     jsonb,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
INSERT INTO orders
SELECT g, 1000 + g % 50, round((g * 7.31)::numeric % 900 + 10, 2), 'paid',
       jsonb_build_object('channel', CASE WHEN g % 3 = 0 THEN 'store' ELSE 'web' END),
       '2026-11-01 09:00:00+01'
FROM generate_series(1, 1000) g;
