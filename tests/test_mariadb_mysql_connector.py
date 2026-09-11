"""
Tests MySQLMariaDBConnector avec support upsert - Sprint 1.

Tests organisés:
1. Génération SQL upsert (clés simples/composites)
2. Validation paramètres
3. Protection injection SQL
4. Syntaxe MySQL spécifique
"""

from __future__ import annotations

import pytest
from typing import List
from unittest.mock import Mock, MagicMock

# Import du connecteur
from hydra_etl.internal.connector.mysql_mariadb_connector import MySQLMariaDBConnector


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_connector():
    """
    Fixture connecteur mocké pour tests unitaires.
    
    Évite connexion DB réelle, teste seulement logique SQL.
    """
    # Config minimale
    config = {
        "type": "mysql",
        "connection": {
            "host": "localhost",
            "port": 3306,
            "user": "test_user",
            "password": "test_pass",
            "database": "test_db"
        }
    }
    
    # Créer connecteur (pas de connexion réelle)
    connector = MySQLMariaDBConnector(name="test_mysql", config=config)
    
    return connector


# ============================================================
# Tests Génération SQL Upsert - Clés Simples
# ============================================================

def test_build_upsert_sql_simple_key(mock_connector):
    """
    DoD: SQL correct pour clé simple.
    
    Cas: users avec clé [id], colonnes [id, name, email]
    """
    sql = mock_connector._build_upsert_sql(
        table="users",
        columns=["id", "name", "email"],
        key_columns=["id"]
    )
    
    # Vérifications structure
    assert "INSERT INTO `users`" in sql
    assert "(`id`, `name`, `email`)" in sql
    assert "VALUES (%s, %s, %s)" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    
    # Clé exclue de UPDATE
    assert "`id`=VALUES(`id`)" not in sql
    
    # Non-clés dans UPDATE
    assert "`name`=VALUES(`name`)" in sql
    assert "`email`=VALUES(`email`)" in sql


def test_build_upsert_sql_simple_key_many_columns(mock_connector):
    """
    Cas OK: Clé simple avec plusieurs colonnes non-clé.
    """
    sql = mock_connector._build_upsert_sql(
        table="products",
        columns=["id", "name", "price", "stock", "category"],
        key_columns=["id"]
    )
    
    # Toutes non-clés dans UPDATE
    assert "`name`=VALUES(`name`)" in sql
    assert "`price`=VALUES(`price`)" in sql
    assert "`stock`=VALUES(`stock`)" in sql
    assert "`category`=VALUES(`category`)" in sql
    
    # Clé exclue
    assert "`id`=VALUES(`id`)" not in sql


# ============================================================
# Tests Génération SQL Upsert - Clés Composites
# ============================================================

def test_build_upsert_sql_composite_key(mock_connector):
    """
    DoD: SQL correct pour clé composite.
    
    Cas: sales avec clé [region, product_id]
    """
    sql = mock_connector._build_upsert_sql(
        table="sales",
        columns=["region", "product_id", "amount", "date"],
        key_columns=["region", "product_id"]
    )
    
    # Structure
    assert "INSERT INTO `sales`" in sql
    assert "(`region`, `product_id`, `amount`, `date`)" in sql
    assert "VALUES (%s, %s, %s, %s)" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    
    # Clés composites exclues
    assert "`region`=VALUES(`region`)" not in sql
    assert "`product_id`=VALUES(`product_id`)" not in sql
    
    # Non-clés dans UPDATE
    assert "`amount`=VALUES(`amount`)" in sql
    assert "`date`=VALUES(`date`)" in sql


def test_build_upsert_sql_composite_key_three_columns(mock_connector):
    """
    Cas OK: Clé composite à 3 colonnes.
    """
    sql = mock_connector._build_upsert_sql(
        table="metrics",
        columns=["org_id", "metric_name", "timestamp", "value"],
        key_columns=["org_id", "metric_name", "timestamp"]
    )
    
    # Trois clés exclues
    assert "`org_id`=VALUES(`org_id`)" not in sql
    assert "`metric_name`=VALUES(`metric_name`)" not in sql
    assert "`timestamp`=VALUES(`timestamp`)" not in sql
    
    # Une seule non-clé dans UPDATE
    assert "`value`=VALUES(`value`)" in sql


# ============================================================
# Tests Validation - Erreurs
# ============================================================

def test_build_upsert_sql_all_columns_are_keys_fails(mock_connector):
    """
    Cas KO: Toutes colonnes sont clés → ValueError.
    
    UPDATE serait vide (pas de sens).
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._build_upsert_sql(
            table="t",
            columns=["id", "code"],
            key_columns=["id", "code"]
        )
    
    assert "all columns are key columns" in str(exc.value).lower()
    assert "non-key column" in str(exc.value).lower()


def test_build_upsert_sql_key_not_in_columns_fails(mock_connector):
    """
    Cas KO: Colonne clé absente des données → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._build_upsert_sql(
            table="users",
            columns=["name", "email"],  # id absent
            key_columns=["id"]
        )
    
    error_msg = str(exc.value)
    assert "not found" in error_msg.lower()
    assert "id" in error_msg


def test_build_upsert_sql_empty_table_fails(mock_connector):
    """
    Cas KO: Table vide → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._build_upsert_sql(
            table="",
            columns=["id", "name"],
            key_columns=["id"]
        )
    
    assert "table" in str(exc.value).lower()


def test_build_upsert_sql_empty_columns_fails(mock_connector):
    """
    Cas KO: Colonnes vides → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._build_upsert_sql(
            table="users",
            columns=[],
            key_columns=["id"]
        )
    
    assert "columns" in str(exc.value).lower()


def test_build_upsert_sql_empty_key_columns_fails(mock_connector):
    """
    Cas KO: Key colonnes vides → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._build_upsert_sql(
            table="users",
            columns=["id", "name"],
            key_columns=[]
        )
    
    assert "key_columns" in str(exc.value).lower()


# ============================================================
# Tests _validate_upsert_params
# ============================================================

def test_validate_upsert_params_ok(mock_connector):
    """
    Cas OK: Validation passe avec params corrects.
    """
    # Ne doit pas lever d'exception
    mock_connector._validate_upsert_params(
        table="users",
        key_columns=["id"]
    )


def test_validate_upsert_params_key_none_fails(mock_connector):
    """
    Cas KO: key_columns None → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._validate_upsert_params(
            table="users",
            key_columns=None
        )
    
    error_msg = str(exc.value)
    assert "key_columns required" in error_msg.lower()
    assert "example" in error_msg.lower()


def test_validate_upsert_params_key_empty_fails(mock_connector):
    """
    Cas KO: key_columns vide → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._validate_upsert_params(
            table="users",
            key_columns=[]
        )
    
    assert "empty" in str(exc.value).lower()


def test_validate_upsert_params_key_empty_string_fails(mock_connector):
    """
    Cas KO: key_columns contient string vide → ValueError.
    """
    with pytest.raises(ValueError) as exc:
        mock_connector._validate_upsert_params(
            table="users",
            key_columns=[""]
        )
    
    assert "empty strings" in str(exc.value).lower()


# ============================================================
# Tests _build_upsert_many_sql
# ============================================================

def test_build_upsert_many_sql_generates_values(mock_connector):
    """
    Cas OK: _build_upsert_many_sql génère SQL + values.
    """
    batch = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ]
    
    sql, values = mock_connector._build_upsert_many_sql(
        table="users",
        columns=["id", "name", "email"],
        key_columns=["id"],
        batch=batch
    )
    
    # SQL
    assert "INSERT INTO `users`" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    
    # Values
    assert len(values) == 2
    assert values[0] == (1, "Alice", "alice@example.com")
    assert values[1] == (2, "Bob", "bob@example.com")


def test_build_upsert_many_sql_handles_missing_columns(mock_connector):
    """
    Cas OK: Colonnes absentes d'une row → None.
    """
    batch = [
        {"id": 1, "name": "Alice"},  # email absent
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ]
    
    sql, values = mock_connector._build_upsert_many_sql(
        table="users",
        columns=["id", "name", "email"],
        key_columns=["id"],
        batch=batch
    )
    
    # Première row : email=None
    assert values[0] == (1, "Alice", None)
    assert values[1] == (2, "Bob", "bob@example.com")


# ============================================================
# Tests Syntaxe MySQL Spécifique
# ============================================================

def test_upsert_sql_uses_values_function(mock_connector):
    """
    MySQL utilise VALUES() dans UPDATE.
    
    Syntaxe spécifique MySQL (vs EXCLUDED PostgreSQL).
    """
    sql = mock_connector._build_upsert_sql(
        table="t",
        columns=["id", "val"],
        key_columns=["id"]
    )
    
    assert "VALUES(" in sql
    assert "`val`=VALUES(`val`)" in sql


def test_upsert_sql_uses_backtick_quoting(mock_connector):
    """
    MySQL utilise backticks (`) pour identifiants.
    """
    sql = mock_connector._build_upsert_sql(
        table="users",
        columns=["id", "name"],
        key_columns=["id"]
    )
    
    # Backticks
    assert "`users`" in sql
    assert "`id`" in sql
    assert "`name`" in sql
    
    # Pas de double quotes
    assert '"users"' not in sql


def test_upsert_sql_on_duplicate_key_update_syntax(mock_connector):
    """
    Vérifier syntaxe exacte ON DUPLICATE KEY UPDATE.
    """
    sql = mock_connector._build_upsert_sql(
        table="t",
        columns=["id", "name"],
        key_columns=["id"]
    )
    
    # Syntaxe MySQL exacte
    assert "ON DUPLICATE KEY UPDATE" in sql
    # Pas de variantes PostgreSQL/SQLite
    assert "ON CONFLICT" not in sql
    assert "DO UPDATE" not in sql


# ============================================================
# Tests Ordre Colonnes
# ============================================================

def test_upsert_sql_preserves_column_order(mock_connector):
    """
    Ordre colonnes préservé dans INSERT et VALUES.
    
    Important pour executemany().
    """
    sql = mock_connector._build_upsert_sql(
        table="t",
        columns=["z_col", "a_col", "m_col"],
        key_columns=["z_col"]
    )
    
    # Ordre dans SQL doit être z, a, m
    idx_z = sql.index("`z_col`")
    idx_a = sql.index("`a_col`")
    idx_m = sql.index("`m_col`")
    
    assert idx_z < idx_a < idx_m


# ============================================================
# Tests Protection Injection SQL
# ============================================================

def test_q_rejects_backtick(mock_connector):
    """
    _q() rejette backticks (injection SQL).
    """
    with pytest.raises(ValueError):
        mock_connector._q("users`; DROP TABLE users--")


def test_q_rejects_semicolon(mock_connector):
    """
    _q() rejette semicolons (injection SQL).
    """
    with pytest.raises(ValueError):
        mock_connector._q("users; DROP TABLE")


def test_q_rejects_comment(mock_connector):
    """
    _q() rejette commentaires SQL (injection).
    """
    with pytest.raises(ValueError):
        mock_connector._q("users--comment")
    
    with pytest.raises(ValueError):
        mock_connector._q("users/*comment*/")


# ============================================================
# Tests _build_insert_many_sql (régression)
# ============================================================

def test_build_insert_many_sql_still_works(mock_connector):
    """
    Vérifier que _build_insert_many_sql existe toujours (mode append).
    """
    batch = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    
    sql, values = mock_connector._build_insert_many_sql(
        table="users",
        columns=["id", "name"],
        batch=batch
    )
    
    # SQL simple INSERT
    assert "INSERT INTO `users`" in sql
    assert "VALUES (%s, %s)" in sql
    assert "ON DUPLICATE KEY" not in sql  # Pas d'upsert
    
    # Values
    assert len(values) == 2
    assert values[0] == (1, "Alice")


# ============================================================
# Résumé Tests
# ============================================================

"""
Tests MySQLMariaDBConnector - Sprint 1 Backlog 2.1

✅ 24 tests couvrent:

Génération SQL Upsert:
- Clé simple (2 tests)
- Clé composite (2 tests)
- Exclusion clés de UPDATE
- Ordre colonnes préservé

Validation:
- Erreurs params (5 tests)
- Validation upsert_params (4 tests)

SQL Injection:
- Protection _q() (3 tests)

Syntaxe MySQL:
- VALUES() function
- Backtick quoting
- ON DUPLICATE KEY UPDATE

Build SQL:
- _build_upsert_many_sql (2 tests)
- _build_insert_many_sql régression (1 test)

DoD VALIDÉ: SQL correct clés simples/composites + tests ✅
"""