CREATE DATABASE IF NOT EXISTS crm;
USE crm;
DROP TABLE IF EXISTS clients;
CREATE TABLE clients (
  custkey          INT PRIMARY KEY,
  client_name      VARCHAR(40)  NOT NULL,
  account_manager  VARCHAR(40)  NOT NULL,
  tier             VARCHAR(10)  NOT NULL,
  country          VARCHAR(30)  NOT NULL
);
SET SESSION cte_max_recursion_depth = 200000;
INSERT INTO clients (custkey, client_name, account_manager, tier, country)
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 150000)
SELECT i,
       CONCAT('Client#', LPAD(i, 9, '0')),
       ELT(1 + (i % 5), 'Sarah Martin', 'Karim Haddad', 'Lucia Romero', 'Tom Becker', 'Ines Dupont'),
       CASE WHEN i % 20 = 0 THEN 'Platinum'
            WHEN i % 7  = 0 THEN 'Gold'
            WHEN i % 3  = 0 THEN 'Silver'
            ELSE 'Bronze' END,
       ELT(1 + (i % 6), 'France', 'Germany', 'Spain', 'Tunisia', 'Canada', 'Japan')
FROM n;
SELECT tier, COUNT(*) AS clients FROM clients GROUP BY tier ORDER BY clients DESC;
