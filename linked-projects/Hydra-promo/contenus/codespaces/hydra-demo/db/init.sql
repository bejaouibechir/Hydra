-- Runs once, when the MySQL container is first created.
-- Hydra writes into an existing table; it does not create one.
CREATE TABLE IF NOT EXISTS orders (
  order_id INT PRIMARY KEY,
  customer VARCHAR(80),
  region   VARCHAR(20),
  amount   DECIMAL(12,2)
);
