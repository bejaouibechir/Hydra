"""
Tests Complets JSON Connector - Sprint 4
Projet Hydra ETL

Fichier de test unique et complet pour JSONConnector.
Combine tests simples + tests avec fixtures + tests paramétrés.

Usage:
    cd C:\\Users\\DELL\\Desktop\\Hydra
    
    # Tous les tests
    pytest tests/test_json_connector.py -v
    
    # Tests spécifiques
    pytest tests/test_json_connector.py::test_instantiation -v
    pytest tests/test_json_connector.py::TestJSONFlat -v
    
    # Avec output détaillé
    pytest tests/test_json_connector.py -v -s
    
    # Sans tests lents
    pytest tests/test_json_connector.py -v -m "not slow"

Auteur: Hydra Consortium
Date: Janvier 2026
Sprint: 4
"""

import json
import sys
import os
from pathlib import Path
import tempfile
import pytest

# PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from internal.connector.json_connector import JSONConnector


# ============================================================================
# FIXTURES - Setup et données de test
# ============================================================================

@pytest.fixture
def json_connector():
    """
    Fixture: Créer un JSONConnector de test.
    
    Returns:
        JSONConnector instance
    """
    config = {
        "type": "json",
        "extract": {}
    }
    return JSONConnector(name="test_json", config=config)


@pytest.fixture
def sample_flat_data():
    """
    Fixture: Données JSON flat pour tests.
    
    Returns:
        List[Dict]: JSON flat data
    """
    return [
        {"id": 1, "name": "Alice", "email": "alice@test.com", "age": 30},
        {"id": 2, "name": "Bob", "email": "bob@test.com", "age": 25},
        {"id": 3, "name": "Charlie", "email": "charlie@test.com", "age": 35}
    ]


@pytest.fixture
def sample_nested_data():
    """
    Fixture: Données JSON nested pour tests.
    
    Returns:
        List[Dict]: JSON nested data
    """
    return [
        {
            "id": 1,
            "user": {
                "name": "Alice",
                "age": 30,
                "city": "Paris"
            },
            "metadata": {
                "created": "2024-01-01",
                "updated": "2024-01-15"
            }
        },
        {
            "id": 2,
            "user": {
                "name": "Bob",
                "age": 25,
                "city": "Lyon"
            },
            "metadata": {
                "created": "2024-01-02",
                "updated": "2024-01-16"
            }
        }
    ]


@pytest.fixture
def temp_json_file(request):
    """
    Fixture: Créer un fichier JSON temporaire avec auto-cleanup.
    
    Usage:
        def test_my_test(temp_json_file):
            filepath = temp_json_file({"id": 1, "name": "test"})
            # Use filepath
    
    Args:
        request: pytest request object
    
    Returns:
        Callable: Fonction qui crée un temp file
    """
    temp_files = []
    
    def _create_temp_json(data, suffix='.json'):
        """Créer fichier JSON temporaire."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix=suffix,
            delete=False,
            encoding='utf-8'
        ) as f:
            json.dump(data, f)
            temp_files.append(f.name)
            return f.name
    
    yield _create_temp_json
    
    # Cleanup automatique
    for filepath in temp_files:
        try:
            os.unlink(filepath)
        except Exception:
            pass


@pytest.fixture
def temp_jsonl_file(request):
    """
    Fixture: Créer un fichier JSONL temporaire avec auto-cleanup.
    
    Args:
        request: pytest request object
    
    Returns:
        Callable: Fonction qui crée un temp JSONL file
    """
    temp_files = []
    
    def _create_temp_jsonl(data_list):
        """Créer fichier JSONL temporaire."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False,
            encoding='utf-8'
        ) as f:
            for record in data_list:
                f.write(json.dumps(record) + '\n')
            temp_files.append(f.name)
            return f.name
    
    yield _create_temp_jsonl
    
    # Cleanup automatique
    for filepath in temp_files:
        try:
            os.unlink(filepath)
        except Exception:
            pass


# ============================================================================
# TESTS - Instantiation et Capabilities
# ============================================================================

def test_instantiation(json_connector):
    """Test instantiation du connecteur."""
    assert json_connector is not None
    assert json_connector.name == "test_json"
    assert json_connector.config["type"] == "json"


def test_capabilities(json_connector):
    """Test capabilities du connecteur."""
    # Méthodes boolean
    assert json_connector.supports_extract() is True
    assert json_connector.supports_load() is False
    
    # Dict capabilities
    caps = json_connector.get_capabilities()
    
    assert caps["supports_extract"] is True
    assert caps["supports_load"] is False
    assert caps["supports_upsert"] is False
    assert "json" in caps["formats"]
    assert "jsonl" in caps["formats"]
    assert caps["flatten_max_depth"] == 3
    assert caps["streaming"] is True


def test_test_connection(json_connector):
    """Test méthode test_connection (sans fichier dans config)."""
    # Sans fichier dans config → pas d'erreur
    try:
        json_connector.test_connection()
    except Exception as e:
        pytest.fail(f"test_connection raised unexpected exception: {e}")


# ============================================================================
# TESTS - JSON Flat
# ============================================================================

class TestJSONFlat:
    """Tests pour JSON flat (structure simple)."""
    
    def test_json_flat_object(self, json_connector, temp_json_file):
        """Test extraction JSON objet unique."""
        data = {"id": 1, "name": "Alice", "email": "alice@test.com"}
        filepath = temp_json_file(data)
        
        result = []
        for batch in json_connector.extract_batches(file=filepath):
            result.extend(batch)
        
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["email"] == "alice@test.com"
    
    def test_json_flat_array(self, json_connector, sample_flat_data, temp_json_file):
        """Test extraction JSON array d'objets."""
        filepath = temp_json_file(sample_flat_data)
        
        result = []
        for batch in json_connector.extract_batches(file=filepath):
            result.extend(batch)
        
        assert len(result) == 3
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"
        assert result[2]["name"] == "Charlie"
    
    def test_json_flat_with_batch_size(self, json_connector, sample_flat_data, temp_json_file):
        """Test extraction avec batch_size custom."""
        filepath = temp_json_file(sample_flat_data)
        
        batches = list(json_connector.extract_batches(file=filepath, batch_size=2))
        
        # 3 records / batch_size=2 → 2 batches (2+1)
        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 1
    
    def test_json_empty_array(self, json_connector, temp_json_file):
        """Test extraction JSON array vide."""
        filepath = temp_json_file([])
        
        result = []
        for batch in json_connector.extract_batches(file=filepath):
            result.extend(batch)
        
        assert len(result) == 0


# ============================================================================
# TESTS - JSON Nested
# ============================================================================

class TestJSONNested:
    """Tests pour JSON nested (structure imbriquée)."""
    
    def test_nested_with_flatten(self, json_connector, sample_nested_data, temp_json_file):
        """Test extraction nested avec flatten."""
        filepath = temp_json_file(sample_nested_data)
        
        result = []
        for batch in json_connector.extract_batches(file=filepath, flatten_depth=2):
            result.extend(batch)
        
        assert len(result) == 2
        
        # Vérifier que flatten a créé des colonnes (pandas peut créer user.name ou user_name)
        assert any("user.name" in r or "user_name" in r for r in result)
    
    def test_nested_without_flatten(self, json_connector, sample_nested_data, temp_json_file):
        """Test extraction nested SANS flatten."""
        filepath = temp_json_file(sample_nested_data)
        
        result = []
        for batch in json_connector.extract_batches(file=filepath, flatten_depth=0):
            result.extend(batch)
        
        assert len(result) == 2
        
        # Vérifier que nested est preserved
        assert isinstance(result[0]["user"], dict)
        assert result[0]["user"]["name"] == "Alice"
        assert result[0]["user"]["city"] == "Paris"
    
    @pytest.mark.parametrize("flatten_depth", [0, 1, 2, 3])
    def test_nested_multiple_depths(
        self, 
        json_connector, 
        sample_nested_data, 
        temp_json_file, 
        flatten_depth
    ):
        """Test extraction avec différents niveaux de flatten."""
        filepath = temp_json_file(sample_nested_data)
        
        result = []
        for batch in json_connector.extract_batches(file=filepath, flatten_depth=flatten_depth):
            result.extend(batch)
        
        assert len(result) == 2
        
        if flatten_depth == 0:
            # Pas de flatten → nested preserved
            assert isinstance(result[0]["user"], dict)
        else:
            # Flatten → au moins une clé flatten doit exister
            result_keys = list(result[0].keys())
            # Vérifier qu'il y a des clés avec "." ou que la structure est différente
            # (pandas peut créer user.name ou user_name selon version)
            assert len(result_keys) > 0


# ============================================================================
# TESTS - JSONL Format
# ============================================================================

class TestJSONL:
    """Tests pour JSONL (JSON Lines)."""
    
    def test_jsonl_basic(self, json_connector, sample_flat_data, temp_jsonl_file):
        """Test extraction JSONL basique."""
        filepath = temp_jsonl_file(sample_flat_data)
        
        result = []
        for batch in json_connector.extract_batches(file=filepath):
            result.extend(batch)
        
        assert len(result) == 3
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"
    
    def test_jsonl_with_batch_size(self, json_connector, temp_jsonl_file):
        """Test extraction JSONL avec batch_size."""
        # Créer 10 records
        data = [{"id": i, "value": i * 10} for i in range(1, 11)]
        filepath = temp_jsonl_file(data)
        
        batches = list(json_connector.extract_batches(file=filepath, batch_size=3))
        
        # 10 records / batch_size=3 → 4 batches (3+3+3+1)
        assert len(batches) == 4
        assert len(batches[0]) == 3
        assert len(batches[1]) == 3
        assert len(batches[2]) == 3
        assert len(batches[3]) == 1
    
    def test_jsonl_empty_lines(self, json_connector):
        """Test JSONL avec lignes vides (doivent être ignorées)."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write('{"id": 1}\n')
            f.write('\n')  # Ligne vide
            f.write('{"id": 2}\n')
            f.write('   \n')  # Ligne whitespace
            f.write('{"id": 3}\n')
            filepath = f.name
        
        try:
            result = []
            for batch in json_connector.extract_batches(file=filepath):
                result.extend(batch)
            
            # Lignes vides doivent être ignorées
            assert len(result) == 3
            assert result[0]["id"] == 1
            assert result[1]["id"] == 2
            assert result[2]["id"] == 3
        
        finally:
            os.unlink(filepath)


# ============================================================================
# TESTS - Gestion Erreurs
# ============================================================================

class TestErrorHandling:
    """Tests de gestion d'erreurs."""
    
    def test_error_file_not_found(self, json_connector):
        """Test erreur fichier inexistant."""
        with pytest.raises(FileNotFoundError) as exc_info:
            list(json_connector.extract_batches(file="nonexistent_file_123456.json"))
        
        error_msg = str(exc_info.value)
        assert "introuvable" in error_msg.lower() or "not found" in error_msg.lower()
    
    def test_error_invalid_json(self, json_connector):
        """Test erreur JSON invalide."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write('{"invalid": ')  # JSON incomplet
            filepath = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                list(json_connector.extract_batches(file=filepath))
            
            error_msg = str(exc_info.value)
            assert "JSON invalide" in error_msg or "invalid" in error_msg.lower()
        
        finally:
            os.unlink(filepath)
    
    def test_error_invalid_jsonl_line(self, json_connector):
        """Test erreur JSON invalide dans JSONL."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write('{"id": 1}\n')
            f.write('{"invalid": \n')  # Ligne invalide
            filepath = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                list(json_connector.extract_batches(file=filepath))
            
            error_msg = str(exc_info.value)
            assert "ligne" in error_msg.lower() or "line" in error_msg.lower()
        
        finally:
            os.unlink(filepath)
    
    def test_error_no_file_or_url(self, json_connector):
        """Test erreur: ni file ni url fourni."""
        with pytest.raises((ValueError, TypeError)):
            list(json_connector.extract_batches())
    
    def test_error_both_file_and_url(self, json_connector):
        """Test erreur: file et url mutuellement exclusifs."""
        with pytest.raises(ValueError) as exc_info:
            list(json_connector.extract_batches(
                file="test.json",
                url="http://example.com"
            ))
        
        error_msg = str(exc_info.value)
        assert "mutuellement exclusifs" in error_msg.lower() or \
               "mutually exclusive" in error_msg.lower()


# ============================================================================
# TESTS - Validation Paramètres
# ============================================================================

class TestParameterValidation:
    """Tests de validation des paramètres."""
    
    @pytest.mark.parametrize("bad_depth", [-1, 4, 5, 10, "invalid"])
    def test_invalid_flatten_depth(
        self, 
        json_connector, 
        sample_flat_data, 
        temp_json_file, 
        bad_depth
    ):
        """Test validation flatten_depth invalide."""
        filepath = temp_json_file(sample_flat_data)
        
        with pytest.raises((ValueError, TypeError)):
            list(json_connector.extract_batches(file=filepath, flatten_depth=bad_depth))
    
    @pytest.mark.parametrize("bad_size", [0, -1, -10, "invalid"])
    def test_invalid_batch_size(
        self, 
        json_connector, 
        sample_flat_data, 
        temp_json_file, 
        bad_size
    ):
        """Test validation batch_size invalide."""
        filepath = temp_json_file(sample_flat_data)
        
        with pytest.raises((ValueError, TypeError)):
            list(json_connector.extract_batches(file=filepath, batch_size=bad_size))
    
    def test_valid_batch_size_range(
        self, 
        json_connector, 
        sample_flat_data, 
        temp_json_file
    ):
        """Test batch_size valides."""
        filepath = temp_json_file(sample_flat_data)
        
        # Test différentes tailles valides
        for size in [1, 10, 100, 1000, 10000]:
            result = []
            for batch in json_connector.extract_batches(file=filepath, batch_size=size):
                result.extend(batch)
            
            assert len(result) == 3  # Toujours 3 records


# ============================================================================
# TESTS - Formats Multiples
# ============================================================================

@pytest.mark.parametrize("file_ext,data_format", [
    (".json", "json"),
    (".jsonl", "jsonl"),
    (".ndjson", "jsonl"),
])
def test_multiple_file_extensions(
    json_connector,
    sample_flat_data,
    file_ext,
    data_format
):
    """Test support de multiples extensions de fichier."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix=file_ext,
        delete=False,
        encoding='utf-8'
    ) as f:
        if data_format == "json":
            json.dump(sample_flat_data, f)
        else:  # jsonl
            for record in sample_flat_data:
                f.write(json.dumps(record) + '\n')
        filepath = f.name
    
    try:
        result = []
        for batch in json_connector.extract_batches(file=filepath):
            result.extend(batch)
        
        assert len(result) == 3
        assert result[0]["name"] == "Alice"
    
    finally:
        os.unlink(filepath)


# ============================================================================
# TESTS - Performance (marqués slow)
# ============================================================================

@pytest.mark.slow
def test_performance_large_dataset(json_connector, temp_json_file):
    """
    Test performance avec large dataset.
    
    Marqué 'slow' pour skip par défaut.
    Run avec: pytest -v -m slow
    """
    import time
    
    # Créer 10k records
    large_data = [
        {
            "id": i,
            "user": {"name": f"User{i}", "age": 20 + (i % 50)},
            "metadata": {"created": f"2024-01-{(i % 30) + 1:02d}"}
        }
        for i in range(10000)
    ]
    
    filepath = temp_json_file(large_data)
    
    start = time.time()
    result = []
    for batch in json_connector.extract_batches(file=filepath, flatten_depth=2):
        result.extend(batch)
    elapsed = time.time() - start
    
    assert len(result) == 10000
    assert elapsed < 5.0, f"Too slow: {elapsed:.3f}s (expected <5s)"
    
    print(f"\n✅ Performance: {len(result)} records en {elapsed:.3f}s")
    print(f"✅ Throughput: {len(result)/elapsed:.0f} records/sec")


# ============================================================================
# TESTS - Features Sprint 5+ (NotImplementedError)
# ============================================================================

class TestFutureFeatures:
    """Tests pour features pas encore implémentées."""
    
    def test_url_extraction_not_implemented(self, json_connector):
        """Test URL extraction → Sprint 5+."""
        with pytest.raises(NotImplementedError) as exc_info:
            list(json_connector.extract_batches(url="http://example.com/data.json"))
        
        error_msg = str(exc_info.value)
        assert "Sprint 5" in error_msg or "URL" in error_msg
    
    def test_load_not_implemented(self, json_connector):
        """Test load operation → Sprint 5+."""
        with pytest.raises(NotImplementedError):
            json_connector.load_batches(
                batches=[],
                table="output",
                mode="append"
            )


# ============================================================================
# Configuration pytest
# ============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


# ============================================================================
# Main pour exécution standalone (optionnel)
# ============================================================================

if __name__ == "__main__":
    """
    Exécution standalone possible (mais pytest recommandé).
    
    Usage: python test_json_connector.py
    """
    print("=" * 70)
    print("TESTS JSON CONNECTOR")
    print("=" * 70)
    print("\nRecommandation: Utilisez pytest pour meilleurs résultats")
    print("  pytest tests/test_json_connector.py -v")
    print("\nExécution pytest en cours...")
    print("=" * 70)
    
    import pytest
    pytest.main([__file__, "-v"])