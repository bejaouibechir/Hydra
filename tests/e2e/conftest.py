import pytest
import psycopg2

# ===== FIXTURES MYSQL (existantes - garder) =====
@pytest.fixture(scope="function")
def mysql_connection():
    """Connexion MySQL pour tests E2E."""
    # ... votre code MySQL existant ...
    pass

# ===== FIXTURES POSTGRESQL (nouvelles - ajouter) =====
@pytest.fixture(scope="function")
def pg_connection():
    """Connexion PostgreSQL pour tests E2E."""
    conn = psycopg2.connect(
        host="localhost",
        port=5432,  # postgres1
        user="postgres",
        password="postgres",
        database="postgres"
    )
    yield conn
    conn.close()

@pytest.fixture(scope="function")
def pg_connection2():
    """Connexion PostgreSQL container 2."""
    conn = psycopg2.connect(
        host="localhost",
        port=5431,  # postgres2
        user="postgres",
        password="postgres",
        database="postgres"
    )
    yield conn
    conn.close()

@pytest.fixture(scope="function", autouse=True)
def cleanup_pg_tables(pg_connection):
    """
    Auto-cleanup tables PostgreSQL e2e_*.
    
    FIX: Gère le cas où pg_connection est None (tests MongoDB).
    """
    yield
    
    # ✅ FIX: Vérifier si pg_connection existe avant de l'utiliser
    if pg_connection is not None:
        cursor = pg_connection.cursor()
        cursor.execute("TRUNCATE TABLE e2e_users RESTART IDENTITY CASCADE")
        cursor.execute("TRUNCATE TABLE e2e_inventory RESTART IDENTITY CASCADE")
        cursor.execute("TRUNCATE TABLE e2e_employees RESTART IDENTITY CASCADE")
        pg_connection.commit()