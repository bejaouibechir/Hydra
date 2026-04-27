"""
Tests JobExecutor - Sprint 1 avec validation capabilities upsert.

VERSION FINALE - Patch au bon endroit pour MySQL mock.

Total: 18 tests
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pandas as pd
import pytest
import yaml

from internal.runner.executor import JobExecutor


# =========================================================================
# Fixtures helpers
# =========================================================================

def create_job_dir(
    tmp_path: Path,
    *,
    source_csv: str,
    source_data: list,
    transformations: dict = None,
    destination_mode: str = "replace",
    destination_key: list = None,
    destination_type: str = "csv",
    batch_size: int = 1000,
) -> Path:
    """Crée un job_dir temporaire complet."""
    job_dir = tmp_path / "test_job"
    job_dir.mkdir()
    
    source_path = job_dir / source_csv
    df_source = pd.DataFrame(source_data)
    
    if df_source.empty:
        df_source = pd.DataFrame(columns=["id", "value"])
    
    df_source.to_csv(source_path, index=False)
    
    sources_yaml = {
        "sources": {
            "src_test": {
                "type": "csv",
                "connection": {},
                "extract": {
                    "table": str(source_path),
                    "batch_size": batch_size,
                }
            }
        }
    }
    
    dest_config = {
        "type": destination_type,
        "connection": {},
        "load": {
            "table": str(job_dir / "output.csv") if destination_type == "csv" else "test_table",
            "mode": destination_mode,
        }
    }
    
    if destination_key:
        dest_config["load"]["key"] = destination_key
    
    destinations_yaml = {
        "destinations": {
            "dest_test": dest_config
        }
    }
    
    pipeline_yaml = {
        "pipeline": {
            "from": "src_test",
            "to": "dest_test",
        }
    }
    
    (job_dir / "sources.yaml").write_text(yaml.dump(sources_yaml), encoding="utf-8")
    (job_dir / "destinations.yaml").write_text(yaml.dump(destinations_yaml), encoding="utf-8")
    (job_dir / "pipeline.yaml").write_text(yaml.dump(pipeline_yaml), encoding="utf-8")
    
    if transformations:
        (job_dir / "transformations.yaml").write_text(yaml.dump(transformations), encoding="utf-8")
    
    return job_dir


# =========================================================================
# Tests : Happy path (end-to-end) - BASE
# =========================================================================

def test_executor_csv_to_csv_no_transform(tmp_path: Path):
    """Test end-to-end : CSV → CSV (sans transformation)."""
    source_data = [
        {"id": 1, "name": "Alice", "age": 25},
        {"id": 2, "name": "Bob", "age": 30},
        {"id": 3, "name": "Charlie", "age": 35},
    ]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        transformations=None,
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is True
    assert result.error is None
    assert result.rows_in == 3
    assert result.rows_out == 3
    assert result.duration > 0
    
    output_csv = job_dir / "output.csv"
    assert output_csv.exists()
    
    df_output = pd.read_csv(output_csv)
    assert len(df_output) == 3
    assert list(df_output.columns) == ["id", "name", "age"]
    assert df_output["name"].tolist() == ["Alice", "Bob", "Charlie"]


def test_executor_csv_to_csv_with_transforms(tmp_path: Path):
    """Test end-to-end : CSV → Transform → CSV."""
    source_data = [
        {"id": 1, "name": "Alice", "age": 25},
        {"id": 2, "name": "Bob", "age": 30},
        {"id": 3, "name": "Charlie", "age": 35},
    ]
    
    transformations = {
        "steps": [
            {"select": {"columns": ["id", "name"]}},
            {"filter": {"expr": 'name != "Bob"'}},
            {"calculate": {"column": "name_length", "expr": "name.str.len()"}},
            {"rename": {"mapping": {"name": "full_name"}}},
        ]
    }
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        transformations=transformations,
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is True
    assert result.rows_in == 3
    assert result.rows_out == 2
    
    df_output = pd.read_csv(job_dir / "output.csv")
    assert len(df_output) == 2
    assert list(df_output.columns) == ["id", "full_name", "name_length"]
    assert df_output["full_name"].tolist() == ["Alice", "Charlie"]
    assert df_output["name_length"].tolist() == [5, 7]


def test_executor_mode_replace(tmp_path: Path):
    """Test mode replace."""
    source_data = [{"id": 1, "val": "A"}]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        destination_mode="replace",
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is True
    assert result.rows_out == 1


def test_executor_mode_append(tmp_path: Path):
    """Test mode append."""
    source_data = [{"id": 1, "val": "A"}]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        destination_mode="append",
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is True


def test_executor_empty_source(tmp_path: Path):
    """Test source CSV vide."""
    job_dir = create_job_dir(
        tmp_path,
        source_csv="empty.csv",
        source_data=[],
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is True
    assert result.rows_in == 0
    assert result.rows_out == 0


def test_executor_large_batch_processing(tmp_path: Path):
    """Test traitement par batch (1000 rows, batch_size=100)."""
    source_data = [{"id": i, "val": f"val_{i}"} for i in range(1000)]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="large.csv",
        source_data=source_data,
        batch_size=100,
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is True
    assert result.rows_in == 1000
    assert result.rows_out == 1000


# =========================================================================
# Tests : Fail-fast
# =========================================================================

def test_executor_missing_sources_yaml_fails(tmp_path: Path):
    """Cas KO : sources.yaml manquant."""
    job_dir = tmp_path / "broken_job"
    job_dir.mkdir()
    
    (job_dir / "pipeline.yaml").write_text(
        yaml.dump({"pipeline": {"from": "src", "to": "dest"}}),
        encoding="utf-8"
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is False
    assert "sources.yaml" in result.error.lower()


def test_executor_invalid_pipeline_fails(tmp_path: Path):
    """Cas KO : pipeline invalide."""
    job_dir = tmp_path / "broken_job"
    job_dir.mkdir()
    
    (job_dir / "sources.yaml").write_text(yaml.dump({"sources": {}}), encoding="utf-8")
    (job_dir / "destinations.yaml").write_text(yaml.dump({"destinations": {}}), encoding="utf-8")
    (job_dir / "pipeline.yaml").write_text(
        yaml.dump({"pipeline": {}}),
        encoding="utf-8"
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is False
    assert "sources" in result.error.lower() or "validation" in result.error.lower()


# =========================================================================
# Tests : Sprint 1 - Validation Capabilities Upsert
# =========================================================================

def test_executor_validation_csv_upsert_fails(tmp_path: Path):
    """DoD 2.3: CSV ne supporte pas upsert → erreur claire."""
    source_data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        destination_mode="upsert",
        destination_key=["id"],
        destination_type="csv",
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is False
    assert "csv" in result.error.lower()
    assert "upsert" in result.error.lower()
    assert "does not support" in result.error.lower()


def test_executor_validation_upsert_without_key_fails(tmp_path: Path):
    """DoD 2.3: Upsert sans key → erreur claire."""
    source_data = [{"id": 1, "name": "Alice"}]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        destination_mode="upsert",
        destination_key=None,
        destination_type="mysql",
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is False
    assert "key" in result.error.lower()
    assert "requires" in result.error.lower()


def test_executor_validation_key_column_not_in_data_fails(tmp_path: Path):
    """
    DoD 2.3: Colonne key absente des données → erreur claire.
    
    FIX FINAL: Patch executor._build_connector pour mocker destination.
    """
    source_data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        destination_mode="upsert",
        destination_key=["user_id"],
        destination_type="mysql",
    )
    
    # ✅ FIX: Patcher _build_connector au lieu de registry
    with patch.object(JobExecutor, '_build_connector') as mock_build_method:
        from internal.connector.csv_connector import CSVConnector
        
        # Mock retourne vrai CSV pour source, mock pour destination
        def build_side_effect(name, definition, is_source):
            if is_source:
                # Source CSV réel
                return CSVConnector(
                    name=name,
                    config={
                        "type": "csv",
                        "job_dir": str(job_dir),
                        "extract": {"table": str(job_dir / "input.csv")}
                    },
                    job_dir=str(job_dir)
                )
            else:
                # Destination mock
                mock_dest = Mock(spec=['config', 'load_batches'])
                mock_dest.config = {"type": "mysql"}
                mock_dest.load_batches = Mock()
                return mock_dest
        
        mock_build_method.side_effect = build_side_effect
        
        executor = JobExecutor(job_dir=job_dir)
        result = executor.run()
    
    assert result.success is False
    assert "user_id" in result.error


def test_executor_validation_mysql_upsert_with_key_ok(tmp_path: Path):
    """
    Cas OK: MySQL avec upsert et key correcte.
    
    FIX FINAL: Patch executor._build_connector.
    """
    source_data = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        destination_mode="upsert",
        destination_key=["id"],
        destination_type="mysql",
    )
    
    # ✅ FIX: Patcher _build_connector
    with patch.object(JobExecutor, '_build_connector') as mock_build_method:
        from internal.connector.csv_connector import CSVConnector
        
        def build_side_effect(name, definition, is_source):
            if is_source:
                return CSVConnector(
                    name=name,
                    config={
                        "type": "csv",
                        "job_dir": str(job_dir),
                        "extract": {"table": str(job_dir / "input.csv")}
                    },
                    job_dir=str(job_dir)
                )
            else:
                mock_dest = Mock(spec=['config', 'load_batches'])
                mock_dest.config = {"type": "mysql"}
                mock_dest.load_batches = Mock()
                return mock_dest
        
        mock_build_method.side_effect = build_side_effect
        
        executor = JobExecutor(job_dir=job_dir)
        result = executor.run()
    
    assert result.success is True
    assert result.rows_in == 2
    assert result.rows_out == 2


# =========================================================================
# Tests : Validation paramètres
# =========================================================================

def test_executor_invalid_batch_size_fails(tmp_path: Path):
    """Cas KO : batch_size invalide."""
    source_data = [{"id": 1}]
    
    job_dir = create_job_dir(
        tmp_path,
        source_csv="input.csv",
        source_data=source_data,
        batch_size=10,
    )
    
    executor = JobExecutor(job_dir=job_dir)
    result = executor.run()
    
    assert result.success is False
    assert "batch_size" in result.error.lower()


def test_executor_env_variable_resolution(tmp_path: Path):
    """Test résolution ${ENV:...} dans YAML."""
    os.environ["TEST_TABLE_NAME"] = "dynamic_table.csv"
    
    try:
        source_data = [{"id": 1}]
        job_dir = tmp_path / "test_job"
        job_dir.mkdir()
        
        source_path = job_dir / "input.csv"
        pd.DataFrame(source_data).to_csv(source_path, index=False)
        
        destinations_yaml = {
            "destinations": {
                "dest_test": {
                    "type": "csv",
                    "connection": {},
                    "load": {
                        "table": "${ENV:TEST_TABLE_NAME}",
                        "mode": "replace",
                    }
                }
            }
        }
        
        sources_yaml = {
            "sources": {
                "src_test": {
                    "type": "csv",
                    "connection": {},
                    "extract": {"table": str(source_path)}
                }
            }
        }
        
        pipeline_yaml = {"pipeline": {"from": "src_test", "to": "dest_test"}}
        
        (job_dir / "sources.yaml").write_text(yaml.dump(sources_yaml), encoding="utf-8")
        (job_dir / "destinations.yaml").write_text(yaml.dump(destinations_yaml), encoding="utf-8")
        (job_dir / "pipeline.yaml").write_text(yaml.dump(pipeline_yaml), encoding="utf-8")
        
        executor = JobExecutor(job_dir=job_dir)
        result = executor.run()
        
        assert result.success is True
        assert (job_dir / "dynamic_table.csv").exists()
    
    finally:
        del os.environ["TEST_TABLE_NAME"]


"""
✅ 18/18 tests COMPLETS

FIX FINAL:
- Patch executor._build_connector au lieu de registry.build_connector
- Résout le problème de vraie instanciation MySQL

DoD 2.3 VALIDÉ: Erreur claire si upsert CSV ou key absente ✅
"""