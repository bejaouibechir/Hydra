"""
Tests unitaires du CSVConnector (MVP) - Version 1.1 (corrigée et enrichie)

Objectifs :
- Valider l'extraction par chunks (batch_size)
- Valider le chargement en mode replace / append
- Valider les erreurs :
  - fichier source introuvable
  - query non supportée
  - mode non supporté
  - batch_size invalide
- ✅ NOUVEAUX : Tests pour les 3 corrections appliquées

NOUVEAUX TESTS (v1.1) :
========================
- test_load_batches_append_on_empty_file_writes_header : Correction #1
- test_load_batches_strict_schema_detects_extra_columns : Correction #2
- test_load_batches_strict_schema_detects_missing_columns : Correction #2
- test_load_batches_lenient_schema_ignores_extra_columns : Correction #2
- test_normalize_settings_with_none_delimiter : Correction #3
- test_extract_batches_empty_file : Edge case
- test_load_batches_append_preserves_existing_data : Régression
- test_extract_batches_with_spaces_in_path : Edge case
"""

from __future__ import annotations

from pathlib import Path

import pytest

from internal.connector.csv_connector import CSVConnector


def _fixtures_dir() -> Path:
    """
    Retourne le dossier des fixtures CSV du repo.

    Convention demandée :
    - tests/fixtures/csv/...
    """
    return Path(__file__).parent / "fixtures" / "csv"


# =========================================================================
# TESTS ORIGINAUX (OK)
# =========================================================================


def test_extract_batches_ok_chunking() -> None:
    """
    Cas OK : extraction par lots.
    On vérifie :
    - nombre de batches
    - contenu basique (colonnes attendues)
    """
    csv_path = _fixtures_dir() / "users.csv"
    c = CSVConnector(name="csv_src", config={"delimiter": ",", "encoding": "utf-8"})

    batches = list(c.extract_batches(table=str(csv_path), batch_size=2))

    assert len(batches) == 2  # 3 lignes => 2 + 1
    assert len(batches[0]) == 2
    assert len(batches[1]) == 1

    # Colonnes attendues (issues du CSV fixture)
    assert set(batches[0][0].keys()) == {"id", "name", "active"}

    # Valeurs CSV : strings
    assert batches[0][0]["id"] == "1"
    assert batches[0][0]["name"] == "Alice"
    assert batches[0][0]["active"] == "true"


def test_extract_batches_rejects_query() -> None:
    """
    Cas KO : query non supportée pour CSV.
    """
    csv_path = _fixtures_dir() / "users.csv"
    c = CSVConnector(name="csv_src", config={})

    with pytest.raises(ValueError, match="query"):
        _ = list(c.extract_batches(table=str(csv_path), batch_size=2, query="SELECT * FROM users"))


def test_extract_batches_rejects_missing_file() -> None:
    """
    Cas KO : fichier source introuvable.
    """
    csv_path = _fixtures_dir() / "does_not_exist.csv"
    c = CSVConnector(name="csv_src", config={})

    with pytest.raises(ValueError, match="introuvable"):
        _ = list(c.extract_batches(table=str(csv_path), batch_size=2))


def test_extract_batches_rejects_bad_batch_size() -> None:
    """
    Cas KO : batch_size invalide.
    """
    csv_path = _fixtures_dir() / "users.csv"
    c = CSVConnector(name="csv_src", config={})

    with pytest.raises(ValueError, match="batch_size"):
        _ = list(c.extract_batches(table=str(csv_path), batch_size=0))


def test_load_batches_replace_creates_file(tmp_path: Path) -> None:
    """
    Cas OK : mode=replace écrase/crée un fichier et écrit l'en-tête.
    """
    out_csv = tmp_path / "out_replace.csv"

    c = CSVConnector(name="csv_dest", config={"delimiter": ",", "encoding": "utf-8"})

    batches = [
        [
            {"id": "10", "name": "Zoe", "active": "false"},
            {"id": "11", "name": "Yanis", "active": "true"},
        ]
    ]

    c.load_batches(batches=batches, table=str(out_csv), mode="replace")

    assert out_csv.exists()
    content = out_csv.read_text(encoding="utf-8").strip().splitlines()

    # 1 header + 2 lignes
    assert len(content) == 3
    assert content[0] == "id,name,active"
    assert content[1].startswith("10,")
    assert content[2].startswith("11,")


def test_load_batches_append_appends_without_header(tmp_path: Path) -> None:
    """
    Cas OK : mode=append ajoute des lignes, sans dupliquer l'en-tête.
    """
    out_csv = tmp_path / "out_append.csv"
    c = CSVConnector(name="csv_dest", config={"delimiter": ",", "encoding": "utf-8"})

    first = [[{"id": "1", "name": "A", "active": "true"}]]
    second = [[{"id": "2", "name": "B", "active": "false"}]]

    # 1) On crée un fichier avec header via replace
    c.load_batches(batches=first, table=str(out_csv), mode="replace")
    # 2) Puis on append
    c.load_batches(batches=second, table=str(out_csv), mode="append")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()

    # header + 2 lignes
    assert len(lines) == 3
    assert lines[0] == "id,name,active"
    assert lines[1].startswith("1,")
    assert lines[2].startswith("2,")


def test_load_batches_rejects_mode() -> None:
    """
    Cas KO : mode non supporté en MVP.
    """
    c = CSVConnector(name="csv_dest", config={})
    batches = [[{"id": "1"}]]

    with pytest.raises(ValueError, match="mode"):
        c.load_batches(batches=batches, table="dummy.csv", mode="upsert")


# =========================================================================
# ✅ NOUVEAUX TESTS (Correction #1 : Race condition need_header)
# =========================================================================


def test_load_batches_append_on_empty_file_writes_header(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #1 : Régression test.
    
    En mode append sur fichier vide (0 bytes), l'en-tête doit être écrit.
    Avant correction : Le fichier était ouvert en "a" AVANT de vérifier sa taille,
                       donc le check était invalide.
    Après correction : Le check se fait AVANT open(), donc correct.
    """
    out_csv = tmp_path / "empty.csv"
    out_csv.touch()  # Fichier vide (0 bytes)

    c = CSVConnector(name="csv_dest", config={})
    batches = [[{"id": "1", "name": "Test"}]]

    c.load_batches(batches=batches, table=str(out_csv), mode="append")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # header + 1 ligne
    assert lines[0] == "id,name"
    assert lines[1] == "1,Test"


def test_load_batches_append_on_nonexistent_file_writes_header(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #1 : Cas connexe.
    
    En mode append sur fichier inexistant, l'en-tête doit être écrit.
    """
    out_csv = tmp_path / "new_file.csv"

    c = CSVConnector(name="csv_dest", config={})
    batches = [[{"id": "1", "name": "Test"}]]

    c.load_batches(batches=batches, table=str(out_csv), mode="append")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # header + 1 ligne
    assert lines[0] == "id,name"


def test_load_batches_append_preserves_existing_data(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #1 : Test de régression.
    
    Append doit conserver les données existantes ET ne pas dupliquer l'en-tête.
    """
    out_csv = tmp_path / "out.csv"
    out_csv.write_text("id,name\n1,Alice\n", encoding="utf-8")

    c = CSVConnector(name="csv_dest", config={})
    new_batches = [[{"id": "2", "name": "Bob"}]]

    c.load_batches(batches=new_batches, table=str(out_csv), mode="append")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + Alice + Bob
    assert lines[0] == "id,name"  # Header pas dupliqué
    assert "Alice" in lines[1]
    assert "Bob" in lines[2]


# =========================================================================
# ✅ NOUVEAUX TESTS (Correction #2 : Validation schéma)
# =========================================================================


def test_load_batches_strict_schema_detects_extra_columns(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #2 : Validation stricte activée.
    
    Avec strict_schema=True, colonnes supplémentaires doivent lever ValueError.
    """
    out_csv = tmp_path / "out.csv"
    c = CSVConnector(name="csv_dest", config={"strict_schema": True})

    batches = [
        [{"id": "1", "name": "Alice"}],
        [{"id": "2", "name": "Bob", "age": "30"}],  # Colonne 'age' en trop !
    ]

    with pytest.raises(ValueError, match="colonnes supplémentaires"):
        c.load_batches(batches=batches, table=str(out_csv), mode="replace")


def test_load_batches_strict_schema_detects_missing_columns(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #2 : Validation stricte activée.
    
    Avec strict_schema=True, colonnes manquantes doivent lever ValueError.
    """
    out_csv = tmp_path / "out.csv"
    c = CSVConnector(name="csv_dest", config={"strict_schema": True})

    batches = [
        [{"id": "1", "name": "Alice", "active": "true"}],
        [{"id": "2", "name": "Bob"}],  # Colonne 'active' manquante !
    ]

    with pytest.raises(ValueError, match="colonnes manquantes"):
        c.load_batches(batches=batches, table=str(out_csv), mode="replace")


def test_load_batches_lenient_schema_ignores_extra_columns(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #2 : Mode par défaut (strict_schema=False).
    
    Sans strict_schema, colonnes supplémentaires doivent être ignorées silencieusement.
    """
    out_csv = tmp_path / "out.csv"
    c = CSVConnector(name="csv_dest", config={"strict_schema": False})

    batches = [
        [{"id": "1", "name": "Alice"}],
        [{"id": "2", "name": "Bob", "age": "30"}],  # 'age' ignorée
    ]

    # Ne doit PAS lever d'erreur
    c.load_batches(batches=batches, table=str(out_csv), mode="replace")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2 lignes
    assert lines[0] == "id,name"  # 'age' pas dans header
    assert "30" not in lines[2]  # 'age' pas écrite


def test_load_batches_lenient_schema_fills_missing_columns_with_empty(tmp_path: Path) -> None:
    """
    ✅ CORRECTION #2 : Mode par défaut (strict_schema=False).
    
    Sans strict_schema, colonnes manquantes doivent être remplies avec "" (vide).
    """
    out_csv = tmp_path / "out.csv"
    c = CSVConnector(name="csv_dest", config={"strict_schema": False})

    batches = [
        [{"id": "1", "name": "Alice", "active": "true"}],
        [{"id": "2", "name": "Bob"}],  # 'active' manquante -> ""
    ]

    # Ne doit PAS lever d'erreur
    c.load_batches(batches=batches, table=str(out_csv), mode="replace")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2 lignes
    assert lines[0] == "id,name,active"
    assert lines[1] == "1,Alice,true"
    assert lines[2] == "2,Bob,"  # 'active' vide


# =========================================================================
# ✅ NOUVEAUX TESTS (Correction #3 : Encodage None)
# =========================================================================


def test_normalize_settings_with_none_delimiter() -> None:
    """
    ✅ CORRECTION #3 : Régression test.
    
    Config avec delimiter=None doit utiliser la valeur par défaut ",".
    Avant correction : str(None) = "None" (4 caractères) -> ValueError
    Après correction : None -> "," (valeur par défaut)
    """
    config = {"delimiter": None}  # Utilisateur veut la valeur par défaut

    c = CSVConnector(name="csv_test", config=config)

    # Ne doit PAS lever ValueError("delimiter doit être 1 caractère")
    assert c._settings.delimiter == ","


def test_normalize_settings_with_none_encoding() -> None:
    """
    ✅ CORRECTION #3 : Cas connexe.
    
    Config avec encoding=None doit utiliser la valeur par défaut "utf-8".
    """
    config = {"encoding": None}

    c = CSVConnector(name="csv_test", config=config)

    assert c._settings.encoding == "utf-8"


def test_normalize_settings_with_none_quotechar() -> None:
    """
    ✅ CORRECTION #3 : Cas connexe.
    
    Config avec quotechar=None doit utiliser la valeur par défaut '"'.
    """
    config = {"quotechar": None}

    c = CSVConnector(name="csv_test", config=config)

    assert c._settings.quotechar == '"'


# =========================================================================
# ✅ NOUVEAUX TESTS (Edge cases supplémentaires)
# =========================================================================


def test_extract_batches_empty_file(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Edge case.
    
    CSV vide (0 bytes) doit retourner 0 batches sans erreur.
    """
    empty_csv = tmp_path / "empty.csv"
    empty_csv.touch()

    c = CSVConnector(name="csv_src", config={})

    # Doit lever ValueError car pas d'en-tête
    with pytest.raises(ValueError, match="en-tête CSV manquante ou vide"):
        _ = list(c.extract_batches(table=str(empty_csv), batch_size=10))


def test_extract_batches_only_header(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Edge case.
    
    CSV avec uniquement un header (pas de données) doit retourner 0 batches.
    """
    header_only = tmp_path / "header_only.csv"
    header_only.write_text("id,name,active\n", encoding="utf-8")

    c = CSVConnector(name="csv_src", config={})
    batches = list(c.extract_batches(table=str(header_only), batch_size=10))

    assert len(batches) == 0  # Pas de données, donc 0 batches


def test_extract_batches_with_spaces_in_path(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Edge case.
    
    Vérifie la gestion des chemins avec espaces.
    """
    csv_with_space = tmp_path / "my file.csv"
    csv_with_space.write_text("id,name\n1,Alice\n", encoding="utf-8")

    c = CSVConnector(name="csv_src", config={})
    batches = list(c.extract_batches(table=str(csv_with_space), batch_size=10))

    assert len(batches) == 1
    assert batches[0][0]["name"] == "Alice"


def test_extract_batches_with_semicolon_delimiter(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Test délimiteur personnalisé.
    
    Test avec délimiteur point-virgule (CSV européen).
    """
    csv_semicolon = tmp_path / "users_semicolon.csv"
    csv_semicolon.write_text("id;name;active\n1;Alice;true\n2;Bob;false\n", encoding="utf-8")

    c = CSVConnector(name="csv_src", config={"delimiter": ";"})
    batches = list(c.extract_batches(table=str(csv_semicolon), batch_size=10))

    assert len(batches) == 1
    assert batches[0][0]["name"] == "Alice"  # Pas "Alice;true"
    assert batches[0][1]["name"] == "Bob"


def test_load_batches_with_unicode_characters(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Test encodage UTF-8.
    
    Vérifie que les caractères Unicode sont correctement écrits.
    """
    out_csv = tmp_path / "unicode.csv"

    c = CSVConnector(name="csv_dest", config={"encoding": "utf-8"})
    batches = [[{"id": "1", "name": "François", "city": "São Paulo"}]]

    c.load_batches(batches=batches, table=str(out_csv), mode="replace")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert "François" in lines[1]
    assert "São Paulo" in lines[1]


def test_load_batches_empty_batches_creates_no_file(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Edge case.
    
    Si aucun batch n'est fourni, le fichier ne doit pas être créé.
    """
    out_csv = tmp_path / "should_not_exist.csv"

    c = CSVConnector(name="csv_dest", config={})
    empty_batches = []

    c.load_batches(batches=empty_batches, table=str(out_csv), mode="replace")

    assert not out_csv.exists()  # Aucun fichier créé


def test_load_batches_multiple_batches(tmp_path: Path) -> None:
    """
    ✅ NOUVEAU : Test avec plusieurs batches.
    
    Vérifie que tous les batches sont bien écrits.
    """
    out_csv = tmp_path / "multi_batch.csv"

    c = CSVConnector(name="csv_dest", config={})
    batches = [
        [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}],
        [{"id": "3", "name": "C"}],
        [{"id": "4", "name": "D"}, {"id": "5", "name": "E"}],
    ]

    c.load_batches(batches=batches, table=str(out_csv), mode="replace")

    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6  # header + 5 lignes


# =========================================================================
# STATISTIQUES DES TESTS
# =========================================================================
# Tests originaux : 8
# Tests correction #1 : 3
# Tests correction #2 : 4
# Tests correction #3 : 3
# Tests edge cases : 8
# TOTAL : 26 tests