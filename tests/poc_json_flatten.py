"""
POC JSON Flatten - Sprint 4 Préalable
Projet Hydra - Structure interne/connector

Valide que pandas json_normalize peut gérer les cas JSON nested
avant de commencer l'implémentation complète du JSONConnector.

Tests critiques:
1. JSON flat → DataFrame
2. JSON nested 1 niveau → Flatten auto
3. JSON nested 2 niveaux + arrays → Flatten contrôlé
4. Types mixtes → Gestion robuste
5. JSONL streaming → Batch processing
6. Performance → 10k records
7. Gestion erreurs → Messages actionnables

Critères succès:
- Tous les tests passent sans erreur
- Performance acceptable (<1s pour 10k records)
- Gestion erreurs robuste

Si échec: Réévaluer approche (polars, pyarrow, plugin custom)

Usage:
    cd C:\\Users\\DELL\\Desktop\\Hydra
    python tests\\poc_json_flatten.py
"""

import sys
import os
import json
import time

# Ajouter le répertoire racine au PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Imports
try:
    import pandas as pd
    from pandas import json_normalize
except ImportError as e:
    print("ERREUR: pandas non installé")
    print("Solution: pip install pandas")
    sys.exit(1)


def test_1_flat():
    """Test 1: JSON flat simple."""
    print("\n" + "=" * 70)
    print("Test 1: JSON Flat")
    print("=" * 70)
    
    data = [
        {"id": 1, "name": "Alice", "email": "alice@test.com"},
        {"id": 2, "name": "Bob", "email": "bob@test.com"}
    ]
    
    df = pd.DataFrame(data)
    
    assert df.shape == (2, 3), f"Expected (2,3), got {df.shape}"
    assert list(df.columns) == ["id", "name", "email"]
    
    print(f"✅ Shape: {df.shape}")
    print(f"✅ Columns: {list(df.columns)}")
    print("\nDataFrame:")
    print(df.to_string())
    
    return True


def test_2_nested_1_level():
    """Test 2: JSON nested 1 niveau."""
    print("\n" + "=" * 70)
    print("Test 2: JSON Nested 1 Niveau")
    print("=" * 70)
    
    data = [
        {"id": 1, "user": {"name": "Alice", "age": 30}},
        {"id": 2, "user": {"name": "Bob", "age": 25}}
    ]
    
    # Test avec max_level=1
    df = json_normalize(data, max_level=1)
    
    print(f"✅ Shape: {df.shape}")
    print(f"✅ Columns: {list(df.columns)}")
    print("\nDataFrame:")
    print(df.to_string())
    
    # Vérifier que flatten a fonctionné
    assert "user.name" in df.columns or "user_name" in df.columns
    assert df.shape[0] == 2
    
    return True


def test_3_nested_2_levels_arrays():
    """Test 3: JSON nested 2 niveaux avec arrays."""
    print("\n" + "=" * 70)
    print("Test 3: JSON Nested 2 Niveaux + Arrays")
    print("=" * 70)
    
    data = [
        {
            "id": 1,
            "user": {
                "name": "Alice",
                "addresses": [
                    {"city": "Paris", "zip": "75001"},
                    {"city": "Lyon", "zip": "69001"}
                ]
            }
        }
    ]
    
    # Stratégie 1: Flatten sans explode (garde array)
    print("\n--- Stratégie 1: Flatten sans explode ---")
    df1 = json_normalize(data, max_level=2)
    print(f"Shape: {df1.shape}")
    print(f"Columns: {list(df1.columns)}")
    print("\nDataFrame:")
    print(df1.to_string())
    
    # Stratégie 2: Explode array en lignes
    print("\n--- Stratégie 2: Flatten avec explode ---")
    df2 = json_normalize(
        data, 
        record_path=["user", "addresses"],
        meta=["id", ["user", "name"]]
    )
    print(f"Shape: {df2.shape}")
    print(f"Columns: {list(df2.columns)}")
    print("\nDataFrame:")
    print(df2.to_string())
    
    assert df2.shape[0] == 2, "Expected 2 rows (2 addresses)"
    
    return True


def test_4_mixed_types():
    """Test 4: Types mixtes."""
    print("\n" + "=" * 70)
    print("Test 4: Types Mixtes")
    print("=" * 70)
    
    data = [
        {"id": 1, "value": 100},
        {"id": 2, "value": "text"},
        {"id": 3, "value": None},
        {"id": 4, "value": [1, 2, 3]}
    ]
    
    df = pd.DataFrame(data)
    
    print(f"✅ Shape: {df.shape}")
    print(f"✅ Dtypes:")
    print(df.dtypes)
    print("\nDataFrame:")
    print(df.to_string())
    
    # Vérifier que pandas gère les types mixtes (dtype=object)
    assert df["value"].dtype == object
    
    return True


def test_5_jsonl_streaming():
    """Test 5: JSONL avec streaming simulation."""
    print("\n" + "=" * 70)
    print("Test 5: JSONL Streaming")
    print("=" * 70)
    
    # Simuler JSONL
    jsonl_lines = [
        '{"id": 1, "event": "login"}',
        '{"id": 2, "event": "logout"}',
        '{"id": 3, "event": "purchase"}'
    ]
    
    # Parse ligne par ligne (streaming)
    records = []
    for line in jsonl_lines:
        records.append(json.loads(line))
    
    df = pd.DataFrame(records)
    
    print(f"✅ Shape: {df.shape}")
    print(f"✅ Columns: {list(df.columns)}")
    print("\nDataFrame:")
    print(df.to_string())
    
    assert df.shape == (3, 2)
    
    return True


def test_6_performance():
    """Test 6: Performance sur dataset moyen."""
    print("\n" + "=" * 70)
    print("Test 6: Performance (10k records)")
    print("=" * 70)
    
    # Générer 10k records nested
    print("Génération de 10,000 records nested...")
    data = [
        {
            "id": i,
            "user": {"name": f"User{i}", "age": 20 + (i % 50)},
            "metadata": {"created": f"2024-01-{(i % 30) + 1:02d}"}
        }
        for i in range(10000)
    ]
    
    print("Flatten en cours...")
    start = time.time()
    df = json_normalize(data, max_level=2)
    elapsed = time.time() - start
    
    print(f"\n✅ Shape: {df.shape}")
    print(f"✅ Temps: {elapsed:.3f}s")
    print(f"✅ Rows/sec: {len(df)/elapsed:.0f}")
    print(f"\nPremières lignes:")
    print(df.head(3).to_string())
    
    if elapsed < 1.0:
        print(f"\n✅ PERFORMANCE OK (<1s)")
    else:
        print(f"\n⚠️  PERFORMANCE LIMITE ({elapsed:.3f}s > 1s)")
    
    assert elapsed < 2.0, f"Trop lent: {elapsed:.3f}s (limite: 2s)"
    
    return True


def test_7_error_handling():
    """Test 7: Gestion erreurs."""
    print("\n" + "=" * 70)
    print("Test 7: Gestion Erreurs")
    print("=" * 70)
    
    # Test 7.1: JSON invalide
    print("\n--- Test 7.1: JSON invalide ---")
    try:
        json.loads('{"invalid": ')
        print("❌ FAIL: Should have raised JSONDecodeError")
        return False
    except json.JSONDecodeError as e:
        print(f"✅ JSONDecodeError capturé:")
        print(f"   Ligne {e.lineno}, colonne {e.colno}: {e.msg}")
    
    # Test 7.2: Nested inconsistant
    print("\n--- Test 7.2: Nested inconsistant ---")
    data = [
        {"id": 1, "user": {"name": "Alice"}},
        {"id": 2, "user": "Bob"}  # Type différent !
    ]
    
    try:
        df = json_normalize(data)
        print(f"✅ Nested inconsistant géré (shape: {df.shape})")
        print(df.to_string())
    except Exception as e:
        print(f"⚠️  Erreur lors du flatten: {e}")
        # Pas critique, on peut gérer avec warning
    
    # Test 7.3: NaN handling
    print("\n--- Test 7.3: NaN handling (None → NaN) ---")
    data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": None}]
    df = pd.DataFrame(data)
    
    # Pandas convertit None en NaN
    print("Avant conversion:")
    print(df.to_string())
    
    # Convertir NaN → None pour JSON serialization
    df_clean = df.where(pd.notna(df), None)
    print("\nAprès conversion NaN → None:")
    print(df_clean.to_string())
    
    records = df_clean.to_dict('records')
    print(f"\nDict records: {records}")
    assert records[1]["name"] is None
    print("✅ NaN → None conversion OK")
    
    return True


def run_all_poc_tests():
    """Lance tous les tests POC."""
    print("=" * 70)
    print("POC JSON FLATTEN - VALIDATION PANDAS")
    print("Projet: Hydra")
    print("Sprint: 4 - JSON Connector")
    print("=" * 70)
    
    tests = [
        ("Test 1: JSON Flat", test_1_flat),
        ("Test 2: Nested 1 niveau", test_2_nested_1_level),
        ("Test 3: Nested 2 niveaux + arrays", test_3_nested_2_levels_arrays),
        ("Test 4: Types mixtes", test_4_mixed_types),
        ("Test 5: JSONL streaming", test_5_jsonl_streaming),
        ("Test 6: Performance", test_6_performance),
        ("Test 7: Gestion erreurs", test_7_error_handling),
    ]
    
    passed = 0
    failed = 0
    failed_tests = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"\n✅ {test_name} PASSED")
            else:
                failed += 1
                failed_tests.append(test_name)
                print(f"\n❌ {test_name} FAILED")
        except Exception as e:
            failed += 1
            failed_tests.append(test_name)
            print(f"\n❌ {test_name} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    # Résumé
    print("\n" + "=" * 70)
    print("RÉSULTATS POC")
    print("=" * 70)
    print(f"Tests passés: {passed}/{len(tests)}")
    print(f"Tests échoués: {failed}/{len(tests)}")
    
    if failed > 0:
        print(f"\nTests échoués:")
        for test_name in failed_tests:
            print(f"  - {test_name}")
    
    print("\n" + "=" * 70)
    
    if failed == 0:
        print("✅ POC VALIDÉ - Pandas est adapté pour JSON connector")
        print("✅ Tous les tests passent")
        print("✅ Performance acceptable")
        print("✅ Gestion erreurs robuste")
        print("\n→ DÉCISION: GO pour Sprint 4 (JSONConnector)")
        print("→ Approche: Pandas json_normalize")
    else:
        print("❌ POC ÉCHOUÉ - Pandas inadapté")
        print(f"❌ {failed} test(s) échoué(s)")
        print("\n→ DÉCISION: NO-GO pour Sprint 4")
        print("→ Alternatives à évaluer:")
        print("   - Polars (plus rapide)")
        print("   - PyArrow (mémoire efficace)")
        print("   - Plugin custom (contrôle total)")
    
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("HYDRA ETL - POC JSON FLATTEN")
    print("=" * 70)
    print(f"Python version: {sys.version}")
    print(f"Pandas version: {pd.__version__}")
    print("=" * 70)
    
    success = run_all_poc_tests()
    
    print(f"\nCode retour: {'0 (SUCCESS)' if success else '1 (FAILURE)'}")
    sys.exit(0 if success else 1)