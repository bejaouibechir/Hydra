"""
Tests E2E PostgreSQL Connector - Sprint 2

Tests avec vrais containers Docker postgres1 et postgres2.

Ports utilises:
- postgres1: localhost:5432
- postgres2: localhost:5431

Scenarios testes:
1. Load append
2. Load replace
3. Load upsert cle simple
4. Load upsert cle composite
5. Extract table
6. Extract query

Prerequis:
- Containers postgres1 (5432) et postgres2 (5431) actifs
- User postgres / password postgres
- Tables e2e_* creees via setup_postgres_e2e.sql
"""

import pytest

pytestmark = pytest.mark.skip(reason="E2E: requires live PostgreSQL containers")

import sys
import os

# Ajouter le repertoire racine au PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector


def get_test_connector(container="postgres1"):
    """Cree un connector de test."""
    ports = {
        "postgres1": 5432,
        "postgres2": 5431,
    }
    
    config = {
        "type": "postgresql",
        "connection": {
            "host": "localhost",
            "port": ports[container],
            "user": "postgres",
            "password": "postgres",
            "database": "postgres",
            "schema": "public",
        }
    }
    return PostgreSQLConnector(name=f"test_pg_{container}", config=config)


def test_load_append():
    """Test load mode append."""
    print("\nTest 1: Load Append")
    
    conn = get_test_connector("postgres1")
    
    # Donnees a inserer
    batches = [
        [
            {"id": 100, "name": "Test User 1", "email": "test1@example.com"},
            {"id": 101, "name": "Test User 2", "email": "test2@example.com"},
        ]
    ]
    
    try:
        # Cleanup
        cleanup_table(conn, "e2e_users")
        
        # Load
        conn.load_batches(
            batches=batches,
            table="e2e_users",
            mode="append"
        )
        
        # Verification
        result = extract_all(conn, "e2e_users")
        assert len(result) == 2, f"Expected 2 rows, got {len(result)}"
        
        print("OK Load append OK")
    except Exception as e:
        print(f"FAIL Load append FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_load_replace():
    """Test load mode replace (TRUNCATE puis INSERT)."""
    print("\nTest 2: Load Replace")
    
    conn = get_test_connector("postgres1")
    
    try:
        # Cleanup initial
        cleanup_table(conn, "e2e_users")
        
        # Insert initial
        batch1 = [[{"id": 200, "name": "Initial", "email": "initial@test.com"}]]
        conn.load_batches(batches=batch1, table="e2e_users", mode="append")
        
        # Replace
        batch2 = [[{"id": 201, "name": "Replaced", "email": "replaced@test.com"}]]
        conn.load_batches(batches=batch2, table="e2e_users", mode="replace")
        
        # Verification: seulement 1 row (ancienne supprimee)
        result = extract_all(conn, "e2e_users")
        assert len(result) == 1, f"Expected 1 row, got {len(result)}"
        assert result[0]["name"] == "Replaced"
        
        print("OK Load replace OK")
    except Exception as e:
        print(f"FAIL Load replace FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_load_upsert_simple_key():
    """Test load mode upsert avec cle simple."""
    print("\nTest 3: Load Upsert (cle simple)")
    
    conn = get_test_connector("postgres1")
    
    try:
        # Cleanup et insert initial
        cleanup_table(conn, "e2e_employees")
        batch_init = [[
            {"id": 1, "name": "Charlie", "email": "charlie@company.com", "salary": 50000.00},
            {"id": 2, "name": "Diana", "email": "diana@company.com", "salary": 60000.00},
        ]]
        conn.load_batches(batches=batch_init, table="e2e_employees", mode="append")
        
        # Upsert: UPDATE id=1, INSERT id=3
        batch_upsert = [[
            {"id": 1, "name": "Charlie Updated", "email": "charlie.new@company.com", "salary": 55000.00},
            {"id": 3, "name": "Eve", "email": "eve@company.com", "salary": 70000.00},
        ]]
        
        conn.load_batches(
            batches=batch_upsert,
            table="e2e_employees",
            mode="upsert",
            key=["id"]
        )
        
        # Verification
        result = extract_all(conn, "e2e_employees")
        assert len(result) == 3, f"Expected 3 rows, got {len(result)}"
        
        charlie = [r for r in result if r["id"] == 1][0]
        assert charlie["name"] == "Charlie Updated", f"Expected name updated, got {charlie['name']}"
        assert float(charlie["salary"]) == 55000.00
        
        print("OK Load upsert (simple key) OK")
    except Exception as e:
        print(f"FAIL Load upsert (simple key) FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_load_upsert_composite_key():
    """Test load mode upsert avec cle composite."""
    print("\nTest 4: Load Upsert (cle composite)")
    
    conn = get_test_connector("postgres1")
    
    try:
        # Cleanup et insert initial
        cleanup_table(conn, "e2e_inventory")
        batch_init = [[
            {"region": "EU", "product_id": "P001", "stock": 100},
            {"region": "US", "product_id": "P001", "stock": 150},
        ]]
        conn.load_batches(batches=batch_init, table="e2e_inventory", mode="append")
        
        # Upsert: UPDATE (EU, P001), INSERT (EU, P002)
        batch_upsert = [[
            {"region": "EU", "product_id": "P001", "stock": 120},  # UPDATE
            {"region": "EU", "product_id": "P002", "stock": 200},  # INSERT
        ]]
        
        conn.load_batches(
            batches=batch_upsert,
            table="e2e_inventory",
            mode="upsert",
            key=["region", "product_id"]
        )
        
        # Verification
        result = extract_all(conn, "e2e_inventory")
        assert len(result) == 3, f"Expected 3 rows, got {len(result)}"
        
        eu_p001 = [r for r in result if r["region"] == "EU" and r["product_id"] == "P001"][0]
        assert eu_p001["stock"] == 120, f"Expected stock=120, got {eu_p001['stock']}"
        
        print("OK Load upsert (composite key) OK")
    except Exception as e:
        print(f"FAIL Load upsert (composite key) FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_extract_table():
    """Test extract depuis table."""
    print("\nTest 5: Extract Table")
    
    conn = get_test_connector("postgres1")
    
    try:
        # Setup data
        cleanup_table(conn, "e2e_users")
        batch = [[
            {"id": 500, "name": "User A", "email": "a@test.com"},
            {"id": 501, "name": "User B", "email": "b@test.com"},
        ]]
        conn.load_batches(batches=batch, table="e2e_users", mode="append")
        
        # Extract
        result = []
        for batch in conn.extract_batches(table="e2e_users", batch_size=10):
            result.extend(batch)
        
        assert len(result) == 2, f"Expected 2 rows, got {len(result)}"
        
        print("OK Extract table OK")
    except Exception as e:
        print(f"FAIL Extract table FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_extract_query():
    """Test extract avec query custom."""
    print("\nTest 6: Extract Query")
    
    conn = get_test_connector("postgres1")
    
    try:
        # Setup
        cleanup_table(conn, "e2e_users")
        batch = [[
            {"id": 600, "name": "Active User", "email": "active@test.com"},
            {"id": 601, "name": "Inactive User", "email": "inactive@test.com"},
        ]]
        conn.load_batches(batches=batch, table="e2e_users", mode="append")
        
        # Extract avec filtre
        result = []
        query = "SELECT * FROM e2e_users WHERE name LIKE '%Active%'"
        for batch in conn.extract_batches(query=query, batch_size=10):
            result.extend(batch)
        
        assert len(result) == 1, f"Expected 1 row, got {len(result)}"
        assert result[0]["name"] == "Active User"
        
        print("OK Extract query OK")
    except Exception as e:
        print(f"FAIL Extract query FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# =============================================================
# Helpers
# =============================================================

def cleanup_table(conn, table):
    """Truncate une table."""
    import psycopg2
    
    # Determiner le port depuis la config du connector
    port = conn._conn_cfg.get("port", 5432)
    
    pg_conn = psycopg2.connect(
        host="localhost",
        port=port,
        user="postgres",
        password="postgres",
        database="postgres"
    )
    cursor = pg_conn.cursor()
    
    try:
        cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
        pg_conn.commit()
    finally:
        cursor.close()
        pg_conn.close()


def extract_all(conn, table):
    """Extract toutes les rows d'une table."""
    result = []
    for batch in conn.extract_batches(table=table, batch_size=1000):
        result.extend(batch)
    return result


def run_all_e2e_tests():
    """Lance tous les tests E2E."""
    print("=" * 70)
    print("TESTS E2E POSTGRESQL CONNECTOR")
    print("=" * 70)
    
    try:
        # Verifier connexion
        print("\nVerification connexion PostgreSQL...")
        
        import psycopg2
        
        # Test postgres1 (port 5432)
        pg_conn1 = psycopg2.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="postgres",
            database="postgres"
        )
        pg_conn1.close()
        print("OK Connexion postgres1 (port 5432) OK")
        
        # Test postgres2 (port 5431)
        pg_conn2 = psycopg2.connect(
            host="localhost",
            port=5431,
            user="postgres",
            password="postgres",
            database="postgres"
        )
        pg_conn2.close()
        print("OK Connexion postgres2 (port 5431) OK")
        
    except Exception as e:
        print(f"FAIL Connexion PostgreSQL FAILED: {e}")
        print("\nVerifiez que les containers sont actifs:")
        print("  docker ps | grep postgres")
        print("\nPorts attendus:")
        print("  postgres1: localhost:5432")
        print("  postgres2: localhost:5431")
        sys.exit(1)
    
    # Tests
    test_load_append()
    test_load_replace()
    test_load_upsert_simple_key()
    test_load_upsert_composite_key()
    test_extract_table()
    test_extract_query()
    
    print("\n" + "=" * 70)
    print("OK TOUS LES TESTS E2E PASSED (6/6)")
    print("=" * 70)


if __name__ == "__main__":
    # Check psycopg2
    try:
        import psycopg2
    except ImportError:
        print("FAIL psycopg2 non installe")
        print("Installer avec: pip install psycopg2-binary")
        sys.exit(1)
    
    run_all_e2e_tests()