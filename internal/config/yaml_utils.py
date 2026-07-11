"""
Utilitaires de lecture YAML robustes.

Gère les encodages Windows : UTF-8, UTF-8 avec BOM (0xEF 0xBB 0xBF),
UTF-16 LE avec BOM (0xFF 0xFE) — produit par Notepad et certains éditeurs.
"""
from __future__ import annotations

from pathlib import Path


def read_yaml_text(path: Path) -> str:
    """
    Lit un fichier YAML en gérant automatiquement les encodages Windows.

    Ordre de tentative : utf-8-sig (UTF-8 + BOM), utf-16, utf-8, latin-1.
    utf-8-sig gère le BOM silencieusement.
    utf-16 gère les fichiers sauvegardés par Notepad en mode Unicode.

    Args:
        path: Chemin vers le fichier YAML.

    Returns:
        Contenu textuel du fichier.

    Raises:
        ValueError: Si aucun encodage ne fonctionne.
    """
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError(
        f"Impossible de lire '{path.name}' : encodage non reconnu. "
        f"Sauvegardez le fichier en UTF-8 sans BOM."
    )
