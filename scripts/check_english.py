#!/usr/bin/env python3
"""
Contrôle de la règle −2 de CLAUDE.md : tout ce qu'un utilisateur peut lire est
en anglais. Le script est le garde-fou programmatique de cette règle — il se
lance avant toute livraison d'un artefact destiné à l'utilisateur.

Ce qui est inspecté : chaînes d'interface, métadonnées de paquet, schémas,
snippets, exemples, README et CHANGELOG livrés.

Ce qui est ignoré : CLAUDE.md, documentations/, scripts de contrôle interne,
commentaires de code Python et TypeScript non exposés.

Usage :
    python scripts/check_english.py "vscode-extension"
    python scripts/check_english.py cli/locales/en.json studio/src
    python scripts/check_english.py            # cibles par defaut

Sortie : 0 si aucune occurrence, 1 sinon.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TARGETS = ["vscode-extension", "cli/locales/en.json"]

INSPECTED_SUFFIXES = {".json", ".md", ".yaml", ".yml", ".xml", ".vsixmanifest", ".txt"}

SKIPPED_DIRS = {
    "node_modules", "__pycache__", ".git", "_backups", "_archive",
    "documentations", "scripts", "dist", "build",
}
SKIPPED_NAMES = {"CLAUDE.md", "pnpm-lock.yaml", "package-lock.json"}

# Mot accentué, ou mot français courant sans accent. Les termes ambigus
# (table, description, port, format, mode, note, image, simple…) sont exclus :
# ils sont identiques en anglais et produiraient du bruit.
FRENCH = re.compile(
    r"(?<![A-Za-z0-9_])("
    r"[a-zA-ZÀ-ÿ]*[éèêëàâçùûüîïôö][a-zA-ZÀ-ÿ]*"
    r"|les|des|une|aux|dans|pour|avec|sans|sous|sur|par|est|sont|etre"
    r"|que|qui|quand|dont|leur|leurs|cette|cet|ces|ceux|celui"
    r"|fichier|fichiers|dossier|dossiers|colonne|colonnes|ligne|lignes"
    r"|valeur|valeurs|champ|champs|nom|noms|erreur|erreurs|chaine|chaines"
    r"|utiliser|utilise|doit|peut|faut|aucun|aucune|chaque|toute|toutes|tous"
    r"|ajouter|supprimer|modifier|enregistrer|annuler|fermer|ouvrir|charger"
    r"|liste|clef|cles|donnees|reussi|echec|attendu|manquant|invalide"
    r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

# Faux positifs : mots anglais ou identifiants capturés par la regex ci-dessus.
ALLOWED = {
    "des", "que", "sur", "par", "est", "sont", "nom", "liste", "mode",
    "sans", "dans", "pour", "cet", "ces", "une",
}


def looks_french(line: str) -> list[str]:
    found = []
    for m in FRENCH.finditer(line):
        w = m.group(0)
        if w.lower() in ALLOWED:
            continue
        found.append(w)
    return found


def iter_files(target: Path):
    if target.is_file():
        yield target
        return
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIPPED_DIRS for part in p.relative_to(target).parts):
            continue
        if p.name in SKIPPED_NAMES:
            continue
        if p.suffix in INSPECTED_SUFFIXES or p.suffix == ".vsix":
            yield p


def scan_text(path: Path, label: str, hits: list) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    for i, line in enumerate(text.splitlines(), 1):
        words = looks_french(line)
        if words:
            hits.append((label, i, words, line.strip()[:78]))


def scan_vsix(path: Path, hits: list) -> None:
    """Un paquet livré est inspecté de l'intérieur : c'est lui que l'on publie."""
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.endswith(tuple(INSPECTED_SUFFIXES)):
                continue
            body = z.read(name).decode("utf-8", "replace")
            for i, line in enumerate(body.splitlines(), 1):
                words = looks_french(line)
                if words:
                    hits.append((f"{path.name}::{name}", i, words, line.strip()[:78]))


def main(argv: list[str]) -> int:
    targets = argv[1:] or DEFAULT_TARGETS
    hits: list = []
    scanned = 0

    for t in targets:
        target = (ROOT / t) if not Path(t).is_absolute() else Path(t)
        if not target.exists():
            print(f"cible introuvable : {t}")
            return 2
        for f in iter_files(target):
            scanned += 1
            if f.suffix == ".vsix":
                scan_vsix(f, hits)
            else:
                # La cible peut vivre hors du depot (archive extraite, dossier
                # temporaire) : on n'impose pas qu'elle soit sous ROOT.
                try:
                    label = str(f.relative_to(ROOT))
                except ValueError:
                    label = str(f)
                scan_text(f, label, hits)

    print(f"{scanned} fichier(s) inspecte(s) dans : {', '.join(targets)}")
    if not hits:
        print("Aucune occurrence francaise — regle -2 respectee.")
        return 0

    print(f"\n{len(hits)} ligne(s) suspecte(s) :\n")
    for label, line_no, words, snippet in hits:
        print(f"  {label}:{line_no}")
        print(f"     mots : {', '.join(sorted(set(words)))}")
        print(f"     {snippet}")
    print("\nLivraison bloquee : traduire ces chaines avant de publier.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
