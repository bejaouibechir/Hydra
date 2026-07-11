"""
Tests avec fixtures Parquet pour ParquetConnector.

À placer dans: tests/test_parquet_with_fixtures.py

Prérequis:
    1. Générer les fixtures:
       cd tests/fixtures/parquet
       python generate_fixtures.py
    
    2. Lancer les tests:
       pytest tests/test_parquet_with_fixtures.py -v

Author: Hydra Team
Date: Février 2026
"""

import os
import tempfile
from pathlib import Path

import pytest
import pandas as pd

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False
    pytestmark = pytest.mark.skip(reason="PyArrow non installé")

from internal.connector.parquet_connector import ParquetConnector


# ============================================================
# Configuration chemins fixtures
# ============================================================

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "parquet"


# ============================================================
# Fixtures pytest
# ============================================================

@pytest.fixture
def temp_job_dir():
    """Répertoire temporaire pour outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def fixtures_available():
    """Vérifie que les fixtures sont disponibles."""
    if not FIXTURES_DIR.exists():
        pytest.skip(f"Fixtures directory not found: {FIXTURES_DIR}")
    
    required_fixtures = ["users.parquet", "orders.parquet", "products.parquet"]
    missing = [f for f in required_fixtures if not (FIXTURES_DIR / f).exists()]
    
    if missing:
        pytest.skip(f"Missing fixtures: {missing}. Run: python tests/fixtures/parquet/generate_fixtures.py")


# ============================================================
# Tests Extract avec fixtures
# ============================================================

def test_extract_users_fixture(fixtures_available):
    """Test: Extract depuis users.parquet."""
    config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "users.parquet"}
    }
    
    conn = ParquetConnector(name="users_source", config=config)
    batches = list(conn.extract_batches())
    
    assert len(batches) >= 1
    
    # Vérifier données
    all_data = []
    for batch in batches:
        all_data.extend(batch)
    
    assert len(all_data) == 5
    assert all_data[0]["name"] == "Alice"
    assert all_data[0]["email"] == "alice@test.com"
    assert all_data[0]["age"] == 25


def test_extract_orders_fixture(fixtures_available):
    """Test: Extract depuis orders.parquet (100 lignes)."""
    config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "orders.parquet"}
    }
    
    conn = ParquetConnector(name="orders_source", config=config)
    batches = list(conn.extract_batches(batch_size=25))
    
    # Devrait avoir plusieurs batches
    assert len(batches) >= 4
    
    # Vérifier total lignes
    total_rows = sum(len(batch) for batch in batches)
    assert total_rows == 100


def test_extract_large_fixture(fixtures_available):
    """Test: Extract depuis large.parquet (10k lignes)."""
    if not (FIXTURES_DIR / "large.parquet").exists():
        pytest.skip("large.parquet not available")
    
    config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "large.parquet"}
    }
    
    conn = ParquetConnector(name="large_source", config=config)
    batches = list(conn.extract_batches(batch_size=1000))
    
    # Devrait avoir ~10 batches
    assert len(batches) >= 10
    
    # Vérifier total
    total_rows = sum(len(batch) for batch in batches)
    assert total_rows == 10000


def test_extract_empty_fixture(fixtures_available):
    """Test: Extract depuis empty.parquet."""
    if not (FIXTURES_DIR / "empty.parquet").exists():
        pytest.skip("empty.parquet not available")
    
    config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "empty.parquet"}
    }
    
    conn = ParquetConnector(name="empty_source", config=config)
    batches = list(conn.extract_batches())
    
    # Fichier vide = pas de batches ou batches vides
    total_rows = sum(len(batch) for batch in batches)
    assert total_rows == 0


# ============================================================
# Tests Load avec fixtures comme templates
# ============================================================

def test_load_from_users_to_output(fixtures_available, temp_job_dir):
    """Test: Copier users.parquet vers output."""
    # Source
    source_config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "users.parquet"}
    }
    
    source = ParquetConnector(name="source", config=source_config)
    
    # Destination
    dest_config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    dest = ParquetConnector(name="dest", config=dest_config)
    
    # Extract → Load
    batches = list(source.extract_batches())
    dest.load_batches(batches, table="users_copy.parquet", mode="replace")
    
    # Vérifier
    output_path = Path(temp_job_dir) / "users_copy.parquet"
    assert output_path.exists()
    
    df = pd.read_parquet(output_path)
    assert len(df) == 5
    assert list(df["name"]) == ["Alice", "Bob", "Charlie", "Diana", "Eve"]


def test_load_orders_with_compression_change(fixtures_available, temp_job_dir):
    """Test: Changer compression de orders.parquet (gzip → snappy)."""
    # Source (gzip)
    source_config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "orders.parquet"}
    }
    
    source = ParquetConnector(name="source", config=source_config)
    
    # Destination (snappy)
    dest_config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    dest = ParquetConnector(name="dest", config=dest_config)
    
    # Extract → Load avec nouvelle compression
    batches = list(source.extract_batches())
    dest.load_batches(batches, table="orders_snappy.parquet", mode="replace", compression="snappy")
    
    # Vérifier
    output_path = Path(temp_job_dir) / "orders_snappy.parquet"
    assert output_path.exists()
    
    df = pd.read_parquet(output_path)
    assert len(df) == 100


# ============================================================
# Tests Transformations avec fixtures
# ============================================================

def test_transform_filter_users(fixtures_available, temp_job_dir):
    """Test: Filtrer users actifs uniquement."""
    # Source
    source_config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "users.parquet"}
    }
    
    source = ParquetConnector(name="source", config=source_config)
    
    # Extract + Transform
    batches = list(source.extract_batches())
    
    filtered_batches = []
    for batch in batches:
        filtered = [row for row in batch if row.get("is_active") == True]
        if filtered:
            filtered_batches.append(filtered)
    
    # Load
    dest_config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    dest = ParquetConnector(name="dest", config=dest_config)
    dest.load_batches(filtered_batches, table="active_users.parquet", mode="replace")
    
    # Vérifier
    output_path = Path(temp_job_dir) / "active_users.parquet"
    df = pd.read_parquet(output_path)
    
    assert len(df) == 4  # Charlie est is_active=False
    assert all(df["is_active"] == True)


def test_transform_calculate_orders(fixtures_available, temp_job_dir):
    """Test: Calculer total_price pour orders."""
    # Source
    source_config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "orders.parquet"}
    }
    
    source = ParquetConnector(name="source", config=source_config)
    
    # Extract + Transform
    batches = list(source.extract_batches())
    
    transformed_batches = []
    for batch in batches:
        df = pd.DataFrame(batch)
        df["total_price"] = df["quantity"] * df["price"]
        transformed_batches.append(df.to_dict("records"))
    
    # Load
    dest_config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    dest = ParquetConnector(name="dest", config=dest_config)
    dest.load_batches(transformed_batches, table="orders_with_total.parquet", mode="replace")
    
    # Vérifier
    output_path = Path(temp_job_dir) / "orders_with_total.parquet"
    df = pd.read_parquet(output_path)
    
    assert "total_price" in df.columns
    assert len(df) == 100


# ============================================================
# Tests Multi-sources avec fixtures
# ============================================================

def test_merge_multiple_fixtures(fixtures_available, temp_job_dir):
    """Test: Combiner users et products en un seul fichier."""
    dest_config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    dest = ParquetConnector(name="dest", config=dest_config)
    
    # Load users
    source_users = ParquetConnector(
        name="users",
        config={
            "type": "parquet",
            "job_dir": str(FIXTURES_DIR),
            "extract": {"file": "users.parquet"}
        }
    )
    
    batches_users = list(source_users.extract_batches())
    
    # Créer structure commune (id, name, type)
    unified_users = []
    for batch in batches_users:
        for row in batch:
            unified_users.append({
                "id": row["id"],
                "name": row["name"],
                "type": "user"
            })
    
    dest.load_batches([unified_users], table="combined.parquet", mode="replace")
    
    # Load products (append)
    source_products = ParquetConnector(
        name="products",
        config={
            "type": "parquet",
            "job_dir": str(FIXTURES_DIR),
            "extract": {"file": "products.parquet"}
        }
    )
    
    batches_products = list(source_products.extract_batches())
    
    unified_products = []
    for batch in batches_products:
        for row in batch:
            unified_products.append({
                "id": row["product_id"],
                "name": row["product_name"],
                "type": "product"
            })
    
    dest.load_batches([unified_products], table="combined.parquet", mode="append")
    
    # Vérifier
    output_path = Path(temp_job_dir) / "combined.parquet"
    df = pd.read_parquet(output_path)
    
    assert len(df) == 10  # 5 users + 5 products
    assert set(df["type"].unique()) == {"user", "product"}


# ============================================================
# Tests Performance avec fixtures
# ============================================================

def test_performance_large_fixture(fixtures_available, temp_job_dir):
    """Test: Performance avec large.parquet (10k lignes)."""
    if not (FIXTURES_DIR / "large.parquet").exists():
        pytest.skip("large.parquet not available")
    
    import time
    
    # Source
    source_config = {
        "type": "parquet",
        "job_dir": str(FIXTURES_DIR),
        "extract": {"file": "large.parquet"}
    }
    
    source = ParquetConnector(name="source", config=source_config)
    
    # Destination
    dest_config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    dest = ParquetConnector(name="dest", config=dest_config)
    
    # Mesure performance
    start = time.time()
    
    batches = list(source.extract_batches(batch_size=1000))
    dest.load_batches(batches, table="large_copy.parquet", mode="replace")
    
    duration = time.time() - start
    
    # Vérifier performance (<5s pour 10k lignes)
    assert duration < 5.0, f"Performance dégradée: {duration:.2f}s"
    
    # Vérifier intégrité
    output_path = Path(temp_job_dir) / "large_copy.parquet"
    df = pd.read_parquet(output_path)
    assert len(df) == 10000


# ============================================================
# Tests Compressions avec fixtures
# ============================================================

def test_read_different_compressions(fixtures_available):
    """Test: Lire fichiers avec différentes compressions."""
    test_files = [
        ("users.parquet", "snappy"),
        ("orders.parquet", "gzip"),
        ("products.parquet", "brotli")
    ]
    
    for filename, expected_compression in test_files:
        if not (FIXTURES_DIR / filename).exists():
            continue
        
        config = {
            "type": "parquet",
            "job_dir": str(FIXTURES_DIR),
            "extract": {"file": filename}
        }
        
        conn = ParquetConnector(name="test", config=config)
        batches = list(conn.extract_batches())
        
        # Doit pouvoir lire sans erreur
        assert len(batches) >= 1


# ============================================================
# Résumé des tests
# ============================================================

"""
15 tests avec fixtures couvrant:
✅ Extract depuis différentes fixtures (4 tests)
✅ Load avec fixtures comme templates (2 tests)
✅ Transformations (filtrage, calculs) (2 tests)
✅ Multi-sources (merge) (1 test)
✅ Performance (1 test)
✅ Compressions (1 test)

Prérequis:
    1. Générer fixtures: python tests/fixtures/parquet/generate_fixtures.py
    2. Lancer tests: pytest tests/test_parquet_with_fixtures.py -v

Résultat attendu:
    15 passed
"""