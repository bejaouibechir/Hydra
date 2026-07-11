#!/usr/bin/env python3
"""
safe_write — écriture sécurisée sur mount Linux -> NTFS (anti-truncation).

Problème : sur un mount Linux -> Windows NTFS, un `f.write(gros_contenu)` en une
seule passe peut être tronqué silencieusement au-delà de ~32 KB.

Ce module écrit par petits chunks, fait un backup horodaté automatique, puis
VÉRIFIE la taille réellement présente sur le disque. En cas d'écart, il lève
une exception (donc échec bruyant plutôt que corruption silencieuse).

Usage — import :
    from safe_write import safe_write
    safe_write("/chemin/fichier.tsx", content)

Usage — CLI (vérifier un fichier déjà écrit) :
    python3 scripts/safe_write.py --check /chemin/fichier.tsx --expect-lines 2143

Zéro dépendance externe (stdlib uniquement).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

CHUNK_LINES = 50  # nb de lignes écrites par flush


def _backup(path: Path) -> Path | None:
    """Copie horodatée du fichier existant dans <dir>/_backups/. None si absent."""
    if not path.exists():
        return None
    backups = path.parent / "_backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backups / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, dest)
    return dest


def safe_write(
    path: str | os.PathLike,
    content: str,
    *,
    backup: bool = True,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> dict:
    """
    Écrit `content` dans `path` par chunks + backup + vérification post-écriture.

    Retourne un dict {path, backup, expected_bytes, written_bytes,
                      expected_lines, written_lines}.
    Lève RuntimeError si la taille/lignes sur disque ne correspond pas.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    bak = _backup(path) if backup else None

    # Normaliser les fins de ligne selon `newline` (LF par défaut, cf. .gitattributes)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        normalized = normalized.replace("\n", newline)

    expected_bytes = len(normalized.encode(encoding))
    expected_lines = normalized.count(newline) + (
        0 if normalized.endswith(newline) or normalized == "" else 1
    )

    # Écriture par chunks de CHUNK_LINES lignes, flush + fsync à chaque bloc.
    lines = normalized.splitlines(keepends=True)
    with open(path, "w", encoding=encoding, newline="") as f:
        for i in range(0, len(lines), CHUNK_LINES):
            f.write("".join(lines[i : i + CHUNK_LINES]))
            f.flush()
            os.fsync(f.fileno())

    # Vérification stricte sur disque.
    written_bytes = path.stat().st_size
    with open(path, "r", encoding=encoding, newline="") as f:
        disk = f.read()
    written_lines = disk.count(newline) + (
        0 if disk.endswith(newline) or disk == "" else 1
    )

    report = {
        "path": str(path),
        "backup": str(bak) if bak else None,
        "expected_bytes": expected_bytes,
        "written_bytes": written_bytes,
        "expected_lines": expected_lines,
        "written_lines": written_lines,
    }

    if written_bytes != expected_bytes:
        raise RuntimeError(
            f"TRUNCATION DÉTECTÉE sur {path} : "
            f"{written_bytes} octets sur disque, {expected_bytes} attendus. "
            f"Backup dispo : {bak}"
        )
    return report


def check_file(path: str | os.PathLike, expect_lines: int | None = None) -> dict:
    """Vérifie qu'un fichier est lisible et (option) a le nb de lignes attendu."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8", newline="") as f:
        disk = f.read()
    n = disk.count("\n") + (0 if disk.endswith("\n") or disk == "" else 1)
    report = {"path": str(path), "bytes": path.stat().st_size, "lines": n}
    if expect_lines is not None and n != expect_lines:
        raise RuntimeError(
            f"ÉCART DE LIGNES sur {path} : {n} sur disque, {expect_lines} attendues."
        )
    return report


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Écriture/vérification anti-truncation.")
    p.add_argument("--check", metavar="FILE", help="Vérifier un fichier existant.")
    p.add_argument("--expect-lines", type=int, default=None)
    args = p.parse_args(argv)

    if args.check:
        try:
            rep = check_file(args.check, args.expect_lines)
            print(f"OK  {rep['path']}  ({rep['lines']} lignes, {rep['bytes']} octets)")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"ÉCHEC  {exc}", file=sys.stderr)
            return 1

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
