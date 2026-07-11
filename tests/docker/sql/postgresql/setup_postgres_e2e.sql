-- Setup PostgreSQL pour tests E2E Hydra
-- Sprint 2 - PostgreSQL Connector

-- =============================================================
-- 1. Tables de test
-- =============================================================

-- Table simple avec PRIMARY KEY
CREATE TABLE IF NOT EXISTS e2e_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE
);

-- Table avec clé composite
CREATE TABLE IF NOT EXISTS e2e_inventory (
    region VARCHAR(10) NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (region, product_id)
);

-- Table pour test upsert custom update_columns
CREATE TABLE IF NOT EXISTS e2e_employees (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    salary DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- 2. Données initiales (pour tests upsert)
-- =============================================================

-- e2e_users : données existantes
INSERT INTO e2e_users (name, email) VALUES
    ('Alice', 'alice@example.com'),
    ('Bob', 'bob@example.com')
ON CONFLICT (email) DO NOTHING;

-- e2e_inventory : stock initial
INSERT INTO e2e_inventory (region, product_id, stock) VALUES
    ('EU', 'P001', 100),
    ('US', 'P001', 150),
    ('EU', 'P002', 200)
ON CONFLICT (region, product_id) DO NOTHING;

-- e2e_employees : salaires initiaux
INSERT INTO e2e_employees (id, name, email, salary, created_at) VALUES
    (1, 'Charlie', 'charlie@company.com', 50000.00, '2024-01-01 10:00:00'),
    (2, 'Diana', 'diana@company.com', 60000.00, '2024-01-01 10:00:00')
ON CONFLICT (id) DO NOTHING;

-- =============================================================
-- 3. Vues de vérification
-- =============================================================

-- Vue pour compter les tables e2e
CREATE OR REPLACE VIEW e2e_tables_summary AS
SELECT 
    'e2e_users' AS table_name,
    COUNT(*) AS row_count
FROM e2e_users
UNION ALL
SELECT 
    'e2e_inventory',
    COUNT(*)
FROM e2e_inventory
UNION ALL
SELECT 
    'e2e_employees',
    COUNT(*)
FROM e2e_employees;

-- =============================================================
-- 4. Fonction de cleanup
-- =============================================================

CREATE OR REPLACE FUNCTION cleanup_e2e_tables() 
RETURNS void AS $$
BEGIN
    TRUNCATE TABLE e2e_users RESTART IDENTITY CASCADE;
    TRUNCATE TABLE e2e_inventory RESTART IDENTITY CASCADE;
    TRUNCATE TABLE e2e_employees RESTART IDENTITY CASCADE;
END;
$$ LANGUAGE plpgsql;

-- =============================================================
-- 5. Vérifications
-- =============================================================

-- Afficher les tables créées
SELECT tablename 
FROM pg_tables 
WHERE tablename LIKE 'e2e_%'
ORDER BY tablename;

-- Afficher les contraintes
SELECT 
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    array_agg(kcu.column_name ORDER BY kcu.ordinal_position) as columns
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu 
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
WHERE tc.table_name LIKE 'e2e_%'
    AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
ORDER BY tc.table_name, tc.constraint_type;

-- Afficher le résumé
SELECT * FROM e2e_tables_summary;