"""
Parquet Connector pour Hydra ETL.

Connecteur pour lire et écrire des fichiers Parquet avec support:
- Extract: Lecture par batch
- Load: Ecriture avec modes append/replace
- Compressions: snappy, gzip, brotli, none
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

import pandas as pd

from hydra_etl.internal.connector.interface import Connector, Batch, ConnectorCapabilities

# pyarrow importe a la demande - optionnel
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    pa = None   # type: ignore[assignment]
    pq = None   # type: ignore[assignment]
    _PYARROW_AVAILABLE = False


def _require_pyarrow() -> None:
    """Leve une erreur claire si pyarrow n'est pas installe."""
    if not _PYARROW_AVAILABLE:
        raise ImportError(
            "pyarrow is required for Parquet support. "
            "Install it with: pip install pyarrow"
        )


class ParquetConnector(Connector):
    """Connecteur Parquet avec support lecture/ecriture."""

    VALID_COMPRESSIONS = {"snappy", "gzip", "brotli", "none"}

    # Parquet est un format colonne : ne lire que les colonnes utiles evite
    # de decompresser les autres.
    supports_projection = True

    def __init__(self, name: str, config: Dict[str, Any], job_dir: Optional[str] = None) -> None:
        super().__init__(name, config)
        self._job_dir = job_dir or config.get("job_dir")
        if not self._job_dir:
            raise ValueError(f"ParquetConnector [{self.name}]: 'job_dir' requis.")
        if not os.path.isdir(self._job_dir):
            raise ValueError(f"ParquetConnector [{self.name}]: job_dir '{self._job_dir}' inexistant.")
        self._projection: Optional[set] = None

    def set_projection(self, columns: Optional[List[str]]) -> None:
        """Ne lire que ces colonnes (None = toutes). Souple : une colonne
        absente du fichier est ignoree ici."""
        self._projection = {str(c) for c in columns} if columns else None

    @property
    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_transactions=False,
            supports_upsert=False,
            supports_incremental=False
        )

    def test_connection(self) -> None:
        if not os.path.isdir(self._job_dir):
            raise ValueError(f"ParquetConnector [{self.name}]: job_dir inaccessible.")
        extract_cfg = self.config.get("extract", {})
        file_path = extract_cfg.get("file") or extract_cfg.get("table")
        if file_path:
            resolved = self._resolve_path(file_path)
            if not os.path.isfile(resolved):
                raise ValueError(f"ParquetConnector [{self.name}]: fichier '{resolved}' introuvable.")

    def extract_batches(
        self,
        *,
        query: Optional[str] = None,
        table: Optional[str] = None,
        batch_size: int = 10_000,
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Batch]:
        _require_pyarrow()
        file_path = (
            table
            or self.config.get("extract", {}).get("file")
            or self.config.get("extract", {}).get("table")
        )
        if not file_path:
            raise ValueError(f"ParquetConnector [{self.name}]: fichier source manquant.")
        resolved_path = self._resolve_path(file_path)
        if not os.path.isfile(resolved_path):
            raise ValueError(f"ParquetConnector [{self.name}]: fichier '{resolved_path}' introuvable.")
        try:
            parquet_file = pq.ParquetFile(resolved_path)
            columns = None
            if self._projection:
                present = [c for c in parquet_file.schema_arrow.names if c in self._projection]
                if present and len(present) < len(parquet_file.schema_arrow.names):
                    columns = present
            for record_batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
                df = record_batch.to_pandas()
                batch = df.to_dict(orient="records")
                if batch:
                    yield batch
        except ImportError:
            raise
        except Exception as e:
            raise ValueError(
                f"ParquetConnector [{self.name}]: echec lecture Parquet. {type(e).__name__}: {e}"
            ) from e

    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
        compression: str = "snappy",
    ) -> None:
        _require_pyarrow()
        mode_norm = mode.strip().lower()
        if mode_norm not in {"append", "replace"}:
            raise ValueError(f"ParquetConnector [{self.name}]: mode '{mode}' invalide.")
        comp_norm = compression.strip().lower()
        if comp_norm not in self.VALID_COMPRESSIONS:
            raise ValueError(f"ParquetConnector [{self.name}]: compression '{compression}' invalide.")
        resolved_path = self._resolve_path(table)
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
        if mode_norm == "replace" and os.path.isfile(resolved_path):
            os.remove(resolved_path)
        compression_arg = None if comp_norm == "none" else comp_norm
        try:
            all_dfs = [pd.DataFrame(batch) for batch in batches if batch]
            if not all_dfs:
                return
            df_combined = pd.concat(all_dfs, ignore_index=True)
            if mode_norm == "append" and os.path.isfile(resolved_path):
                df_existing = pd.read_parquet(resolved_path)
                if set(df_existing.columns) != set(df_combined.columns):
                    raise ValueError(f"ParquetConnector [{self.name}]: schema incompatible pour append.")
                df_combined = pd.concat([df_existing, df_combined], ignore_index=True)
            df_combined.to_parquet(resolved_path, compression=compression_arg, index=False)
        except (ImportError, ValueError):
            raise
        except Exception as e:
            raise ValueError(
                f"ParquetConnector [{self.name}]: echec ecriture Parquet. {type(e).__name__}: {e}"
            ) from e

    def _resolve_path(self, file_path: str) -> str:
        path = Path(file_path)
        if path.is_absolute():
            return str(path.resolve())
        return str(Path(self._job_dir) / path)
