"""
internal/fs_atomic.py — Écriture de fichiers atomique et sûre.

Problème : sur certains montages (Windows NTFS via bridge, réseau), réécrire un
fichier existant avec `open('w')` / `Path.write_text` peut laisser des octets
résiduels (padding NUL) ou tronquer si le nouveau contenu est plus court — ce
qui corrompt silencieusement JSON/YAML.

Solution : écrire dans un fichier temporaire du MÊME dossier puis remplacer la
cible par un renommage atomique (`os.replace`). La cible reçoit exactement les
octets voulus, sans résidu.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union


def atomic_write_text(
    path: Union[str, os.PathLike],
    data: str,
    encoding: str = "utf-8",
    newline: str = "",
) -> None:
    """Écrit `data` dans `path` de façon atomique (temp + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".__tmp_", suffix=path.suffix or ".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Union[str, os.PathLike], data: bytes) -> None:
    """Variante binaire de atomic_write_text."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".__tmp_", suffix=path.suffix or ".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
