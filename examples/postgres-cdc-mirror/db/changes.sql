-- A day of activity on shop.orders: new orders, refunds, a cancelled order.
\connect shop
INSERT INTO orders (order_id, customer_id, amount, status, details)
SELECT g, 1000 + g % 50, 42.00, 'paid', '{"channel": "web"}' FROM generate_series(1001, 1020) g;
UPDATE orders SET status = 'refunded', updated_at = now() WHERE order_id IN (5, 17, 230);
DELETE FROM orders WHERE order_id = 999;
