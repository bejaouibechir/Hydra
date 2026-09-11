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
    pytestmark = pytest.mark.skip(reason="PyArrow non installé. Installer: pip install pyarrow pandas")

from hydra_etl.internal.connector.parquet_connector import ParquetConnector


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_job_dir():
    """Crée un répertoire temporaire pour les tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_data():
    """Données de test standard."""
    return {
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "value": [100.5, 200.75, 300.0, 400.25, 500.5]
    }


@pytest.fixture
def sample_parquet_file(temp_job_dir, sample_data):
    """Crée un fichier Parquet de test."""
    df = pd.DataFrame(sample_data)
    file_path = Path(temp_job_dir) / "test.parquet"
    df.to_parquet(file_path, compression="snappy", index=False)
    return str(file_path)


# ============================================================
# Tests Initialisation
# ============================================================

def test_init_ok(temp_job_dir):
    """Test: Initialisation normale."""
    config = {
        "type": "parquet",
        "job_dir": temp_job_dir
    }
    
    conn = ParquetConnector(name="test", config=config)
    
    assert conn.name == "test"
    assert conn._job_dir == temp_job_dir


def test_init_job_dir_parameter(temp_job_dir):
    """Test: job_dir passé comme paramètre."""
    config = {"type": "parquet"}
    
    conn = ParquetConnector(name="test", config=config, job_dir=temp_job_dir)
    
    assert conn._job_dir == temp_job_dir


def test_init_job_dir_missing():
    """Test: job_dir manquant → ValueError."""
    config = {"type": "parquet"}
    
    with pytest.raises(ValueError) as exc:
        ParquetConnector(name="test", config=config)
    
    assert "job_dir" in str(exc.value).lower()


def test_init_job_dir_not_exists(temp_job_dir):
    """Test: job_dir n'existe pas → ValueError."""
    bad_dir = os.path.join(temp_job_dir, "nonexistent")
    config = {"type": "parquet", "job_dir": bad_dir}
    
    with pytest.raises(ValueError) as exc:
        ParquetConnector(name="test", config=config)
    
    assert "n'existe pas" in str(exc.value).lower()


# ============================================================
# Tests Capabilities
# ============================================================

def test_capabilities(temp_job_dir):
    """Test: Vérification capabilities."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    caps = conn.capabilities
    
    assert caps.supports_transactions is False
    assert caps.supports_upsert is False
    assert caps.supports_incremental is False


# ============================================================
# Tests test_connection
# ============================================================

def test_connection_ok(temp_job_dir, sample_parquet_file):
    """Test: test_connection avec fichier existant."""
    config = {
        "type": "parquet",
        "job_dir": temp_job_dir,
        "extract": {"file": os.path.basename(sample_parquet_file)}
    }
    
    conn = ParquetConnector(name="test", config=config)
    conn.test_connection()  # Ne doit pas lever d'erreur


def test_connection_file_missing(temp_job_dir):
    """Test: test_connection avec fichier manquant → ValueError."""
    config = {
        "type": "parquet",
        "job_dir": temp_job_dir,
        "extract": {"file": "nonexistent.parquet"}
    }
    
    conn = ParquetConnector(name="test", config=config)
    
    with pytest.raises(ValueError) as exc:
        conn.test_connection()
    
    assert "introuvable" in str(exc.value).lower()


# ============================================================
# Tests extract_batches
# ============================================================

def test_extract_batches_ok(temp_job_dir, sample_parquet_file, sample_data):
    """Test: Extraction basique."""
    config = {
        "type": "parquet",
        "job_dir": temp_job_dir,
        "extract": {"file": os.path.basename(sample_parquet_file)}
    }
    
    conn = ParquetConnector(name="test", config=config)
    batches = list(conn.extract_batches())
    
    assert len(batches) >= 1
    batch = batches[0]
    assert len(batch) == 5
    assert all("id" in row for row in batch)
    assert all("name" in row for row in batch)
    assert batch[0]["id"] == 1
    assert batch[0]["name"] == "Alice"


def test_extract_batches_custom_batch_size(temp_job_dir):
    """Test: Extraction avec batch_size personnalisé."""
    # Créer fichier avec 100 lignes
    data = {"id": list(range(100)), "value": list(range(100))}
    df = pd.DataFrame(data)
    file_path = Path(temp_job_dir) / "large.parquet"
    df.to_parquet(file_path, index=False)
    
    config = {
        "type": "parquet",
        "job_dir": temp_job_dir,
        "extract": {"file": "large.parquet"}
    }
    
    conn = ParquetConnector(name="test", config=config)
    batches = list(conn.extract_batches(batch_size=10))
    
    assert len(batches) > 1
    assert len(batches[0]) <= 10


def test_extract_batches_with_table_param(temp_job_dir, sample_parquet_file):
    """Test: Extraction avec paramètre table."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = list(conn.extract_batches(table=os.path.basename(sample_parquet_file)))
    
    assert len(batches) >= 1


def test_extract_batches_file_not_exists(temp_job_dir):
    """Test: Extraction fichier inexistant → ValueError."""
    config = {
        "type": "parquet",
        "job_dir": temp_job_dir,
        "extract": {"file": "nonexistent.parquet"}
    }
    
    conn = ParquetConnector(name="test", config=config)
    
    with pytest.raises(ValueError) as exc:
        list(conn.extract_batches())
    
    assert "introuvable" in str(exc.value).lower()


def test_extract_batches_no_file_specified(temp_job_dir):
    """Test: Extraction sans fichier spécifié → ValueError."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    with pytest.raises(ValueError) as exc:
        list(conn.extract_batches())
    
    assert "manquant" in str(exc.value).lower()


# ============================================================
# Tests load_batches - Mode Replace
# ============================================================

def test_load_batches_replace_ok(temp_job_dir):
    """Test: Load mode replace."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = [[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]]
    
    conn.load_batches(batches, table="output.parquet", mode="replace")
    
    output_path = Path(temp_job_dir) / "output.parquet"
    assert output_path.exists()
    
    df = pd.read_parquet(output_path)
    assert len(df) == 2
    assert list(df["id"]) == [1, 2]


def test_load_batches_replace_overwrites(temp_job_dir):
    """Test: Replace écrase fichier existant."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    # Premier chargement
    batch1 = [[{"id": 999, "name": "Old"}]]
    conn.load_batches(batch1, table="output.parquet", mode="replace")
    
    # Replace
    batch2 = [[{"id": 1, "name": "New"}]]
    conn.load_batches(batch2, table="output.parquet", mode="replace")
    
    output_path = Path(temp_job_dir) / "output.parquet"
    df = pd.read_parquet(output_path)
    assert len(df) == 1
    assert df.iloc[0]["id"] == 1


# ============================================================
# Tests load_batches - Mode Append
# ============================================================

def test_load_batches_append_ok(temp_job_dir):
    """Test: Load mode append."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    # Premier chargement
    batch1 = [[{"id": 1, "name": "Alice"}]]
    conn.load_batches(batch1, table="output.parquet", mode="replace")
    
    # Append
    batch2 = [[{"id": 2, "name": "Bob"}]]
    conn.load_batches(batch2, table="output.parquet", mode="append")
    
    output_path = Path(temp_job_dir) / "output.parquet"
    df = pd.read_parquet(output_path)
    assert len(df) == 2


def test_load_batches_append_schema_mismatch(temp_job_dir):
    """Test: Append avec schéma incompatible → ValueError."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    # Premier chargement
    batch1 = [[{"id": 1, "name": "Alice"}]]
    conn.load_batches(batch1, table="output.parquet", mode="replace")
    
    # Append avec schéma différent
    batch2 = [[{"id": 2, "other_field": "Bob"}]]
    
    with pytest.raises(ValueError) as exc:
        conn.load_batches(batch2, table="output.parquet", mode="append")
    
    assert "schéma incompatible" in str(exc.value).lower()


# ============================================================
# Tests load_batches - Compressions
# ============================================================

@pytest.mark.parametrize("compression", ["snappy", "gzip", "brotli", "none"])
def test_load_batches_compressions(temp_job_dir, compression):
    """Test: Différentes compressions."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = [[{"id": 1, "value": 100}]]
    output_file = f"output_{compression}.parquet"
    
    conn.load_batches(batches, table=output_file, mode="replace", compression=compression)
    
    output_path = Path(temp_job_dir) / output_file
    assert output_path.exists()
    
    df = pd.read_parquet(output_path)
    assert len(df) == 1


def test_load_batches_invalid_compression(temp_job_dir):
    """Test: Compression invalide → ValueError."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = [[{"id": 1}]]
    
    with pytest.raises(ValueError) as exc:
        conn.load_batches(batches, table="output.parquet", mode="replace", compression="invalid")
    
    assert "compression" in str(exc.value).lower()
    assert "invalide" in str(exc.value).lower()


# ============================================================
# Tests load_batches - Modes Invalides
# ============================================================

def test_load_batches_invalid_mode(temp_job_dir):
    """Test: Mode invalide → ValueError."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = [[{"id": 1}]]
    
    with pytest.raises(ValueError) as exc:
        conn.load_batches(batches, table="output.parquet", mode="upsert")
    
    assert "mode" in str(exc.value).lower()
    assert "invalide" in str(exc.value).lower()


# ============================================================
# Tests Edge Cases
# ============================================================

def test_load_batches_creates_parent_directory(temp_job_dir):
    """Test: Création automatique du répertoire parent."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = [[{"id": 1}]]
    nested_file = "nested/dir/output.parquet"
    
    conn.load_batches(batches, table=nested_file, mode="replace")
    
    output_path = Path(temp_job_dir) / nested_file
    assert output_path.exists()
    assert output_path.parent.exists()


def test_load_batches_multiple_batches(temp_job_dir):
    """Test: Multiples batches consolidés."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    batches = [
        [{"id": 1}, {"id": 2}],
        [{"id": 3}, {"id": 4}],
        [{"id": 5}]
    ]
    
    conn.load_batches(batches, table="output.parquet", mode="replace")
    
    output_path = Path(temp_job_dir) / "output.parquet"
    df = pd.read_parquet(output_path)
    assert len(df) == 5
    assert list(df["id"]) == [1, 2, 3, 4, 5]


def test_resolve_path_relative(temp_job_dir):
    """Test: Résolution chemin relatif."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    resolved = conn._resolve_path("data/file.parquet")
    
    assert resolved == str(Path(temp_job_dir) / "data" / "file.parquet")


def test_resolve_path_absolute(temp_job_dir):
    """Test: Résolution chemin absolu."""
    config = {"type": "parquet", "job_dir": temp_job_dir}
    conn = ParquetConnector(name="test", config=config)
    
    if os.name == 'nt':  # Windows
        abs_path = "C:\\absolute\\path\\file.parquet"
    else:  # Unix
        abs_path = "/absolute/path/file.parquet"
    
    resolved = conn._resolve_path(abs_path)
    assert Path(resolved).is_absolute()


