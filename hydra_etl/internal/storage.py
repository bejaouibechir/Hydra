"""
Stockage objet — code commun à S3, Azure Blob / ADLS et GCS (fsspec).

Un emplacement distant s'écrit comme une URI, dans les clés de chemin qui
existent déjà (connection.base_path, extract.table, load.table, path d'un
déclencheur fichier) :

    s3://bucket/dossier/fichier.csv        pip install "hydra-etl[s3]"   (S3, MinIO…)
    az://conteneur/dossier/fichier.csv     pip install "hydra-etl[azure]" (abfs://, abfss:// aussi)
    gs://bucket/dossier/fichier.csv        pip install "hydra-etl[gcs]"   (gcs:// aussi)

Les identifiants vont dans `connection.storage` (transmis tels quels au
système de fichiers fsspec : key / secret / endpoint_url pour S3, account_name /
account_key / connection_string / sas_token pour Azure, token / project pour GCS),
sinon les variables d'environnement standard de chaque service sont utilisées.

Approche « copie locale » : les connecteurs CSV, JSON et Parquet ne savent lire
et écrire que des fichiers locaux, et gardent ainsi tous leurs chemins rapides
(lecteur Rust, moteur grand volume, multi-fichiers).
- source : les fichiers (motif compris) sont téléchargés dans un dossier temporaire ;
- destination : le fichier est écrit en local puis envoyé à la publication, en un
  seul envoi : le stockage objet ne rend visible un objet qu'une fois complet,
  donc une destination distante est toujours tout ou rien. En `append`, le fichier
  distant existant est d'abord téléchargé.
"""
from __future__ import annotations

import logging
import posixpath
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# protocole → (protocole fsspec, extra pip, nom affiché)
PROTOCOLS: Dict[str, Tuple[str, str, str]] = {
    "s3": ("s3", "s3", "S3"),
    "s3a": ("s3", "s3", "S3"),
    "az": ("abfs", "azure", "Azure Blob Storage"),
    "abfs": ("abfs", "azure", "Azure Blob Storage"),
    "abfss": ("abfs", "azure", "Azure Blob Storage"),
    "gs": ("gcs", "gcs", "Google Cloud Storage"),
    "gcs": ("gcs", "gcs", "Google Cloud Storage"),
}
RESERVED = ("sftp", "ftp", "http", "https")          # pas encore pris en charge : refusés clairement
_GLOB = "*?["


def scheme(path: Any) -> Optional[str]:
    s = str(path or "").strip()
    i = s.find("://")
    if i <= 1:                     # « C:\… » sous Windows n'est pas une URI
        return None
    return s[:i].lower()


def is_remote(path: Any) -> bool:
    return scheme(path) is not None


def check_uri(path: str, what: str) -> str:
    sc = scheme(path)
    if sc is None:
        return path
    if sc in PROTOCOLS:
        rest = str(path).split("://", 1)[1]
        if not rest or rest.startswith("/"):
            raise ValueError(f"{what}: '{path}' has no bucket or container")
        return path
    if sc in RESERVED:
        raise ValueError(f"{what}: '{sc}://' locations are not supported yet "
                         f"(supported: s3://, az://, gs://)")
    raise ValueError(f"{what}: unknown location scheme '{sc}://' (supported: s3://, az://, gs://)")


def filesystem(uri: str, options: Optional[Dict[str, Any]] = None):
    """Système de fichiers fsspec pour cette URI ; message d'installation si l'extra manque."""
    sc = scheme(uri)
    proto, extra, label = PROTOCOLS[sc]
    try:
        import fsspec  # type: ignore
        return fsspec.filesystem(proto, **dict(options or {}))
    except ImportError as e:
        raise ValueError(f"{label} needs an extra package: pip install \"hydra-etl[{extra}]\" "
                         f"({e.name or e})") from e
    except ValueError as e:
        if "not available" in str(e).lower() or "install" in str(e).lower():
            raise ValueError(f"{label} needs an extra package: pip install \"hydra-etl[{extra}]\"") from e
        raise


def join(base: Optional[str], table: str) -> str:
    """URI d'un fichier : `table` absolue (URI) ou relative à `base`."""
    if is_remote(table):
        return table
    if not base:
        return table
    root, path = base.split("://", 1)
    return f"{root}://{posixpath.join(path.rstrip('/'), table.lstrip('/'))}"


def _strip(uri: str) -> str:
    return uri.split("://", 1)[1]


class RemoteFiles:
    """Copie locale d'une source ou d'une destination distante, pour un job."""

    def __init__(self, uri: str, options: Optional[Dict[str, Any]], *, name: str) -> None:
        self.uri = uri
        self.name = name
        self.fs = filesystem(uri, options)
        self.dir = Path(tempfile.mkdtemp(prefix="hydra-remote-"))

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    # ── Source ──
    def download(self) -> str:
        """Télécharge le fichier (ou les fichiers du motif) ; renvoie le chemin local
        à lire : même nom, ou même motif relatif à la copie."""
        pattern = _strip(self.uri)
        if any(c in pattern for c in _GLOB):
            cut = min(pattern.find(c) for c in _GLOB if c in pattern)
            root = pattern[:cut].rsplit("/", 1)[0]
            try:
                found = sorted(p for p in self.fs.glob(pattern) if not self.fs.isdir(p))
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"source '{self.name}': cannot list {self.uri}: {e}") from e
            if not found:
                raise ValueError(f"source '{self.name}': no file matches {self.uri}")
            for p in found:
                local = self.dir / p[len(root):].lstrip("/")
                local.parent.mkdir(parents=True, exist_ok=True)
                self._get(p, local)
            logger.info("source '%s': %d file(s) downloaded from %s", self.name, len(found), self.uri)
            return pattern[len(root):].lstrip("/")
        local = self.dir / posixpath.basename(pattern)
        self._get(pattern, local)
        return local.name

    def _get(self, remote: str, local: Path) -> None:
        try:
            self.fs.get_file(remote, str(local))
        except FileNotFoundError as e:
            raise ValueError(f"source '{self.name}': file not found: {self.uri if remote in self.uri else remote}") from e
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"source '{self.name}': cannot download {remote}: {type(e).__name__}: {e}") from e

    # ── Destination ──
    def prepare_target(self, mode: str) -> str:
        path = _strip(self.uri)
        if any(c in path for c in _GLOB):
            raise ValueError(f"destination '{self.name}': a pattern cannot be written ({self.uri})")
        local = self.dir / posixpath.basename(path)
        if mode == "append":
            try:
                if self.fs.exists(path):
                    self.fs.get_file(path, str(local))
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"destination '{self.name}': cannot read {self.uri} to append to it: {e}") from e
        return local.name

    def upload(self, local_name: str) -> None:
        local = self.dir / local_name
        if not local.exists():
            return                                   # rien d'écrit (aucun lot) : la cible reste telle quelle
        path = _strip(self.uri)
        try:
            self.fs.put_file(str(local), path)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"destination '{self.name}': upload to {self.uri} failed; the remote file is "
                             f"unchanged. {type(e).__name__}: {e}") from e
        logger.info("destination '%s': %s uploaded", self.name, self.uri)


FILE_TYPES = ("csv", "json", "parquet")


def localize(defn: Dict[str, Any], *, name: str, is_source: bool) -> Optional[Tuple["RemoteFiles", str]]:
    """Remplace, dans la définition YAML d'une source ou d'une destination fichier,
    l'emplacement distant par une copie locale. Renvoie (copie, nom local) ou None."""
    if not isinstance(defn, dict) or str(defn.get("type", "")).lower() not in FILE_TYPES:
        return None
    conn = defn.get("connection") if isinstance(defn.get("connection"), dict) else {}
    block = "extract" if is_source else "load"
    io = defn.get(block) if isinstance(defn.get(block), dict) else {}
    base = conn.get("base_path")
    table = io.get("table") or io.get("file")
    what = f"{'source' if is_source else 'destination'} '{name}'"
    base_remote = is_remote(base)
    if not base_remote and not is_remote(table):
        if conn.get("storage"):
            raise ValueError(f"{what}: connection.storage is set but neither base_path nor the table "
                             f"is a remote location (s3://, az://, gs://)")
        return None
    if base_remote:
        check_uri(base, f"{what}: connection.base_path")
    if not table:
        raise ValueError(f"{what}: {block}.table is required")
    check_uri(str(table), f"{what}: {block}.table")
    uri = join(base if base_remote else None, str(table))
    if not is_remote(uri):
        raise ValueError(f"{what}: a local base_path cannot hold a remote table")
    options = conn.get("storage") if isinstance(conn.get("storage"), dict) else {}
    rf = RemoteFiles(uri, options, name=name)
    try:
        local = rf.download() if is_source else rf.prepare_target(str(io.get("mode") or "replace"))
    except BaseException:
        rf.cleanup()
        raise
    new_conn = {k: v for k, v in conn.items() if k != "storage"}
    new_conn["base_path"] = str(rf.dir)
    defn["connection"] = new_conn
    new_io = dict(io)
    new_io.pop("file", None)
    # chemin absolu : JSON et Parquet lisent les chemins relatifs depuis le dossier du job
    new_io["table"] = str(rf.dir / local)
    defn[block] = new_io
    return rf, local
