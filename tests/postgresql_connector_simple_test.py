"""
Tests unitaires PostgreSQLConnector - Version Hydra

Tests simples sans dependances externes.
Compatible avec la structure Hydra existante.

Pour lancer les tests (depuis le dossier racine Hydra):
    python -m pytest tests/test_postgresql_connector_simple.py -v
    
    OU sans pytest :
    python tests/test_postgresql_connector_simple.py
"""

import sys
import os

# Ajouter le repertoire racine au PYTHONPATH pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

# Import depuis internal.connector
from internal.connector.postgresql_connector import PostgreSQLConnector


def test_parse_table():
    """Test parsing table."""
    config = {
        "type": "postgresql",
        "connection": {
            "user": "test",
            "database": "test_db",
        }
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    # Simple
    schema, table = conn._parse_table("users")
    assert schema == "public" and table == "users", f"Expected ('public', 'users'), got ({schema}, {table})"
    
    # Avec schema
    schema, table = conn._parse_table("sales.customers")
    assert schema == "sales" and table == "customers", f"Expected ('sales', 'customers'), got ({schema}, {table})"
    
    print("OK test_parse_table PASSED")


def test_validate_identifier():
    """Test validation identifiants."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    # Valides
    assert conn._validate_identifier("users") == "users"
    assert conn._validate_identifier("user_accounts") == "user_accounts"
    assert conn._validate_identifier("_internal") == "_internal"
    
    # Invalides
    try:
        conn._validate_identifier("user accounts")
        assert False, "Should reject spaces"
    except ValueError:
        pass
    
    try:
        conn._validate_identifier("123table")
        assert False, "Should reject starting with number"
    except ValueError:
        pass
    
    print("OK test_validate_identifier PASSED")


def test_quote_identifier():
    """Test quoting identifiants."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    quoted = conn._quote_identifier("public", "users")
    assert quoted == '"public"."users"', f"Expected '\"public\".\"users\"', got {quoted}"
    
    print("OK test_quote_identifier PASSED")


def test_build_insert_sql():
    """Test generation SQL INSERT."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    batch = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    
    sql, values = conn._build_insert_sql(
        schema="public",
        table="users",
        columns=["id", "name"],
        batch=batch,
    )
    
    assert 'INSERT INTO "public"."users"' in sql
    assert '"id", "name"' in sql
    assert "VALUES (%s, %s)" in sql
    assert len(values) == 2
    assert values[0] == (1, "Alice")
    assert values[1] == (2, "Bob")
    
    print("OK test_build_insert_sql PASSED")


def test_build_upsert_sql_simple():
    """Test generation SQL UPSERT cle simple."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    batch = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
    ]
    
    sql, values = conn._build_upsert_sql(
        schema="public",
        table="users",
        columns=["id", "name", "email"],
        key=["id"],
        batch=batch,
    )
    
    # Verifications
    assert 'INSERT INTO "public"."users"' in sql
    assert 'ON CONFLICT ("id")' in sql
    assert 'DO UPDATE SET' in sql
    assert '"name" = EXCLUDED."name"' in sql
    assert '"email" = EXCLUDED."email"' in sql
    # id ne doit pas etre dans UPDATE
    assert '"id" = EXCLUDED."id"' not in sql
    
    assert len(values) == 1
    assert values[0] == (1, "Alice", "alice@example.com")
    
    print("OK test_build_upsert_sql_simple PASSED")


def test_build_upsert_sql_composite():
    """Test generation SQL UPSERT cle composite."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    batch = [
        {"region": "EU", "product_id": "P1", "stock": 100},
    ]
    
    sql, values = conn._build_upsert_sql(
        schema="public",
        table="inventory",
        columns=["region", "product_id", "stock"],
        key=["region", "product_id"],
        batch=batch,
    )
    
    assert 'ON CONFLICT ("region", "product_id")' in sql
    assert '"stock" = EXCLUDED."stock"' in sql
    assert '"region" = EXCLUDED."region"' not in sql
    
    print("OK test_build_upsert_sql_composite PASSED")


def test_build_upsert_do_nothing():
    """Test generation SQL DO NOTHING."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    batch = [{"id": 1}]
    
    sql, values = conn._build_upsert_do_nothing_sql(
        schema="public",
        table="users",
        columns=["id"],
        key=["id"],
        batch=batch,
    )
    
    assert 'ON CONFLICT ("id")' in sql
    assert "DO NOTHING" in sql
    assert "DO UPDATE" not in sql
    
    print("OK test_build_upsert_do_nothing PASSED")


def test_validate_upsert_key_success():
    """Test validation contrainte unique reussie."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    cursor_mock = MagicMock()
    cursor_mock.fetchall.return_value = [
        {"constraint_name": "users_pkey", "constraint_cols": ["id"]},
    ]
    
    # Ne doit pas lever d'exception
    try:
        conn._validate_upsert_key(
            cursor=cursor_mock,
            schema="public",
            table="users",
            key=["id"],
        )
        print("OK test_validate_upsert_key_success PASSED")
    except Exception as e:
        print(f"FAIL test_validate_upsert_key_success FAILED: {e}")
        sys.exit(1)


def test_validate_upsert_key_no_constraint():
    """Test validation echoue si aucune contrainte."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    cursor_mock = MagicMock()
    cursor_mock.fetchall.return_value = []
    
    try:
        conn._validate_upsert_key(
            cursor=cursor_mock,
            schema="public",
            table="users",
            key=["id"],
        )
        print("FAIL test_validate_upsert_key_no_constraint FAILED: should have raised")
        sys.exit(1)
    except ValueError as e:
        if "aucune contrainte" in str(e):
            print("OK test_validate_upsert_key_no_constraint PASSED")
        else:
            print(f"FAIL Wrong error message: {e}")
            sys.exit(1)


def test_validate_upsert_key_composite_match():
    """Test validation cle composite ordre different."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    cursor_mock = MagicMock()
    cursor_mock.fetchall.return_value = [
        {"constraint_name": "inv_pk", "constraint_cols": ["region", "product_id"]},
    ]
    
    # Ordre different mais set matching
    try:
        conn._validate_upsert_key(
            cursor=cursor_mock,
            schema="public",
            table="inventory",
            key=["product_id", "region"],  # Ordre inverse
        )
        print("OK test_validate_upsert_key_composite_match PASSED")
    except Exception as e:
        print(f"FAIL test_validate_upsert_key_composite_match FAILED: {e}")
        sys.exit(1)


def test_infer_columns_from_batch():
    """Test inference colonnes."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    batch = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    
    cols = conn._infer_columns_from_batch(batch)
    assert cols == ["id", "name"], f"Expected ['id', 'name'], got {cols}"
    
    print("OK test_infer_columns_from_batch PASSED")


def test_capabilities():
    """Test capabilities."""
    config = {
        "type": "postgresql",
        "connection": {"user": "test", "database": "test_db"}
    }
    conn = PostgreSQLConnector(name="test", config=config)
    
    assert conn.supports_extract() is True
    assert conn.supports_load() is True
    
    caps = conn.get_capabilities()
    assert caps["supports_extract"] is True
    assert caps["supports_load"] is True
    assert caps["supports_upsert"] is True
    assert caps["supports_incremental"] is False
    
    print("OK test_capabilities PASSED")


def run_all_tests():
    """Lance tous les tests."""
    print("=" * 60)
    print("TESTS UNITAIRES POSTGRESQL CONNECTOR")
    print("=" * 60)
    
    test_parse_table()
    test_validate_identifier()
    test_quote_identifier()
    test_build_insert_sql()
    test_build_upsert_sql_simple()
    test_build_upsert_sql_composite()
    test_build_upsert_do_nothing()
    test_validate_upsert_key_success()
    test_validate_upsert_key_no_constraint()
    test_validate_upsert_key_composite_match()
    test_infer_columns_from_batch()
    test_capabilities()
    
    print("=" * 60)
    print("OK TOUS LES TESTS PASSED (12/12)")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()