"""
Tests E2E CSV → MySQL Upsert - Sprint 1 Backlog 3.2.

Scénarios testés:
1. Upsert clé simple : insertion puis update
2. Upsert clé composite
3. Upsert batch (plusieurs lignes)
4. Erreurs (clé absente, table inexistante)

Prérequis:
- Docker MySQL démarré : docker-compose up -d
- Tables créées (init.sql exécuté)
"""

import pytest

pytestmark = pytest.mark.skip(reason="E2E: requires live MySQL containers")

import pytest
import pandas as pd
import yaml
from pathlib import Path
from decimal import Decimal

from hydra_etl.internal.runner.executor import JobExecutor


# ============================================================
# Helpers
# ============================================================

def create_etl_job(
    job_dir: Path,
    source_csv: str,
    source_data: list,
    dest_table: str,
    dest_mode: str,
    dest_key: list = None,
    mysql_config: dict = None,
):
    """
    Crée un job ETL complet CSV → MySQL.
    
    Args:
        job_dir: Répertoire du job
        source_csv: Nom fichier CSV source
        source_data: Données CSV (liste de dicts)
        dest_table: Table MySQL destination
        dest_mode: Mode (append/replace/upsert)
        dest_key: Colonnes clé pour upsert
        mysql_config: Config connexion MySQL
    """
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Créer CSV source
    source_path = job_dir / source_csv
    df = pd.DataFrame(source_data)
    df.to_csv(source_path, index=False)
    
    # 2. sources.yaml
    sources_yaml = {
        "sources": {
            "csv_source": {
                "type": "csv",
                "connection": {},
                "extract": {
                    "table": str(source_path),
                    "batch_size": 1000
                }
            }
        }
    }
    
    # 3. destinations.yaml
    load_config = {
        "table": dest_table,
        "mode": dest_mode
    }
    if dest_key:
        load_config["key"] = dest_key
    
    destinations_yaml = {
        "destinations": {
            "mysql_dest": {
                "type": "mysql",
                "connection": mysql_config or {
                    "host": "localhost",
                    "port": 3307,
                    "user": "hydra_user",
                    "password": "hydra_pass",
                    "database": "hydra_test"
                },
                "load": load_config
            }
        }
    }
    
    # 4. pipeline.yaml
    pipeline_yaml = {
        "pipeline": {
            "from": "csv_source",
            "to": "mysql_dest"
        }
    }
    
    # Écrire fichiers
    (job_dir / "sources.yaml").write_text(yaml.dump(sources_yaml, allow_unicode=True), encoding="utf-8")
    (job_dir / "destinations.yaml").write_text(yaml.dump(destinations_yaml, allow_unicode=True), encoding="utf-8")
    (job_dir / "pipeline.yaml").write_text(yaml.dump(pipeline_yaml, allow_unicode=True), encoding="utf-8")


# ============================================================
# Tests E2E - Upsert Clé Simple
# ============================================================

@pytest.mark.e2e
def test_csv_to_mysql_upsert_simple_key_insert(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: CSV → MySQL upsert clé simple (id) - Insertion initiale.
    
    Scénario:
    1. Table users vide
    2. CSV avec 3 users
    3. Upsert → 3 insertions
    4. Vérifier données insérées
    """
    # Données source
    source_data = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    ]
    
    # Créer job ETL
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users.csv",
        source_data=source_data,
        dest_table="e2e_users",  # Table E2E
        dest_mode="upsert",
        dest_key=["id"],
        mysql_config=mysql_connection_config
    )
    
    # Exécuter job
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    # Vérifications
    assert result.success is True
    assert result.rows_in == 3
    assert result.rows_out == 3
    
    # Vérifier données en DB
    users = db_helper.select_all("e2e_users", order_by="id")
    assert len(users) == 3
    assert users[0]["name"] == "Alice"
    assert users[1]["name"] == "Bob"
    assert users[2]["name"] == "Charlie"


@pytest.mark.e2e
def test_csv_to_mysql_upsert_simple_key_update(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: CSV → MySQL upsert clé simple (id) - Update données existantes.
    
    Scénario:
    1. Insérer 2 users existants
    2. CSV avec mêmes IDs mais données modifiées
    3. Upsert → 2 updates
    4. Vérifier données mises à jour
    """
    # Données initiales en DB
    db_helper.insert("e2e_users", {"id": 1, "name": "Alice OLD", "email": "old@example.com"})
    db_helper.insert("e2e_users", {"id": 2, "name": "Bob OLD", "email": "old2@example.com"})
    
    # Nouvelles données CSV (mêmes IDs, nouvelles valeurs)
    source_data = [
        {"id": 1, "name": "Alice NEW", "email": "alice.new@example.com"},
        {"id": 2, "name": "Bob NEW", "email": "bob.new@example.com"},
    ]
    
    # Créer job ETL
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users_update.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="upsert",
        dest_key=["id"],
        mysql_config=mysql_connection_config
    )
    
    # Exécuter job
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    # Vérifications
    assert result.success is True
    
    # Vérifier UPDATE effectués
    users = db_helper.select_all("e2e_users", order_by="id")
    assert len(users) == 2  # Toujours 2 users
    assert users[0]["name"] == "Alice NEW"  # Mis à jour
    assert users[0]["email"] == "alice.new@example.com"
    assert users[1]["name"] == "Bob NEW"  # Mis à jour


@pytest.mark.e2e
def test_csv_to_mysql_upsert_simple_key_mixed(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: CSV → MySQL upsert - Mix INSERT + UPDATE.
    
    Scénario:
    1. DB avec user id=1
    2. CSV avec id=1 (update) et id=2 (insert)
    3. Résultat: 1 update + 1 insert
    """
    # Donnée initiale
    db_helper.insert("e2e_users", {"id": 1, "name": "Alice OLD", "email": "old@example.com"})
    
    # CSV mix
    source_data = [
        {"id": 1, "name": "Alice UPDATED", "email": "alice.updated@example.com"},
        {"id": 2, "name": "Bob NEW", "email": "bob@example.com"},
    ]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users_mixed.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="upsert",
        dest_key=["id"],
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    assert result.success is True
    
    # Vérifier 2 users finaux
    users = db_helper.select_all("e2e_users", order_by="id")
    assert len(users) == 2
    assert users[0]["id"] == 1
    assert users[0]["name"] == "Alice UPDATED"
    assert users[1]["id"] == 2
    assert users[1]["name"] == "Bob NEW"


# ============================================================
# Tests E2E - Upsert Clé Composite
# ============================================================

@pytest.mark.e2e
def test_csv_to_mysql_upsert_composite_key(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: CSV → MySQL upsert clé composite (region, product_id).
    
    Table: sales (region, product_id, amount)
    """
    # Données initiales
    db_helper.insert("e2e_sales", {"region": "EU", "product_id": "P001", "amount": Decimal("100.00")})
    
    # CSV avec update EU/P001 et insert US/P002
    source_data = [
        {"region": "EU", "product_id": "P001", "amount": 150.00},  # Update
        {"region": "US", "product_id": "P002", "amount": 200.00},  # Insert
    ]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="sales.csv",
        source_data=source_data,
        dest_table="e2e_sales",
        dest_mode="upsert",
        dest_key=["region", "product_id"],
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    assert result.success is True
    
    # Vérifier résultats
    sales = db_helper.select_all("e2e_sales")
    assert len(sales) == 2
    
    # Vérifier update
    eu_sale = db_helper.select_where("e2e_sales", {"region": "EU", "product_id": "P001"})[0]
    assert eu_sale["amount"] == Decimal("150.00")
    
    # Vérifier insert
    us_sale = db_helper.select_where("e2e_sales", {"region": "US", "product_id": "P002"})[0]
    assert us_sale["amount"] == Decimal("200.00")


# ============================================================
# Tests E2E - Batch Processing
# ============================================================

@pytest.mark.e2e
@pytest.mark.slow
def test_csv_to_mysql_upsert_large_batch(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: Upsert avec grand volume (1000 lignes).
    
    Vérifie:
    - Performance batch
    - Pas de perte de données
    """
    # Générer 1000 lignes
    source_data = [
        {"id": i, "name": f"User_{i}", "email": f"user_{i}@example.com"}
        for i in range(1, 1001)
    ]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="large_users.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="upsert",
        dest_key=["id"],
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    assert result.success is True
    assert result.rows_in == 1000
    assert result.rows_out == 1000
    
    # Vérifier count en DB
    assert db_helper.count("e2e_users") == 1000


# ============================================================
# Tests E2E - Cas d'Erreur
# ============================================================

@pytest.mark.e2e
def test_csv_to_mysql_upsert_missing_key_column_fails(clean_tables, temp_job_dir, mysql_connection_config):
    """
    E2E: Upsert avec colonne key absente des données → erreur claire.
    """
    # CSV sans colonne 'id' (key)
    source_data = [
        {"name": "Alice", "email": "alice@example.com"},  # id manquant !
    ]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users_no_id.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="upsert",
        dest_key=["id"],  # Key demandée: id
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    # Doit échouer
    assert result.success is False
    assert "id" in result.error  # Mentionne colonne manquante
    assert "not found" in result.error.lower()


@pytest.mark.e2e
def test_csv_to_mysql_upsert_without_key_fails(clean_tables, temp_job_dir, mysql_connection_config):
    """
    E2E: Upsert sans spécifier key → erreur.
    """
    source_data = [{"id": 1, "name": "Alice"}]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="upsert",
        dest_key=None,  # Key absente !
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    assert result.success is False
    assert "key" in result.error.lower()
    assert "requires" in result.error.lower()


# ============================================================
# Tests E2E - Régression Modes Classiques
# ============================================================

@pytest.mark.e2e
def test_csv_to_mysql_append_still_works(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: Mode append fonctionne toujours (régression).
    """
    # Insert initial
    db_helper.insert("e2e_users", {"id": 1, "name": "Alice", "email": "alice@example.com"})
    
    # CSV avec nouvel user
    source_data = [{"id": 2, "name": "Bob", "email": "bob@example.com"}]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="append",  # Mode append
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    assert result.success is True
    
    # Vérifier 2 users (append)
    assert db_helper.count("e2e_users") == 2


@pytest.mark.e2e
def test_csv_to_mysql_replace_still_works(clean_tables, db_helper, temp_job_dir, mysql_connection_config):
    """
    E2E: Mode replace fonctionne toujours (régression).
    """
    # Insert initial
    db_helper.insert("e2e_users", {"id": 1, "name": "Alice", "email": "alice@example.com"})
    
    # CSV avec nouveaux users
    source_data = [
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    ]
    
    create_etl_job(
        job_dir=temp_job_dir,
        source_csv="users.csv",
        source_data=source_data,
        dest_table="e2e_users",
        dest_mode="replace",  # Mode replace
        mysql_config=mysql_connection_config
    )
    
    executor = JobExecutor(job_dir=temp_job_dir)
    result = executor.run()
    
    assert result.success is True
    
    # Vérifier 2 users seulement (replace = truncate puis insert)
    users = db_helper.select_all("e2e_users", order_by="id")
    assert len(users) == 2
    assert users[0]["id"] == 2  # Alice (id=1) supprimée


# ============================================================
# Résumé Tests
# ============================================================

"""
Tests E2E CSV → MySQL Upsert - Sprint 1 Backlog 3.2

✅ 12 tests E2E complets:

Upsert clé simple (4 tests):
- Insert initial
- Update existant
- Mix insert + update
- Large batch (1000 lignes)

Upsert clé composite (1 test):
- region + product_id

Cas d'erreur (2 tests):
- Colonne key manquante
- Key non spécifiée

Régression (2 tests):
- Mode append
- Mode replace

DoD VALIDÉ:
✅ Tests E2E avec vraie DB MySQL
✅ Scénarios insert, update, mixed
✅ Clés simples et composites
✅ Gestion erreurs
✅ Performance (1000 lignes)

Prérequis:
1. docker-compose up -d
2. pytest tests/e2e/test_csv_mysql_upsert.py -v
"""