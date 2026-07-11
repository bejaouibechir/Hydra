-- Seed MariaDB (Hydra tests)
-- Ce script est exécuté automatiquement au 1er lancement du conteneur MariaDB.

USE hydra_test;

DROP TABLE IF EXISTS employees;
CREATE TABLE employees (
  id INT PRIMARY KEY AUTO_INCREMENT,
  full_name VARCHAR(120) NOT NULL,
  email VARCHAR(180) NOT NULL,
  age INT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO employees (full_name, email, age) VALUES
('Alice Martin', 'alice@corp.tld', 31),
('Karim Ben Salah', 'karim@corp.tld', 28),
('Sana Trabelsi', 'sana@corp.tld', 35);