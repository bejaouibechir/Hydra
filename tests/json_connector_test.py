"""
Tests Unitaires Simples - JSON Connector Sprint 4
Projet Hydra

Tests sans fixtures pytest - Utilise tempfiles et cleanup manuel.
Compatible pour exécution standalone : python tests/test_json_connector_simple.py

Tests couverts:
1. Instantiation et capabilities
2. JSON flat (objet unique)
3. JSON flat (array)
4. JSON nested 1 niveau
5. JSON nested sans flatten
6. JSONL format
7. JSONL avec batch_size
8. Erreur fichier introuvable
9. Erreur JSON invalide
10. Validation paramètres

Usage:
    cd C:\\Users\\DELL\\Desktop\\Hydra
    python tests\\test_json_connector_simple.py
    
    OU avec pytest:
    pytest tests/test_json_connector_simple.py -v
"""

import json
import sys
import os
from pathlib import Path
import tempfile

# PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from internal.connector.json_connector import JSONConnector


def test_1_instantiation():
    """Test 1: Instantiation et capabilities."""
    print("\n" + "=" * 70)
    print("Test 1: Instantiation et Capabilities")
    print("=" * 70)
    
    config = {"type": "json", "extract": {}}
    conn = JSONConnector(name="test_json", config=config)
    
    # Vérifier capabilities
    assert conn.supports_extract() is True
    assert conn.supports_load() is False
    
    caps = conn.get_capabilities()
    assert caps["supports_extract"] is True
    assert caps["supports_load"] is False
    assert "json" in caps["formats"]
    assert "jsonl" in caps["formats"]
    assert caps["flatten_max_depth"] == 3
    
    print(f"✅ Connector créé: {conn.name}")
    print(f"✅ Capabilities: {caps}")
    print("✅ Test 1 PASSED")


def test_2_json_flat_object():
    """Test 2: JSON objet unique flat."""
    print("\n" + "=" * 70)
    print("Test 2: JSON Flat Object")
    print("=" * 70)
    
    data = {"id": 1, "name": "Alice", "email": "alice@test.com"}
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f)
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        # Extract
        result = []
        for batch in conn.extract_batches(file=temp_file):
            result.extend(batch)
        
        # Vérifications
        assert len(result) == 1, f"Expected 1 record, got {len(result)}"
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["email"] == "alice@test.com"
        
        print(f"✅ Records extraits: {len(result)}")
        print(f"✅ Data: {result[0]}")
        print("✅ Test 2 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_3_json_flat_array():
    """Test 3: JSON array d'objets flat."""
    print("\n" + "=" * 70)
    print("Test 3: JSON Flat Array")
    print("=" * 70)
    
    data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Charlie"}
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f)
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        # Extract avec batch_size custom
        result = []
        for batch in conn.extract_batches(file=temp_file, batch_size=2):
            result.extend(batch)
        
        # Vérifications
        assert len(result) == 3
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"
        assert result[2]["name"] == "Charlie"
        
        print(f"✅ Records extraits: {len(result)}")
        print(f"✅ Noms: {[r['name'] for r in result]}")
        print("✅ Test 3 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_4_json_nested_1_level():
    """Test 4: JSON nested 1 niveau avec auto-flatten."""
    print("\n" + "=" * 70)
    print("Test 4: JSON Nested 1 Level")
    print("=" * 70)
    
    data = [
        {"id": 1, "user": {"name": "Alice", "age": 30}},
        {"id": 2, "user": {"name": "Bob", "age": 25}}
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f)
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        # Extract avec flatten_depth=1 (défaut)
        result = []
        for batch in conn.extract_batches(file=temp_file, flatten_depth=1):
            result.extend(batch)
        
        # Vérifications
        assert len(result) == 2
        
        # Vérifier flatten (pandas crée "user.name", "user.age")
        assert "user.name" in result[0] or "user_name" in result[0], \
            f"Flatten failed. Keys: {result[0].keys()}"
        
        # Vérifier valeurs
        if "user.name" in result[0]:
            assert result[0]["user.name"] == "Alice"
            assert result[0]["user.age"] == 30
        else:
            assert result[0]["user_name"] == "Alice"
            assert result[0]["user_age"] == 30
        
        print(f"✅ Records extraits: {len(result)}")
        print(f"✅ Colonnes flatten: {list(result[0].keys())}")
        print(f"✅ Premier record: {result[0]}")
        print("✅ Test 4 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_5_json_nested_no_flatten():
    """Test 5: JSON nested SANS flatten (flatten_depth=0)."""
    print("\n" + "=" * 70)
    print("Test 5: JSON Nested No Flatten")
    print("=" * 70)
    
    data = [
        {"id": 1, "user": {"name": "Alice", "age": 30}}
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f)
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        # Extract SANS flatten
        result = []
        for batch in conn.extract_batches(file=temp_file, flatten_depth=0):
            result.extend(batch)
        
        # Vérifications : nested doit être preserved
        assert len(result) == 1
        assert isinstance(result[0]["user"], dict), \
            f"Expected nested dict, got {type(result[0]['user'])}"
        assert result[0]["user"]["name"] == "Alice"
        assert result[0]["user"]["age"] == 30
        
        print(f"✅ Records extraits: {len(result)}")
        print(f"✅ Structure nested preservée: {result[0]}")
        print("✅ Test 5 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_6_jsonl_format():
    """Test 6: JSONL (JSON Lines)."""
    print("\n" + "=" * 70)
    print("Test 6: JSONL Format")
    print("=" * 70)
    
    lines = [
        '{"id": 1, "name": "Alice"}',
        '{"id": 2, "name": "Bob"}',
        '{"id": 3, "name": "Charlie"}'
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
        f.write('\n'.join(lines))
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        # Extract
        result = []
        for batch in conn.extract_batches(file=temp_file):
            result.extend(batch)
        
        # Vérifications
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["name"] == "Bob"
        assert result[2]["name"] == "Charlie"
        
        print(f"✅ Records extraits: {len(result)}")
        print(f"✅ JSONL streaming fonctionne")
        print("✅ Test 6 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_7_jsonl_batch_size():
    """Test 7: JSONL avec batch_size."""
    print("\n" + "=" * 70)
    print("Test 7: JSONL Batch Size")
    print("=" * 70)
    
    # 10 lignes
    lines = [f'{{"id": {i}, "value": {i*10}}}' for i in range(1, 11)]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
        f.write('\n'.join(lines))
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        # Extract avec batch_size=3
        batches = list(conn.extract_batches(file=temp_file, batch_size=3))
        
        # Vérifications : 10 records / batch_size=3 → 4 batches (3+3+3+1)
        assert len(batches) == 4, f"Expected 4 batches, got {len(batches)}"
        assert len(batches[0]) == 3, f"Expected 3 in batch 0, got {len(batches[0])}"
        assert len(batches[1]) == 3, f"Expected 3 in batch 1, got {len(batches[1])}"
        assert len(batches[2]) == 3, f"Expected 3 in batch 2, got {len(batches[2])}"
        assert len(batches[3]) == 1, f"Expected 1 in batch 3, got {len(batches[3])}"
        
        print(f"✅ Batches créés: {len(batches)}")
        print(f"✅ Tailles: {[len(b) for b in batches]}")
        print("✅ Test 7 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_8_error_file_not_found():
    """Test 8: Erreur fichier inexistant."""
    print("\n" + "=" * 70)
    print("Test 8: Error File Not Found")
    print("=" * 70)
    
    config = {"type": "json", "extract": {}}
    conn = JSONConnector(name="test", config=config)
    
    try:
        list(conn.extract_batches(file="nonexistent_file.json"))
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "introuvable" in str(e).lower() or "not found" in str(e).lower()
        print(f"✅ FileNotFoundError capturé: {str(e)[:100]}...")
        print("✅ Test 8 PASSED")


def test_9_error_invalid_json():
    """Test 9: Erreur JSON invalide."""
    print("\n" + "=" * 70)
    print("Test 9: Error Invalid JSON")
    print("=" * 70)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        f.write('{"invalid": ')  # JSON incomplet
        temp_file = f.name
    
    try:
        config = {"type": "json", "extract": {}}
        conn = JSONConnector(name="test", config=config)
        
        try:
            list(conn.extract_batches(file=temp_file))
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "JSON invalide" in str(e) or "invalid" in str(e).lower()
            print(f"✅ ValueError capturé: {str(e)[:150]}...")
            print("✅ Test 9 PASSED")
    
    finally:
        os.unlink(temp_file)


def test_10_validation_params():
    """Test 10: Validation paramètres."""
    print("\n" + "=" * 70)
    print("Test 10: Validation Paramètres")
    print("=" * 70)
    
    config = {"type": "json", "extract": {}}
    conn = JSONConnector(name="test", config=config)
    
    # Test 10.1: file et url mutuellement exclusifs
    print("\n--- Test 10.1: file et url exclusifs ---")
    try:
        list(conn.extract_batches(file="test.json", url="http://example.com"))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "mutuellement exclusifs" in str(e) or "mutually exclusive" in str(e).lower()
        print(f"✅ ValueError capturé: mutuellement exclusifs")
    
    # Test 10.2: file ou url requis
    print("\n--- Test 10.2: file ou url requis ---")
    try:
        list(conn.extract_batches())
        assert False, "Should have raised ValueError"
    except (ValueError, TypeError) as e:
        print(f"✅ Erreur capturée: paramètre requis")
    
    # Test 10.3: flatten_depth hors range
    print("\n--- Test 10.3: flatten_depth hors range ---")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"id": 1}, f)
        temp_file = f.name
    
    try:
        try:
            list(conn.extract_batches(file=temp_file, flatten_depth=5))
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "flatten_depth" in str(e)
            print(f"✅ ValueError capturé: flatten_depth invalide")
        
        # Test 10.4: batch_size invalide
        print("\n--- Test 10.4: batch_size invalide ---")
        try:
            list(conn.extract_batches(file=temp_file, batch_size=0))
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "batch_size" in str(e)
            print(f"✅ ValueError capturé: batch_size invalide")
    
    finally:
        os.unlink(temp_file)
    
    print("\n✅ Test 10 PASSED")


def run_all_tests():
    """Lance tous les tests simples."""
    print("=" * 70)
    print("TESTS UNITAIRES SIMPLES - JSON CONNECTOR")
    print("Projet: Hydra ETL")
    print("Sprint: 4")
    print("=" * 70)
    
    tests = [
        test_1_instantiation,
        test_2_json_flat_object,
        test_3_json_flat_array,
        test_4_json_nested_1_level,
        test_5_json_nested_no_flatten,
        test_6_jsonl_format,
        test_7_jsonl_batch_size,
        test_8_error_file_not_found,
        test_9_error_invalid_json,
        test_10_validation_params,
    ]
    
    passed = 0
    failed = 0
    failed_tests = []
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            failed_tests.append(test_func.__name__)
            print(f"\n❌ {test_func.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    # Résumé
    print("\n" + "=" * 70)
    print("RÉSULTATS")
    print("=" * 70)
    print(f"Tests passés: {passed}/{len(tests)}")
    print(f"Tests échoués: {failed}/{len(tests)}")
    
    if failed > 0:
        print(f"\nTests échoués:")
        for test_name in failed_tests:
            print(f"  - {test_name}")
    
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("HYDRA ETL - TESTS SIMPLES JSON CONNECTOR")
    print("=" * 70)
    
    success = run_all_tests()
    
    print(f"\nCode retour: {'0 (SUCCESS)' if success else '1 (FAILURE)'}")
    sys.exit(0 if success else 1)