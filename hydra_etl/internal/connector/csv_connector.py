"""
Connecteur CSV pour Hydra ETL.

Fonctionnalités MVP :
- Lecture streaming par batches
- Écriture streaming (append/replace)
- Validation schéma optionnelle (strict_schema)
- Gestion base_path pour chemins relatifs

Version : 1.2 (Correctif Étape 7)
Correctifs appliqués :
- Lecture unifiée base_path (racine ou connection.base_path)
- Fallback automatique sur job_dir
- Création automatique dossiers parents
- Messages d'erreur enrichis
"""

from __future__ import annotations

import csv
import gc
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from hydra_etl.internal.connector.interface import Batch, Connector, Row
from hydra_etl.internal.connector.frame_batch import FrameBatch
from hydra_etl._backend import dual, warn_once

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CsvSettings:
    """
    Settings normalisés du connecteur CSV.
    
    Immuable (frozen) pour éviter modifications accidentelles.
    """
    base_path: Optional[Path]
    delimiter: str
    encoding: str
    newline: str
    quotechar: str
    lineterminator: str
    strict_schema: bool


class CSVConnector(Connector):
    """
    Connecteur CSV minimal.

    Remarques :
    - On reste "streaming friendly" : extract_batches() lit et yield par lots.
    - load_batches() écrit au fil de l'eau.
    - Les erreurs I/O sont normalisées en ValueError pour rester cohérent côté core.
    
    Version : 1.2 (Correctif Étape 7)
    """

    # Étape 0-bis : load_batches accepte des FrameBatch ; extract_frames disponible.
    accepts_frame_batches = True

    # Backend Rust de « csv.read » : en dessous de cette taille de fichier, le
    # surcoût fixe (pyarrow, double passage) dépasse le gain ; Python est utilisé.
    # Mesuré : 1 000 lignes / 64 Ko -> égalité ; 20 lignes -> Rust +10 %.
    rust_min_bytes = 64 * 1024

    # Projection : le lecteur sait ne construire que les colonnes demandées.
    supports_projection = True

    def __init__(self, name: str, config: Dict[str, Any], job_dir: Optional[str] = None) -> None:
        """
        Args:
            name: Nom du connecteur (ex: 'src_csv', 'dest_csv')
            config: Configuration depuis YAML (connection + autres params)
            job_dir: Répertoire du job (pour résolution chemins relatifs)
                     Si None, utilise Path.cwd() comme fallback
        """
        # On appelle le constructeur du contrat de base.
        super().__init__(name=name, config=config)
        
        # ✅ CORRECTIF ÉTAPE 7 : Conserver job_dir pour résolution chemins
        self._job_dir = Path(job_dir).resolve() if job_dir else Path.cwd()

        # On normalise les settings une seule fois (plus simple + plus sûr).
        self._settings = self._normalize_settings(config, self._job_dir)

        # Colonnes demandées par le job (None = toutes). Voir set_projection.
        self._projection: Optional[set] = None

    def set_projection(self, columns: Optional[List[str]]) -> None:
        """Ne construire que ces colonnes (None = toutes).

        Souple : une colonne demandée mais absente du fichier est ignorée ici,
        l'opération qui en a besoin produira son message habituel.
        """
        self._projection = {str(c) for c in columns} if columns else None

    def reader_releases_gil(self, table: Optional[str] = None) -> bool:
        """Vrai quand « csv.read » passe par le module natif : le lecteur Rust
        relâche le GIL pendant l'analyse du fichier, ce qui rend le
        préchargement du lot suivant réellement utile. Le lecteur Python, lui,
        garde le GIL : y ajouter un thread ne ferait que du surcoût."""
        try:
            from hydra_etl._backend import native_status, resolve

            if resolve("csv.read") != "rust":
                return False
            ok, _ = native_status()
            return bool(ok)
        except Exception:  # noqa: BLE001
            return False

    def estimate_row_bytes(self, table: Optional[str]) -> Optional[float]:
        """Octets qu'occupe une ligne une fois en DataFrame, estimés sur un
        échantillon du fichier. None si l'estimation n'est pas possible.

        Sert au réglage automatique de batch_size ; la projection éventuelle
        est prise en compte, puisqu'elle change ce que le lot contient.
        """
        if not table:
            return None
        try:
            import pandas as pd

            csv_path = self._resolve_path(table)
            if not csv_path.is_file():
                return None
            with csv_path.open("r", encoding=self._settings.encoding, newline="") as f:
                reader = csv.reader(
                    f,
                    delimiter=self._settings.delimiter,
                    quotechar=self._settings.quotechar,
                )
                header = next(reader, None)
                if not header:
                    return None
                rows: List[List[str]] = []
                for row in reader:
                    if row == []:
                        continue
                    rows.append(row)
                    if len(rows) >= 200:
                        break
            if not rows:
                return None
            regular_header = len(set(header)) == len(header)
            frame = self._rows_to_frame(rows, list(header), regular_header, pd,
                                        self._kept_columns(list(header)))
            if len(frame) == 0:
                return None
            return float(frame.memory_usage(deep=True).sum()) / len(frame)
        except Exception:  # noqa: BLE001 - l'estimation ne doit jamais bloquer
            return None

    def _kept_columns(self, header: List[str]) -> Optional[List[str]]:
        """Colonnes du fichier à garder, ou None s'il faut tout garder."""
        if not self._projection:
            return None
        kept = [h for h in header if h in self._projection]
        if not kept or len(kept) == len(header):
            return None  # rien à gagner, ou projection vide : on lit tout
        return kept

    # ---------------------------------------------------------------------
    # Helpers internes
    # ---------------------------------------------------------------------

    @staticmethod
    def _normalize_settings(config: Dict[str, Any], job_dir: Path) -> _CsvSettings:
        """
        Normalise et valide la config.

        Règles :
        - base_path : None ou dossier existant
        - delimiter : 1 caractère (souvent "," ou ";")
        - strict_schema : validation stricte des colonnes (défaut False)
        
        ✅ CORRECTIF ÉTAPE 7 :
        - Lecture unifiée base_path (racine OU connection.base_path)
        - Fallback automatique sur job_dir si base_path absent
        """
        # ✅ Lecture unifiée : racine config OU config.connection.base_path
        base_path_raw = config.get("base_path") or config.get("connection", {}).get("base_path")
        
        base_path: Optional[Path] = None

        if base_path_raw is not None:
            base_path = Path(str(base_path_raw)).expanduser().resolve()
            if not base_path.exists():
                raise ValueError(f"CSVConnector: base_path introuvable: {base_path}")
            if not base_path.is_dir():
                raise ValueError(f"CSVConnector: base_path n'est pas un dossier: {base_path}")
        else:
            # ✅ FALLBACK : Utiliser job_dir si base_path absent
            # Garantit que les chemins relatifs sont résolus correctement
            base_path = job_dir
        

        # ✅ Gérer None explicitement pour éviter str(None) = "None"
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

        # Support strict_schema
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
        - table est relatif -> résolu via base_path (toujours défini maintenant)
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
            # ✅ CORRECTIF ÉTAPE 7 : Message d'erreur enrichi
            raise ValueError(
                f"CSVConnector [{self.name}]: Fichier source introuvable.\n"
                f"  Chemin demandé : {table}\n"
                f"  Chemin résolu : {csv_path}\n"
                f"  base_path effectif : {self._settings.base_path}\n"
                f"  job_dir : {self._job_dir}\n"
                f"  CWD actuel : {Path.cwd()}\n"
                f"  Conseil : Vérifiez que le fichier existe ou que base_path est correct."
            )
        if not csv_path.is_file():
            raise ValueError(
                f"CSVConnector [{self.name}]: La source n'est pas un fichier (peut-être un dossier ?).\n"
                f"  Chemin : {csv_path}"
            )

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
        except FileNotFoundError as e:
            # ✅ CORRECTIF ÉTAPE 7 : Message enrichi pour FileNotFoundError
            raise ValueError(
                f"CSVConnector [{self.name}]: Fichier introuvable lors de l'ouverture.\n"
                f"  Chemin : {csv_path}\n"
                f"  Erreur système : {e}"
            ) from e
        except Exception as e:
            # ✅ CORRECTIF ÉTAPE 7 : Message enrichi pour autres erreurs
            raise ValueError(
                f"CSVConnector [{self.name}]: Échec lecture CSV.\n"
                f"  Chemin : {csv_path}\n"
                f"  base_path : {self._settings.base_path}\n"
                f"  Erreur : {type(e).__name__}: {e}"
            ) from e

    # ---------------------------------------------------------------------
    # Étape 0-bis : lecture en DataFrames (sans dict par ligne)
    # ---------------------------------------------------------------------
    @dual("csv.read", rust="_extract_frames_rust")
    def extract_frames(
        self,
        *,
        table: str,
        batch_size: int = 10_000,
        query: Optional[str] = None,
    ) -> Iterator["pd.DataFrame"]:
        """
        Même contrat que extract_batches, mais chaque lot est rendu directement
        sous forme de DataFrame, égal à pd.DataFrame(lot_de_dicts) du chemin
        historique (mêmes colonnes, dtypes, valeurs).

        - Validations et messages d'erreur : identiques à extract_batches
          (_validated_source_path).
        - Lignes régulières (autant de champs que l'en-tête) : construction par colonnes.
        - Lot contenant une ligne irrégulière ou en-tête à noms dupliqués : on
          reproduit exactement csv.DictReader (restval=None, restkey=None).
        - Aiguillage Python / Rust : opération « csv.read » (voir hydra_etl/_backend.py) ;
          argument supplémentaire backend="python"|"rust".
        """
        csv_path = self._validated_source_path(table=table, batch_size=batch_size, query=query)
        yield from self._frames_python(csv_path, batch_size)

    def _frames_python(self, csv_path: Path, batch_size: int, skip_rows: int = 0) -> Iterator["pd.DataFrame"]:
        """Lecture Python (référence). `skip_rows` : lignes de données (non vides) à
        sauter, pour reprendre après un lecteur Rust qui a rendu la main."""
        import pandas as pd

        try:
            with csv_path.open("r", encoding=self._settings.encoding, newline="") as f:
                dict_reader = csv.DictReader(
                    f,
                    delimiter=self._settings.delimiter,
                    quotechar=self._settings.quotechar,
                )
                if dict_reader.fieldnames is None or len(dict_reader.fieldnames) == 0:
                    raise ValueError(f"CSVConnector: en-tête CSV manquante ou vide: {csv_path}")

                header = list(dict_reader.fieldnames)
                regular_header = len(set(header)) == len(header)
                keep = self._kept_columns(header)
                rows: List[List[str]] = []
                # Le ramasse-miettes est suspendu pendant la lecture d'un lot : les
                # milliers de listes créées déclenchent sinon des collectes complètes
                # coûteuses (~15 % du job). Aucune référence circulaire n'est créée ici ;
                # l'état d'origine est rétabli avant chaque yield et en sortie.
                gc_was_enabled = gc.isenabled()
                try:
                    gc.disable()
                    for row in dict_reader.reader:
                        if row == []:          # csv.DictReader saute les lignes vides
                            continue
                        if skip_rows:
                            skip_rows -= 1
                            continue
                        rows.append(row)
                        if len(rows) >= batch_size:
                            frame = self._rows_to_frame(rows, header, regular_header, pd, keep)
                            rows = []
                            if gc_was_enabled:
                                gc.enable()
                            yield frame
                            gc.disable()
                    if rows:
                        frame = self._rows_to_frame(rows, header, regular_header, pd, keep)
                        rows = []
                        if gc_was_enabled:
                            gc.enable()
                        yield frame
                finally:
                    if gc_was_enabled:
                        gc.enable()

        except ValueError:
            raise
        except FileNotFoundError as e:
            raise ValueError(
                f"CSVConnector [{self.name}]: Fichier introuvable lors de l'ouverture.\n"
                f"  Chemin : {csv_path}\n"
                f"  Erreur système : {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"CSVConnector [{self.name}]: Échec lecture CSV.\n"
                f"  Chemin : {csv_path}\n"
                f"  base_path : {self._settings.base_path}\n"
                f"  Erreur : {type(e).__name__}: {e}"
            ) from e

    def _extract_frames_rust(
        self,
        *,
        table: str,
        batch_size: int = 10_000,
        query: Optional[str] = None,
    ) -> Iterator["pd.DataFrame"]:
        """
        Implémentation Rust de « csv.read » (module hydra_native), mêmes lots et
        mêmes DataFrames que la version Python. Rend la main à Python, avec un
        avertissement, dès que le lecteur Rust ne peut garantir un résultat
        identique (encodage autre qu'UTF-8, BOM, UTF-8 invalide, NUL, guillemet
        ouvert en fin de fichier...) — y compris en cours de lecture, en reprenant
        après les lignes déjà rendues.
        """
        import pandas as pd
        import hydra_native

        csv_path = self._validated_source_path(table=table, batch_size=batch_size, query=query)

        def handover(reason: str, skip_rows: int = 0) -> Iterator["pd.DataFrame"]:
            from hydra_etl._backend import _t
            warn_once(f"csv.read:{csv_path}:{reason}",
                      _t("backend.rust_fallback", path=str(csv_path), reason=reason))
            return self._frames_python(csv_path, batch_size, skip_rows=skip_rows)

        if csv_path.stat().st_size < self.rust_min_bytes:
            logger.debug("CSVConnector: %s below rust_min_bytes, Python reader used", csv_path)
            yield from self._frames_python(csv_path, batch_size)
            return
        if self._settings.encoding.strip().lower().replace("_", "-") not in ("utf-8", "utf8"):
            yield from handover(f"encoding {self._settings.encoding!r}")
            return
        try:
            reader = hydra_native.CsvBatchReader(
                str(csv_path),
                delimiter=self._settings.delimiter,
                quotechar=self._settings.quotechar,
                batch_size=batch_size,
            )
        except hydra_native.CsvFallback as e:
            yield from handover(str(e.args[0]))
            return
        except Exception as e:  # noqa: BLE001 - Python produira son propre message d'erreur
            yield from handover(f"{type(e).__name__}: {e}")
            return

        header = reader.header
        if not header:
            raise ValueError(f"CSVConnector: en-tête CSV manquante ou vide: {csv_path}")
        regular_header = len(set(header)) == len(header)
        keep = self._kept_columns(header)

        batches = iter(reader)
        while True:
            try:
                batch = next(batches)
            except StopIteration:
                return
            except hydra_native.CsvFallback as e:
                yield from handover(str(e.args[0]), skip_rows=reader.rows_emitted)
                return
            if isinstance(batch, list):
                yield self._rows_to_frame(batch, header, regular_header, pd, keep)
            else:
                if keep:
                    # sous-ensemble côté Arrow : les colonnes écartées ne sont
                    # jamais converties en pandas
                    batch = batch.select(list(keep))
                yield batch.to_pandas()

    @staticmethod
    def _rows_to_frame(rows: List[List[str]], header: List[str], regular_header: bool, pd: Any,
                       keep: Optional[List[str]] = None) -> Any:
        n = len(header)
        if regular_header and all(len(r) == n for r in rows):
            if keep:
                # Les colonnes ecartees ne deviennent jamais des Series.
                wanted = set(keep)
                cols = {h: list(col) for h, col in zip(header, zip(*rows)) if h in wanted}
                return pd.DataFrame(cols, columns=keep)
            return pd.DataFrame({h: list(col) for h, col in zip(header, zip(*rows))}, columns=header)
        # Cas irrégulier : reproduction exacte de csv.DictReader.__next__,
        # puis restriction — la parité prime sur le gain.
        records: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(zip(header, r))
            lr = len(r)
            if n < lr:
                d[None] = r[n:]
            elif n > lr:
                for key in header[lr:]:
                    d[key] = None
            records.append(d)
        frame = pd.DataFrame(records)
        if keep:
            present = [c for c in keep if c in frame.columns]
            if present:
                frame = frame.loc[:, present]
        return frame

    def _validated_source_path(self, *, table: str, batch_size: int, query: Optional[str]) -> Path:
        """Mêmes contrôles et mêmes messages que le début d'extract_batches.
        À garder aligné avec extract_batches (test : tests/test_frame_io_parity.py)."""
        if query is not None and str(query).strip():
            raise ValueError("CSVConnector: 'query' n'est pas supporté pour CSV. Utilisez 'table' (chemin fichier).")

        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("CSVConnector: 'batch_size' doit être un entier >= 1.")

        if batch_size > 100_000:
            logger.warning(
                "CSVConnector: batch_size très élevé (%d). Risque de consommation mémoire importante.",
                batch_size
            )

        csv_path = self._resolve_path(table)

        if not csv_path.exists():
            raise ValueError(
                f"CSVConnector [{self.name}]: Fichier source introuvable.\n"
                f"  Chemin demandé : {table}\n"
                f"  Chemin résolu : {csv_path}\n"
                f"  base_path effectif : {self._settings.base_path}\n"
                f"  job_dir : {self._job_dir}\n"
                f"  CWD actuel : {Path.cwd()}\n"
                f"  Conseil : Vérifiez que le fichier existe ou que base_path est correct."
            )
        if not csv_path.is_file():
            raise ValueError(
                f"CSVConnector [{self.name}]: La source n'est pas un fichier (peut-être un dossier ?).\n"
                f"  Chemin : {csv_path}"
            )
        return csv_path

    @dual("csv.write", rust="_load_batches_rust")
    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """Écriture CSV — aiguillage Python / Rust (opération « csv.write »)."""
        return self._load_batches_python(batches, table=table, mode=mode, key=key)

    def _load_batches_python(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """
        Charge des batches dans un fichier CSV (implémentation de référence).

        Modes MVP :
        - replace : écrase le fichier et réécrit l'en-tête
        - append  : ajoute des lignes (écrit l'en-tête si le fichier n'existe pas ou est vide)

        Notes :
        - `key` ignoré (upsert non supporté en MVP).
        - On déduit les colonnes depuis le premier batch non vide.
        
        ✅ CORRECTIONS :
        - need_header déterminé AVANT open() du fichier
        - Validation stricte des colonnes si strict_schema=True
        - Création automatique du dossier parent (Étape 7)
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

        # ✅ CORRECTIF ÉTAPE 7 : Création automatique du dossier parent
        try:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(
                f"CSVConnector [{self.name}]: Impossible de créer le dossier destination.\n"
                f"  Chemin cible : {csv_path}\n"
                f"  Dossier parent : {csv_path.parent}\n"
                f"  Erreur système : {e}"
            )

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

        # Déterminer need_header AVANT d'ouvrir le fichier
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
        except FileNotFoundError as e:
            # ✅ CORRECTIF ÉTAPE 7 : Message ultra-détaillé
            raise ValueError(
                f"CSVConnector [{self.name}]: Impossible de créer/ouvrir le fichier destination.\n"
                f"  Chemin demandé : {table}\n"
                f"  Chemin résolu : {csv_path}\n"
                f"  Dossier parent : {csv_path.parent} (existe: {csv_path.parent.exists()})\n"
                f"  base_path effectif : {self._settings.base_path}\n"
                f"  job_dir : {self._job_dir}\n"
                f"  CWD actuel : {Path.cwd()}\n"
                f"  Erreur système : {e}\n"
                f"  Conseil : Le dossier parent devrait être créé automatiquement. "
                f"Vérifiez les permissions d'écriture."
            ) from e
        except Exception as e:
            raise ValueError(
                f"CSVConnector [{self.name}]: Échec écriture CSV.\n"
                f"  Chemin : {csv_path}\n"
                f"  Mode : {mode_norm}\n"
                f"  Erreur : {type(e).__name__}: {e}"
            ) from e

    # ---------------------------------------------------------------------
    # Ecriture par batch
    # ---------------------------------------------------------------------

    # En dessous de ce nombre de lignes, le surcoût fixe du chemin Rust dépasse
    # le gain (mesuré : 20 lignes -> +8 % sans ce seuil).
    rust_min_write_rows = 5_000

    # dtypes pandas dont le rendu texte est reproduit à l'identique côté Rust.
    _RUST_WRITE_DTYPES = ("str", "string", "int64", "int32", "Int64", "Int32",
                          "float64", "float32", "Float64", "Float32", "bool", "boolean")

    @classmethod
    def _rust_writable(cls, frame: "pd.DataFrame") -> bool:
        """Vrai si chaque colonne a un équivalent exact côté Rust.

        Une valeur manquante n'est écrite de la même façon que si le type la
        représente par pd.NA (Int64, boolean, Float64, string), rendu « vide ».
        Les types dont la valeur manquante est NaN (float64, dtype « str » de
        pandas 3) s'écrivent « nan » côté Python : ces colonnes ne passent par
        Rust que si elles ne contiennent aucune valeur manquante."""
        import pandas as pd

        for _, col in frame.items():
            if str(col.dtype) not in cls._RUST_WRITE_DTYPES:
                return False
            if getattr(col.dtype, "na_value", None) is not pd.NA and col.isna().any():
                return False
        return True

    def _load_batches_rust(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """
        Implémentation Rust de « csv.write » : rend les mêmes octets que le
        chemin Python (voir rust/hydra_native/src/writer.rs). Repasse la main à
        Python — validations, messages d'erreur, types non gérés — dès que la
        parité n'est pas garantie.
        """
        import pyarrow as pa
        import hydra_native

        items = list(batches)
        frames = [b for b in items if isinstance(b, FrameBatch) and len(b)]
        usable = (
            items
            and key is None
            and isinstance(mode, str)
            and mode.strip().lower() in {"append", "replace"}
            and all(isinstance(b, FrameBatch) for b in items)
            and frames
            and sum(len(f) for f in frames) >= self.rust_min_write_rows
            and all(f.columns == frames[0].columns for f in frames)
            and all(self._rust_writable(f.frame) for f in frames)
        )
        if not usable:
            return self._load_batches_python(items, table=table, mode=mode, key=key)

        mode_norm = mode.strip().lower()
        csv_path = self._resolve_path(table)
        try:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return self._load_batches_python(items, table=table, mode=mode, key=key)

        fieldnames = [str(c) for c in frames[0].columns]
        need_header = mode_norm == "replace" or not csv_path.exists() or csv_path.stat().st_size == 0
        append = mode_norm != "replace"

        written = 0
        try:
            for frame_batch in frames:
                rb = pa.RecordBatch.from_pandas(frame_batch.frame, preserve_index=False)
                hydra_native.write_csv(
                    str(csv_path),
                    rb,
                    append=append,
                    header=fieldnames if need_header else None,
                    delimiter=self._settings.delimiter,
                    quotechar=self._settings.quotechar,
                    lineterminator=self._settings.lineterminator,
                )
                written += 1
                need_header = False
                append = True
        except hydra_native.CsvFallback as e:
            if written:
                # Des lignes sont déjà écrites : repasser par Python les dupliquerait.
                raise ValueError(
                    f"CSVConnector [{self.name}]: Échec écriture CSV.\n"
                    f"  Chemin : {csv_path}\n"
                    f"  Erreur : {e.args[0]}"
                ) from e
            from hydra_etl._backend import _t
            warn_once(f"csv.write:{csv_path}:{e.args[0]}",
                      _t("backend.rust_fallback", path=str(csv_path), reason=str(e.args[0])))
            return self._load_batches_python(items, table=table, mode=mode, key=key)

    def _write_one_batch(self, writer: csv.DictWriter, batch: Batch, fieldnames: List[str]) -> None:
        """
        Ecrit un batch de lignes avec validation optionnelle du schéma.

        Règle :
        - Si une ligne manque une colonne, csv.DictWriter mettra vide.
        - Si une ligne contient des colonnes en trop, comportement dépend de strict_schema :
          * strict_schema=False : extrasaction="ignore" les ignore (silencieux)
          * strict_schema=True  : lève ValueError (fail-fast)
        
        ✅ Validation stricte des colonnes si activée
        """
        # Étape 0-bis : batch porté par un DataFrame -> écriture colonne à colonne,
        # mêmes valeurs que le chemin dict (voir frame_batch.py).
        if isinstance(batch, FrameBatch) and batch.columns == list(fieldnames):
            writer.writer.writerows(batch.rows())
            return

        expected_cols = set(fieldnames)

        for row in batch:
            if not isinstance(row, dict):
                raise ValueError("CSVConnector: chaque ligne d'un batch doit être un dict.")

            # Validation stricte si activée
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