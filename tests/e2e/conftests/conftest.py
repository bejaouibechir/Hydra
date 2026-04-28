"""
Fixtures pytest pour tests E2E MySQL - Sprint 1 Backlog 3.2.

ADAPTÉ À HYDRA:
- Utilise containers MySQL existants (hydra_mysql_test:3307)
- S'intègre avec structure tests/ existante
- Compatible avec tests Docker existants
"""

import os
import time
from pathlib import Path
from typing import Generator, Dict, Any, List

try:
    import mysql.connector
    from mysql.connector import Error
    _MYSQL_AVAILABLE = True
except ImportError:
    _MYSQL_AVAILABLE = False
import pytest


# ============================================================
# Configuration MySQL Test (CONTAINERS EXISTANTS)
# ============================================================

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_TEST_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_TEST_PORT", "3307")),
    "user": os.getenv("MYSQL_TEST_USER", "hydra"),  # ✅ user hydra
    "password": os.getenv("MYSQL_TEST_PASSWORD", "hydra"),  # ✅ password hydra
    "database": os.getenv("MYSQL_TEST_DATABASE", "hydra_test"),
}


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="session")
def mysql_connection_config() -> Dict[str, Any]:
    """
    Configuration connexion MySQL pour les tests.
    
    Utilise hydra_mysql_test (port 3307) existant.
    """
    return MYSQL_CONFIG.copy()


@pytest.fixture(scope="session")
def wait_for_mysql(mysql_connection_config) -> None:
    """
    Attend que MySQL soit prêt avant de lancer les tests.
    
    Timeout: 30 secondes
    """
    max_retries = 10
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(**mysql_connection_config)
            conn.close()
            print(f"\n✅ MySQL ready (hydra_mysql_test:3307)")
            return
        except Error as e:
            if attempt < max_retries - 1:
                print(f"⏳ MySQL not ready (attempt {attempt + 1}/{max_retries}), retrying...")
                time.sleep(retry_delay)
            else:
                pytest.fail(f"❌ MySQL not available after {max_retries} attempts: {e}")


@pytest.fixture
def mysql_conn(mysql_connection_config, wait_for_mysql) -> Generator:
    """
    Fournit une connexion MySQL pour un test.
    
    - Auto-commit désactivé
    - Rollback automatique après le test
    - Fermeture automatique
    """
    conn = mysql.connector.connect(**mysql_connection_config)
    conn.autocommit = False
    
    yield conn
    
    try:
        conn.rollback()
        conn.close()
    except Exception:
        pass


@pytest.fixture
def ensure_test_tables(mysql_conn) -> None:
    """
    Crée les tables de test si elles n'existent pas.
    
    Tables créées:
    - e2e_users (id PRIMARY KEY)
    - e2e_sales (region, product_id PRIMARY KEY)
    - e2e_products (sku PRIMARY KEY)
    
    Préfixe 'e2e_' pour isolation des tests E2E.
    """
    cursor = mysql_conn.cursor()
    
    try:
        # Table users : clé simple
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS e2e_users (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # Table sales : clé composite
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS e2e_sales (
                region VARCHAR(50) NOT NULL,
                product_id VARCHAR(50) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (region, product_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # Table products : clé simple avec UNIQUE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS e2e_products (
                sku VARCHAR(50) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                price DECIMAL(10, 2),
                stock INT DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        mysql_conn.commit()
    finally:
        cursor.close()


@pytest.fixture
def clean_tables(mysql_conn, ensure_test_tables) -> Generator:
    """
    Nettoie les tables avant et après chaque test.
    
    Tables nettoyées:
    - e2e_users
    - e2e_sales
    - e2e_products
    """
    tables = ["e2e_users", "e2e_sales", "e2e_products"]
    
    def truncate_all():
        cursor = mysql_conn.cursor()
        try:
            for table in tables:
                cursor.execute(f"TRUNCATE TABLE {table}")
            mysql_conn.commit()
        finally:
            cursor.close()
    
    # Nettoyer avant le test
    truncate_all()
    
    yield
    
    # Nettoyer après le test
    truncate_all()


@pytest.fixture
def db_helper(mysql_conn):
    """
    Helper pour opérations DB communes dans les tests.
    """
    class DBHelper:
        def __init__(self, connection):
            self.conn = connection
        
        def insert(self, table: str, data: Dict[str, Any]) -> None:
            """Insert une ligne."""
            columns = ", ".join(data.keys())
            placeholders = ", ".join(["%s"] * len(data))
            sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            
            cursor = self.conn.cursor()
            try:
                cursor.execute(sql, list(data.values()))
                self.conn.commit()
            finally:
                cursor.close()
        
        def select_all(self, table: str, order_by: str = None) -> List[Dict[str, Any]]:
            """Sélectionne toutes les lignes."""
            sql = f"SELECT * FROM {table}"
            if order_by:
                sql += f" ORDER BY {order_by}"
            
            cursor = self.conn.cursor(dictionary=True)
            try:
                cursor.execute(sql)
                return cursor.fetchall()
            finally:
                cursor.close()
        
        def select_where(self, table: str, where: Dict[str, Any]) -> List[Dict[str, Any]]:
            """Sélectionne avec condition WHERE."""
            conditions = " AND ".join([f"{k} = %s" for k in where.keys()])
            sql = f"SELECT * FROM {table} WHERE {conditions}"
            
            cursor = self.conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, list(where.values()))
                return cursor.fetchall()
            finally:
                cursor.close()
        
        def count(self, table: str) -> int:
            """Compte le nombre de lignes."""
            cursor = self.conn.cursor()
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                return cursor.fetchone()[0]
            finally:
                cursor.close()
    
    return DBHelper(mysql_conn)


@pytest.fixture
def temp_job_dir(tmp_path) -> Path:
    """
    Crée un répertoire temporaire pour un job ETL.
    """
    job_dir = tmp_path / "test_job_e2e"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


# ============================================================
# Markers
# ============================================================

def pytest_configure(config):
    """Configure les markers personnalisés."""
    config.addinivalue_line(
        "markers", "e2e: Tests end-to-end avec base de données réelle"
    )
    config.addinivalue_line(
        "markers", "slow: Tests lents (>1s)"
    )


# ============================================================
# Résumé Fixtures
# ============================================================

"""
Fixtures disponibles pour tests E2E:

SESSION:
- mysql_connection_config : Dict config MySQL (hydra_mysql_test:3307)
- wait_for_mysql : Attend que MySQL soit prêt

FUNCTION:
- mysql_conn : Connexion MySQL avec rollback auto
- ensure_test_tables : Crée tables e2e_* si nécessaire
- clean_tables : Nettoie tables avant/après test
- db_helper : Helpers INSERT/SELECT/COUNT
- temp_job_dir : Répertoire temporaire pour job ETL

Tables créées:
- e2e_users (id PK)
- e2e_sales (region, product_id PK)
- e2e_products (sku PK)

Préfixe 'e2e_' pour isolation.
"""