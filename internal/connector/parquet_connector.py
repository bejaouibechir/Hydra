"""
Parquet Connector pour Hydra ETL.

Connecteur pour lire et écrire des fichiers Parquet avec support:
- Extract: Lecture par batch
- Load: Écriture avec modes append/replace
- Compressions: snappy, gzip, brotli, none

Author: Hydra Team
Date: Février 2026
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from internal.connector.interface import Connector, Batch, ConnectorCapabilities


class ParquetConnector(Connector):
    """
    Connecteur Parquet avec support lecture/écriture.
    
    Configuration:
        sources:
          my_parquet:
            type: parquet
            extract:
              file: "data/input.parquet"
              batch_size: 10000
        
        destinations:
          output_parquet:
            type: parquet
            load:
              table: "output/results.parquet"
              mode: replace
              compression: snappy
    """
    
    VALID_COMPRESSIONS = {"snappy", "gzip", "brotli", "none"}
    
    def __init__(self, name: str, config: Dict[str, Any], job_dir: Optional[str] = None) -> None:
        """
        Initialise le connecteur Parquet.
        
        Args:
            name: Nom du connecteur
            config: Configuration dict
            job_dir: Répertoire job pour paths relatifs
        """
        super().__init__(name, config)
        
        self._job_dir = job_dir or config.get("job_dir")
        
        if not self._job_dir:
            raise ValueError(
                f"ParquetConnector [{self.name}]: 'job_dir' requis pour résolution chemins relatifs."
            )
        
        if not os.path.isdir(self._job_dir):
            raise ValueError(
                f"ParquetConnector [{self.name}]: job_dir '{self._job_dir}' n'existe pas."
            )
    
    @property
    def capabilities(self) -> ConnectorCapabilities:
        """Capabilities du connecteur."""
        return ConnectorCapabilities(
            supports_transactions=False,
            supports_upsert=False,
            supports_incremental=False
        )
    
    def test_connection(self) -> None:
        """Test de validité du connecteur."""
        if not os.path.isdir(self._job_dir):
            raise ValueError(
                f"ParquetConnector [{self.name}]: job_dir '{self._job_dir}' inaccessible."
            )
        
        extract_cfg = self.config.get("extract", {})
        file_path = extract_cfg.get("file") or extract_cfg.get("table")
        
        if file_path:
            resolved = self._resolve_path(file_path)
            if not os.path.isfile(resolved):
                raise ValueError(
                    f"ParquetConnector [{self.name}]: fichier '{resolved}' introuvable."
                )
    
    def extract_batches(
        self,
        *,
        query: Optional[str] = None,
        table: Optional[str] = None,
        batch_size: int = 10_000,
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Batch]:
        """
        Extrait données depuis fichier Parquet en batches.
        
        Args:
            query: Non utilisé pour Parquet
            table: Chemin fichier Parquet
            batch_size: Nombre lignes par batch
            incremental: Non supporté
        
        Yields:
            Batch de lignes (list de dict)
        """
        file_path = table or self.config.get("extract", {}).get("file") or self.config.get("extract", {}).get("table")
        
        if not file_path:
            raise ValueError(
                f"ParquetConnector [{self.name}]: fichier source manquant."
            )
        
        resolved_path = self._resolve_path(file_path)
        
        if not os.path.isfile(resolved_path):
            raise ValueError(
                f"ParquetConnector [{self.name}]: fichier '{resolved_path}' introuvable."
            )
        
        try:
            parquet_file = pq.ParquetFile(resolved_path)
            
            for record_batch in parquet_file.iter_batches(batch_size=batch_size):
                df = record_batch.to_pandas()
                batch = df.to_dict(orient="records")
                
                if batch:
                    yield batch
        
        except Exception as e:
            raise ValueError(
                f"ParquetConnector [{self.name}]: échec lecture Parquet.\n"
                f"  Fichier : {resolved_path}\n"
                f"  Erreur : {type(e).__name__}: {e}"
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
        """
        Charge batches vers fichier Parquet.
        
        Args:
            batches: Itérable de batches
            table: Chemin fichier cible
            mode: append|replace
            key: Non utilisé
            compression: snappy|gzip|brotli|none
        """
        mode_norm = mode.strip().lower()
        if mode_norm not in {"append", "replace"}:
            raise ValueError(
                f"ParquetConnector [{self.name}]: mode '{mode}' invalide. "
                f"Modes supportés: append, replace"
            )
        
        comp_norm = compression.strip().lower()
        if comp_norm not in self.VALID_COMPRESSIONS:
            raise ValueError(
                f"ParquetConnector [{self.name}]: compression '{compression}' invalide. "
                f"Options: {', '.join(sorted(self.VALID_COMPRESSIONS))}"
            )
        
        resolved_path = self._resolve_path(table)
        
        parent_dir = Path(resolved_path).parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        
        # Mode replace: supprimer fichier existant
        if mode_norm == "replace" and os.path.isfile(resolved_path):
            try:
                os.remove(resolved_path)
            except Exception as e:
                raise ValueError(
                    f"ParquetConnector [{self.name}]: échec suppression fichier.\n"
                    f"  Erreur : {type(e).__name__}: {e}"
                ) from e
        
        compression_arg = None if comp_norm == "none" else comp_norm
        
        try:
            # Collecter tous les batches en DataFrame
            all_dfs = []
            for batch in batches:
                if batch:
                    all_dfs.append(pd.DataFrame(batch))
            
            if not all_dfs:
                return  # Rien à écrire
            
            # Concaténer tous les DataFrames
            df_combined = pd.concat(all_dfs, ignore_index=True)
            
            # Mode append: lire fichier existant et concaténer
            if mode_norm == "append" and os.path.isfile(resolved_path):
                try:
                    df_existing = pd.read_parquet(resolved_path)
                    
                    # Vérifier compatibilité schéma
                    if set(df_existing.columns) != set(df_combined.columns):
                        raise ValueError(
                            f"ParquetConnector [{self.name}]: schéma incompatible pour append."
                        )
                    
                    # Concaténer
                    df_combined = pd.concat([df_existing, df_combined], ignore_index=True)
                
                except pd.errors.ParserError as e:
                    raise ValueError(
                        f"ParquetConnector [{self.name}]: échec lecture fichier existant.\n"
                        f"  Erreur : {e}"
                    ) from e
            
            # Écrire le DataFrame final
            df_combined.to_parquet(
                resolved_path,
                compression=compression_arg,
                index=False
            )
        
        except Exception as e:
            if not isinstance(e, ValueError):
                raise ValueError(
                    f"ParquetConnector [{self.name}]: échec écriture Parquet.\n"
                    f"  Erreur : {type(e).__name__}: {e}"
                ) from e
            else:
                raise
    
    def _resolve_path(self, file_path: str) -> str:
        """Résout chemin fichier (relatif → absolu via job_dir)."""
        path = Path(file_path)
        
        if path.is_absolute():
            return str(path.resolve())
        else:
            return str(Path(self._job_dir) / path)