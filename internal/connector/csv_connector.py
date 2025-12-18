"""
CSVConnector (MVP) — Source/Destination CSV sans dépendances externes.

Objectif de l'étape 4 :
- Avoir un pipeline concret "end-to-end" basé sur CSV (lecture + écriture)
- Fonctionner sans Pandas, sans driver DB, sans libs tierces
- Supporter :
  - extraction par chunks (batch_size)
  - chargement en mode append / replace

Convention :
- Le paramètre `table` représente un chemin de fichier CSV :
    - absolu  : C:\data\input.csv
    - relatif : input.csv  (résolu via config["base_path"] si fourni)

Configuration (config dict) acceptée (optionnelle) :
- base_path : dossier racine pour les fichiers relatifs
- delimiter : séparateur CSV (par défaut ",")
- encoding  : encodage (par défaut "utf-8")
- newline   : newline pour l'écriture (par défaut "")
- quotechar : caractère de quote (par défaut '"')
- lineterminator : fin de ligne (par défaut "\\n")
- strict_schema : validation stricte des colonnes (par défaut False) [NOUVEAU]

CORRECTIONS APPLIQUÉES (v1.1) :
================================
1. ✅ Race condition need_header : vérification AVANT open() du fichier
2. ✅ Validation schéma : paramètre strict_schema pour fail-fast sur colonnes manquantes/supplémentaires
3. ✅ Encodage None : gestion explicite de config.get() retournant None
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from internal.connector.interface import Batch, Connector, Row

# Logger pour diagnostics
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CsvSettings:
    """Paramètres normalisés de lecture/écriture CSV (issus de config)."""

    base_path: Optional[Path]
    delimiter: str
    encoding: str
    newline: str
    quotechar: str
    lineterminator: str
    strict_schema: bool  # ✅ NOUVEAU : validation stricte des colonnes


class CSVConnector(Connector):
    """
    Connecteur CSV minimal.

    Remarques :
    - On reste "streaming friendly" : extract_batches() lit et yield par lots.
    - load_batches() écrit au fil de l'eau.
    - Les erreurs I/O sont normalisées en ValueError pour rester cohérent côté core.
    
    Version : 1.1 (corrections appliquées)
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        # On appelle le constructeur du contrat de base.
        super().__init__(name=name, config=config)

        # On normalise les settings une seule fois (plus simple + plus sûr).
        self._settings = self._normalize_settings(config)

    # ---------------------------------------------------------------------
    # Helpers internes
    # ---------------------------------------------------------------------

    @staticmethod
    def _normalize_settings(config: Dict[str, Any]) -> _CsvSettings:
        """
        Normalise et valide la config.

        Règles :
        - base_path : None ou dossier existant
        - delimiter : 1 caractère (souvent "," ou ";")
        - strict_schema : validation stricte des colonnes (défaut False)
        
        ✅ CORRECTION #3 : Gestion explicite de None pour éviter str(None) = "None"
        """
        base_path_raw = config.get("base_path")
        base_path: Optional[Path] = None

        if base_path_raw is not None:
            base_path = Path(str(base_path_raw)).expanduser().resolve()
            if not base_path.exists():
                raise ValueError(f"CSVConnector: base_path introuvable: {base_path}")
            if not base_path.is_dir():
                raise ValueError(f"CSVConnector: base_path n'est pas un dossier: {base_path}")

        # ✅ CORRECTION #3 : Gérer None explicitement
        delimiter_raw = config.get("delimiter")
        delimiter = "," if delimiter_raw is None else str(delimiter_raw)
        if len(delimiter) != 1:
            raise ValueError("CSVConnector: 'delimiter' doit être un seul caractère (ex: ',' ou ';').")

        encoding_raw = config.get("encoding")
        encoding = "utf-8" if encoding_raw is None else str(encoding_raw)

        newline_raw = config.get("newline")
        newline = "" if newline_raw is None else str(newline_raw)

        quotechar_raw = config.get("quotechar")
        quotechar = '"' if quotechar_raw is None else str(quotechar_raw)
        if len(quotechar) != 1:
            raise ValueError("CSVConnector: 'quotechar' doit être un seul caractère (ex: '\"').")

        lineterminator_raw = config.get("lineterminator")
        lineterminator = "\n" if lineterminator_raw is None else str(lineterminator_raw)

        # ✅ CORRECTION #2 : Support strict_schema
        strict_schema = bool(config.get("strict_schema", False))

        return _CsvSettings(
            base_path=base_path,
            delimiter=delimiter,
            encoding=encoding,
            newline=newline,
            quotechar=quotechar,
            lineterminator=lineterminator,
            strict_schema=strict_schema,
        )

    def _resolve_path(self, table: str) -> Path:
        """
        Convertit `table` en chemin de fichier.

        Cas :
        - table est un chemin absolu -> utilisé tel quel
        - table est relatif -> résolu via base_path si fourni, sinon relatif au cwd
        """
        if not isinstance(table, str) or not table.strip():
            raise ValueError("CSVConnector: 'table' doit être un chemin non vide (string).")

        p = Path(table.strip()).expanduser()

        # Si le chemin n'est pas absolu et qu'on a un base_path, on préfixe.
        if not p.is_absolute() and self._settings.base_path is not None:
            p = self._settings.base_path / p

        # On normalise (resolve) sans exiger l'existence.
        try:
            return p.resolve()
        except Exception:
            # Certains OS / chemins peuvent lever (ex: caractères invalides).
            raise ValueError(f"CSVConnector: chemin invalide: {table}")

    # ---------------------------------------------------------------------
    # Contrat Connector
    # ---------------------------------------------------------------------

    def test_connection(self) -> None:
        """
        Diagnostic rapide.

        Pour CSV, il n'y a pas de "connexion" réseau.
        On valide juste que la config est cohérente (déjà fait)
        et que base_path (si présent) est accessible.
        """
        # Rien de plus à faire : _normalize_settings() a déjà validé.
        return

    def extract_batches(
        self,
        *,
        table: str,
        batch_size: int = 10_000,
        query: Optional[str] = None,
    ) -> Iterator[Batch]:
        """
        Lit un CSV et renvoie des lots de lignes (liste de dict).

        Notes :
        - `query` est ignoré (CSV = pas de SQL). S'il est fourni, on refuse explicitement.
        - Chaque ligne est retournée comme dict {col: valeur}.
        - Les valeurs sont retournées en strings (comportement CSV natif).
        """
        if query is not None and str(query).strip():
            raise ValueError("CSVConnector: 'query' n'est pas supporté pour CSV. Utilisez 'table' (chemin fichier).")

        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("CSVConnector: 'batch_size' doit être un entier >= 1.")

        # Limite de sécurité pour éviter OOM
        if batch_size > 100_000:
            logger.warning(
                "CSVConnector: batch_size très élevé (%d). Risque de consommation mémoire importante.",
                batch_size
            )

        csv_path = self._resolve_path(table)

        if not csv_path.exists():
            raise ValueError(f"CSVConnector: fichier source introuvable: {csv_path}")
        if not csv_path.is_file():
            raise ValueError(f"CSVConnector: la source n'est pas un fichier: {csv_path}")

        try:
            with csv_path.open("r", encoding=self._settings.encoding, newline="") as f:
                reader = csv.DictReader(
                    f,
                    delimiter=self._settings.delimiter,
                    quotechar=self._settings.quotechar,
                )

                # csv.DictReader exige une ligne d'en-tête.
                if reader.fieldnames is None or len(reader.fieldnames) == 0:
                    raise ValueError(f"CSVConnector: en-tête CSV manquante ou vide: {csv_path}")

                batch: Batch = []
                for row in reader:
                    # row est un dict[str, str | None] ; on garde None si cellule vide.
                    # On force en dict standard (Row = Dict[str, Any]).
                    batch.append(dict(row))

                    if len(batch) >= batch_size:
                        yield batch
                        batch = []

                if batch:
                    yield batch

        except ValueError:
            # On laisse passer nos ValueError (messages déjà clairs).
            raise
        except Exception as e:
            # Normalisation : aucune exception "brute" ne doit fuiter.
            raise ValueError(f"CSVConnector: échec lecture CSV ({csv_path}): {e}")

    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """
        Charge des batches dans un fichier CSV.

        Modes MVP :
        - replace : écrase le fichier et réécrit l'en-tête
        - append  : ajoute des lignes (écrit l'en-tête si le fichier n'existe pas ou est vide)

        Notes :
        - `key` ignoré (upsert non supporté en MVP).
        - On déduit les colonnes depuis le premier batch non vide.
        
        ✅ CORRECTION #1 : need_header déterminé AVANT open() du fichier
        ✅ CORRECTION #2 : Validation stricte des colonnes si strict_schema=True
        """
        if key is not None:
            # On refuse explicitement : pas d'upsert en MVP CSV.
            raise ValueError("CSVConnector: 'key' (upsert) n'est pas supporté pour CSV en MVP.")

        if not isinstance(mode, str) or not mode.strip():
            raise ValueError("CSVConnector: 'mode' doit être un string non vide ('append' ou 'replace').")

        mode_norm = mode.strip().lower()
        if mode_norm not in {"append", "replace"}:
            raise ValueError("CSVConnector: mode non supporté. Utilisez 'append' ou 'replace' (MVP).")

        csv_path = self._resolve_path(table)

        # On s'assure que le dossier parent existe.
        try:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(f"CSVConnector: impossible de créer le dossier destination ({csv_path.parent}): {e}")

        # On prépare un itérateur sur batches (sans consommer tout en mémoire).
        it = iter(batches)

        # On cherche le premier batch non vide pour déterminer les colonnes.
        first_batch: Optional[Batch] = None
        while True:
            try:
                candidate = next(it)
            except StopIteration:
                return  # Rien à écrire
            if candidate and len(candidate) > 0:
                first_batch = candidate
                break

        # Déduction des colonnes depuis la 1ère ligne du 1er batch.
        first_row: Row = first_batch[0]
        if not isinstance(first_row, dict) or len(first_row) == 0:
            raise ValueError("CSVConnector: batch invalide (la première ligne doit être un dict non vide).")

        fieldnames = list(first_row.keys())

        # ✅ CORRECTION #1 : Déterminer need_header AVANT d'ouvrir le fichier
        # En mode append, open("a") crée le fichier, donc on doit check AVANT !
        need_header = False
        if mode_norm == "replace":
            need_header = True
        elif mode_norm == "append":
            # Vérifier l'état du fichier AVANT open()
            if not csv_path.exists() or csv_path.stat().st_size == 0:
                need_header = True

        # Stratégie d'ouverture fichier selon mode.
        file_mode = "w" if mode_norm == "replace" else "a"

        try:
            # newline param important sous Windows pour éviter lignes vides.
            with csv_path.open(file_mode, encoding=self._settings.encoding, newline=self._settings.newline) as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=fieldnames,
                    delimiter=self._settings.delimiter,
                    quotechar=self._settings.quotechar,
                    lineterminator=self._settings.lineterminator,
                    extrasaction="ignore",  # si une ligne a des colonnes en plus, on ignore (sauf si strict_schema)
                )

                if need_header:
                    writer.writeheader()

                # On écrit d'abord le first_batch, puis le reste.
                self._write_one_batch(writer, first_batch, fieldnames)
                for b in it:
                    if not b:
                        continue
                    self._write_one_batch(writer, b, fieldnames)

        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"CSVConnector: échec écriture CSV ({csv_path}): {e}")

    # ---------------------------------------------------------------------
    # Ecriture par batch
    # ---------------------------------------------------------------------

    def _write_one_batch(self, writer: csv.DictWriter, batch: Batch, fieldnames: List[str]) -> None:
        """
        Ecrit un batch de lignes avec validation optionnelle du schéma.

        Règle :
        - Si une ligne manque une colonne, csv.DictWriter mettra vide.
        - Si une ligne contient des colonnes en trop, comportement dépend de strict_schema :
          * strict_schema=False : extrasaction="ignore" les ignore (silencieux)
          * strict_schema=True  : lève ValueError (fail-fast)
        
        ✅ CORRECTION #2 : Validation stricte des colonnes si activée
        """
        expected_cols = set(fieldnames)

        for row in batch:
            if not isinstance(row, dict):
                raise ValueError("CSVConnector: chaque ligne d'un batch doit être un dict.")

            # ✅ CORRECTION #2 : Validation stricte si activée
            if self._settings.strict_schema:
                row_cols = set(row.keys())
                extra = row_cols - expected_cols
                missing = expected_cols - row_cols

                if extra:
                    raise ValueError(
                        f"CSVConnector: colonnes supplémentaires détectées : {sorted(extra)}. "
                        f"Colonnes attendues : {sorted(fieldnames)}. "
                        f"Ligne : {row}"
                    )
                if missing:
                    raise ValueError(
                        f"CSVConnector: colonnes manquantes détectées : {sorted(missing)}. "
                        f"Colonnes attendues : {sorted(fieldnames)}. "
                        f"Ligne : {row}"
                    )

            # On garantit que toutes les clés attendues existent (sinon cellule vide).
            normalized = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(normalized)