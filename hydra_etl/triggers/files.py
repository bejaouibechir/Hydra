"""Événements de fichiers pour les déclencheurs `file` et `marker`.

Socle commun, indépendant de l'endroit où sont les fichiers :

- `FileEventSource` : liste les fichiers d'un motif (chemin, date, taille) et
  sait en supprimer un. `LocalSource` = dossier du projet (ce lot).
  `SftpSource` et `S3Source` sont réservées : même interface, à implémenter
  plus tard (triggers.yaml ne les accepte pas encore).
- `FileWatcher` : compare les listes successives (scrutation, pas de dépendance
  système) et produit les événements `added` / `modified`, une fois le fichier
  stable pendant `debounce` (un fichier encore en cours de copie n'est pas pris).

Les fichiers présents au démarrage forment l'état de départ : ils ne
déclenchent rien. Un fichier supprimé puis recréé redevient `added`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

Sig = Tuple[float, int]          # (date de modification, taille)


class FileEventSource:
    """Endroit où des fichiers arrivent."""
    kind = "abstract"

    def list(self, pattern: str) -> Dict[str, Sig]:
        """Chemins (relatifs, séparateur /) qui correspondent au motif → (mtime, taille)."""
        raise NotImplementedError

    def delete(self, path: str) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return self.kind


class LocalSource(FileEventSource):
    """Dossier local : la racine du projet. Motifs glob, `**` pour les sous-dossiers."""
    kind = "local"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def list(self, pattern: str) -> Dict[str, Sig]:
        out: Dict[str, Sig] = {}
        pat = pattern.replace("\\", "/")
        for p in self.root.glob(pat):
            try:
                if not p.is_file():
                    continue
                st = p.stat()
            except OSError:            # supprimé entre-temps
                continue
            out[p.relative_to(self.root).as_posix()] = (st.st_mtime, st.st_size)
        return out

    def delete(self, path: str) -> None:
        target = (self.root / path).resolve()
        if self.root not in target.parents:
            raise ValueError(f"{path} is outside the project")
        target.unlink()

    def describe(self) -> str:
        return str(self.root)


class _Planned(FileEventSource):
    """Source distante réservée : l'interface est là, l'accès viendra plus tard."""

    def __init__(self, url: str):
        self.url = url

    def list(self, pattern: str) -> Dict[str, Sig]:
        raise NotImplementedError(f"{self.kind} file triggers are not available yet ({self.url})")

    def delete(self, path: str) -> None:
        raise NotImplementedError(f"{self.kind} file triggers are not available yet ({self.url})")

    def describe(self) -> str:
        return self.url


class SftpSource(_Planned):
    kind = "sftp"


class S3Source(_Planned):
    kind = "s3"


def source_for(root: Path, location: Optional[str] = None) -> FileEventSource:
    """Source d'un déclencheur : None = dossier du projet ; sftp://… ou s3://… plus tard."""
    if not location:
        return LocalSource(root)
    scheme = urlparse(location).scheme.lower()
    if scheme == "sftp":
        return SftpSource(location)
    if scheme == "s3":
        return S3Source(location)
    raise ValueError(f"unsupported file location '{location}' (local folder, later sftp:// or s3://)")


@dataclass
class FileEvent:
    path: str
    kind: str                     # added | modified


@dataclass
class FileWatcher:
    """Compare les listes successives d'une source pour un motif."""
    source: FileEventSource
    pattern: str
    events: List[str] = field(default_factory=lambda: ["added"])
    debounce: float = 2.0
    known: Dict[str, Sig] = field(default_factory=dict)
    pending: Dict[str, Tuple[Sig, float, str]] = field(default_factory=dict)
    started: bool = False

    def baseline(self) -> None:
        """État de départ : les fichiers déjà là ne déclenchent rien."""
        self.known = self.source.list(self.pattern)
        self.pending = {}
        self.started = True

    def poll(self, now: float) -> List[FileEvent]:
        """Événements des fichiers devenus stables depuis `debounce` secondes."""
        if not self.started:
            self.baseline()
            return []
        current = self.source.list(self.pattern)
        out: List[FileEvent] = []
        for path in list(self.known):
            if path not in current:            # supprimé : redeviendra `added`
                del self.known[path]
                self.pending.pop(path, None)
        for path, sig in sorted(current.items()):
            if self.known.get(path) == sig:
                self.pending.pop(path, None)
                continue
            kind = "modified" if path in self.known else "added"
            seen = self.pending.get(path)
            if seen is None or seen[0] != sig:
                self.pending[path] = (sig, now, kind if seen is None else seen[2])
                if self.debounce > 0:
                    continue
                seen = self.pending[path]
            if now - seen[1] >= self.debounce:
                del self.pending[path]
                self.known[path] = sig
                if seen[2] in self.events:
                    out.append(FileEvent(path, seen[2]))
        return out
