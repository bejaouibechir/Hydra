"""
Parquet Connector pour Hydra ETL.

- Extract : lecture par lots, en DataFrame (extract_frames) ou en dicts.
- Load    : écriture en flux, modes append / replace.
- Compressions : snappy, gzip, brotli, none.

Pourquoi Parquet pour les sorties intermédiaires
------------------------------------------------
Dans une chaîne de jobs, chaque fichier intermédiaire écrit en CSV est
réanalysé caractère par caractère au job suivant, et son schéma est perdu
(tout redevient du texte, à recaster). En Parquet, le fichier est
colonnes, typé, compressé : le job suivant relit les colonnes dont il a
besoin, dans le bon type, sans analyse syntaxique.

C'est pourquoi ce connecteur déclare ses lots comme « par colonnes » : la
lecture rend des DataFrames construits depuis Arrow et l'écriture consomme
directement les colonnes, sans jamais fabriquer un dict par ligne.

Mémoire
-------
L'écriture est faite en flux avec ParquetWriter : les lots sont écrits au
fur et à mesure, jamais accumulés. En mode append sur un fichier existant,
le contenu déjà présent est recopié lot par lot (le format Parquet se
termine par un pied de page, on ne peut pas y ajouter en place), puis le
fichier est remplacé de façon atomique.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

import pandas as pd

from hydra_etl.internal.connector.frame_batch import FrameBatch
from hydra_etl.internal.connector.interface import Connector, Batch, ConnectorCapabilities

logger = logging.getLogger(__name__)

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

    # Lots par colonnes des deux cotes : extract_frames rend des DataFrames,
    # load_batches accepte des FrameBatch.
    accepts_frame_batches = True

    def reader_is_columnar(self, table: Optional[str] = None) -> bool:
        return _PYARROW_AVAILABLE

    def writer_is_columnar(self, table: Optional[str] = None) -> bool:
        return _PYARROW_AVAILABLE

    def reader_releases_gil(self, table: Optional[str] = None) -> bool:
        """pyarrow lit et decompresse en C++, GIL relache."""
        return _PYARROW_AVAILABLE

    def __init__(self, name: str, config: Dict[str, Any], job_dir: Optional[str] = None) -> None:
        super().__init__(name, config)
        self._job_dir = job_dir or config.get("job_dir")
        if not self._job_dir:
            raise ValueError(f"ParquetConnector [{self.name}]: 'job_dir' requis.")
        if not os.path.isdir(self._job_dir):
            raise ValueError(f"ParquetConnector [{self.name}]: job_dir '{self._job_dir}' inexistant.")
        self._projection: Optional[set] = None

    def estimate_row_bytes(self, table: Optional[str]) -> Optional[float]:
        """Octets par ligne, lus dans les metadonnees Parquet (taille non
        compressee du premier groupe de lignes). None si indisponible."""
        if not _PYARROW_AVAILABLE:
            return None
        file_path = (
            table
            or self.config.get("extract", {}).get("file")
            or self.config.get("extract", {}).get("table")
        )
        if not file_path:
            return None
        try:
            resolved = self._resolve_path(file_path)
            if not os.path.isfile(resolved):
                return None
            meta = pq.ParquetFile(resolved).metadata
            if meta.num_row_groups == 0:
                return None
            rg = meta.row_group(0)
            if rg.num_rows == 0:
                return None
            return float(rg.total_byte_size) / rg.num_rows
        except Exception:  # noqa: BLE001
            return None

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
        for record_batch in self._iter_record_batches(table, batch_size):
            batch = record_batch.to_pandas().to_dict(orient="records")
            if batch:
                yield batch

    def extract_frames(
        self,
        *,
        table: Optional[str] = None,
        batch_size: int = 10_000,
        query: Optional[str] = None,
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Iterator[pd.DataFrame]:
        """Memes lots que extract_batches, rendus directement en DataFrame.

        Chaque lot est egal a pd.DataFrame(lot_de_dicts) du chemin historique :
        c'est le meme RecordBatch, converti une fois au lieu de passer par un
        dict par ligne.
        """
        for record_batch in self._iter_record_batches(table, batch_size):
            frame = record_batch.to_pandas()
            if len(frame):
                yield frame

    def _iter_record_batches(self, table: Optional[str], batch_size: int):
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
            columns = self._projected_columns(parquet_file)
            for record_batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
                yield record_batch
        except ImportError:
            raise
        except Exception as e:
            raise ValueError(
                f"ParquetConnector [{self.name}]: echec lecture Parquet. {type(e).__name__}: {e}"
            ) from e

    def _projected_columns(self, parquet_file) -> Optional[List[str]]:
        if not self._projection:
            return None
        noms = list(parquet_file.schema_arrow.names)
        present = [c for c in noms if c in self._projection]
        if present and len(present) < len(noms):
            return present
        return None

    # ------------------------------------------------------------------ load

    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
        compression: str = "snappy",
    ) -> None:
        """Ecrit les lots en flux, sans les accumuler en memoire."""
        _require_pyarrow()
        mode_norm = mode.strip().lower()
        if mode_norm not in {"append", "replace"}:
            raise ValueError(f"ParquetConnector [{self.name}]: mode '{mode}' invalide.")
        comp_norm = compression.strip().lower()
        if comp_norm not in self.VALID_COMPRESSIONS:
            raise ValueError(f"ParquetConnector [{self.name}]: compression '{compression}' invalide.")
        compression_arg = None if comp_norm == "none" else comp_norm

        resolved_path = self._resolve_path(table)
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)

        tables = [t for t in (self._to_table(b) for b in batches) if t is not None]
        if not tables:
            if mode_norm == "replace" and os.path.isfile(resolved_path):
                os.remove(resolved_path)
            return

        recopier = mode_norm == "append" and os.path.isfile(resolved_path)
        if recopier:
            existant = pq.ParquetFile(resolved_path)
            if set(existant.schema_arrow.names) != set(tables[0].schema.names):
                raise ValueError(f"ParquetConnector [{self.name}]: schema incompatible pour append.")

        cible = Path(resolved_path)
        temporaire = cible.with_name(cible.name + ".hydra-tmp")
        writer = None
        try:
            if recopier:
                # Parquet se termine par un pied de page : on ne peut pas y
                # ajouter en place. On recopie l'existant lot par lot (memoire
                # bornee), puis on ajoute les nouveaux lots.
                lecteur = pq.ParquetFile(resolved_path)
                schema = lecteur.schema_arrow
                writer = pq.ParquetWriter(temporaire, schema, compression=compression_arg)
                for rb in lecteur.iter_batches(batch_size=64 * 1024):
                    writer.write_table(pa.Table.from_batches([rb], schema=schema))
            else:
                schema = tables[0].schema
                writer = pq.ParquetWriter(temporaire, schema, compression=compression_arg)

            for t in tables:
                if not t.schema.equals(schema):
                    try:
                        t = t.cast(schema)
                    except Exception as e:
                        raise ValueError(
                            f"ParquetConnector [{self.name}]: schema incompatible entre lots. {e}"
                        ) from None
                writer.write_table(t)
            writer.close()
            writer = None
            os.replace(temporaire, resolved_path)
        except (ImportError, ValueError):
            self._nettoyer(writer, temporaire)
            raise
        except Exception as e:
            self._nettoyer(writer, temporaire)
            raise ValueError(
                f"ParquetConnector [{self.name}]: echec ecriture Parquet. {type(e).__name__}: {e}"
            ) from e

    @staticmethod
    def _nettoyer(writer, temporaire: Path) -> None:
        if writer is not None:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            if temporaire.exists():
                temporaire.unlink()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _to_table(batch: Any):
        """Lot -> table Arrow, sans passer par un dict par ligne quand c'est possible."""
        if batch is None or len(batch) == 0:
            return None
        if isinstance(batch, FrameBatch):
            return pa.Table.from_pandas(batch.frame, preserve_index=False)
        if isinstance(batch, pd.DataFrame):
            return pa.Table.from_pandas(batch, preserve_index=False)
        return pa.Table.from_pandas(pd.DataFrame(batch), preserve_index=False)

    def _resolve_path(self, file_path: str) -> str:
        path = Path(file_path)
        if path.is_absolute():
            return str(path.resolve())
        return str(Path(self._job_dir) / path)
