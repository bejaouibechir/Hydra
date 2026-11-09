-- Fix the wrong order at the source.
\connect shop
UPDATE orders SET amount = 15.00 WHERE order_id = 1021;
