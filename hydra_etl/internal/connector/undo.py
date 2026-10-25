"""
Annulation d'un chargement déjà publié (`rollback: true` d'un workflow).

Quand un workflow échoue, ses jobs déjà publiés sont annulés en pile (le
dernier publié d'abord). Pour cela, chaque session de chargement ouverte avec
`undo=True` garde, AVANT d'écrire, de quoi revenir en arrière :

| Destination | replace | append | upsert |
|---|---|---|---|
| CSV / Parquet | ancien fichier gardé à côté (renommage) | taille d'origine (CSV) / ancien fichier (Parquet) | — |
| Bases | copie de la table (`hydra_bak_…`) | clés insérées (`load.key` exigée, clés neuves seulement) | anciennes lignes + clés insérées |

`UndoRecord.undo()` remet la destination dans son état d'avant le job ;
`discard()` supprime les sauvegardes (workflow réussi). Avant d'annuler, on
vérifie que la destination n'a pas changé depuis la publication (taille et
date d'un fichier, nombre de lignes d'une table) : si un autre programme y a
écrit, l'annulation est refusée (`UndoConflict`) plutôt que d'effacer son
travail.

Les enregistrements sont sérialisables (`to_dict` / `undo_from_dict`) pour le
journal d'annulation (reprise après un arrêt brutal). Jamais de secret dedans :
la connexion est reconstruite à partir du job.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class UndoConflict(RuntimeError):
    """La destination a changé depuis la publication : annulation refusée."""


class UndoUnavailable(ValueError):
    """Ce chargement ne pourra pas être annulé (connecteur, mode, clé manquante)."""


def backup_path_for(target: Path) -> Path:
    return target.with_name(f".{target.name}.hydra-bak-{os.getpid()}-{uuid.uuid4().hex[:8]}")


def backup_table_name(table: str) -> str:
    """Nom court (limites PostgreSQL 63, MySQL 64) dans le même schéma."""
    base = table.split(".")[-1].strip('"`[]')[:30]
    return f"hydra_bak_{base}_{uuid.uuid4().hex[:8]}"


def _stat(path: Path) -> Optional[List[int]]:
    try:
        st = path.stat()
        return [st.st_size, st.st_mtime_ns]
    except FileNotFoundError:
        return None


@dataclass
class UndoRecord:
    kind: str = ""                     # file | db
    target: str = ""                   # fichier ou table
    mode: str = ""                     # replace | append | upsert
    job_dir: str = ""                  # pour reconstruire la connexion (journal)
    dest_id: str = ""
    partial: bool = False              # job en échec qui avait déjà écrit

    def describe(self) -> str:
        return f"{self.mode} {self.target}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def undo(self, connector: Any = None) -> str:
        raise NotImplementedError

    def discard(self, connector: Any = None) -> None:
        pass


@dataclass
class FileUndo(UndoRecord):
    kind: str = "file"
    backup: Optional[str] = None       # ancien fichier (replace)
    existed: bool = True
    orig_size: Optional[int] = None    # append CSV : taille avant le job
    after: Optional[List[int]] = None  # [taille, mtime_ns] juste après publication

    def seal(self) -> "FileUndo":
        self.after = _stat(Path(self.target))
        return self

    def undo(self, connector: Any = None) -> str:
        path = Path(self.target)
        now = _stat(path)
        if self.after is not None and now != self.after:
            raise UndoConflict(f"{path} changed after this run wrote it (size or date): "
                               f"not restored, to keep the other changes")
        if self.backup:
            os.replace(self.backup, path)
            return f"{path}: previous file restored"
        if self.orig_size is not None:
            os.truncate(path, self.orig_size)
            return f"{path}: back to {self.orig_size} bytes"
        if not self.existed:
            if path.exists():
                path.unlink()
            return f"{path}: removed (it did not exist before)"
        return f"{path}: nothing to undo"

    def discard(self, connector: Any = None) -> None:
        if self.backup:
            try:
                Path(self.backup).unlink()
            except FileNotFoundError:
                pass


@dataclass
class DBUndo(UndoRecord):
    kind: str = "db"
    backup_table: Optional[str] = None           # replace : copie de la table
    created: bool = False                        # table créée par le job
    key: List[str] = field(default_factory=list)
    inserted_keys: List[List[Any]] = field(default_factory=list)
    old_rows: List[Dict[str, Any]] = field(default_factory=list)   # upsert : lignes d'avant
    count_after: Optional[int] = None

    def undo(self, connector: Any = None) -> str:
        if connector is None:
            raise UndoUnavailable("a database connection is needed to undo this load")
        return connector._undo_load(self)

    def discard(self, connector: Any = None) -> None:
        if self.backup_table and connector is not None:
            connector._discard_undo(self)


def undo_from_dict(d: Dict[str, Any]) -> UndoRecord:
    cls = {"file": FileUndo, "db": DBUndo}.get(d.get("kind", ""))
    if cls is None:
        raise ValueError(f"unknown undo record: {d.get('kind')!r}")
    names = set(cls.__dataclass_fields__)
    return cls(**{k: v for k, v in d.items() if k in names})
