"""
scripts/register_hdr_filetype.py
=================================
Associe l'extension .hdr à l'icône Hydra sur le système d'exploitation courant.

Usage:
    python scripts/register_hdr_filetype.py          # enregistre
    python scripts/register_hdr_filetype.py --undo   # supprime l'association

Compatibilité:
    Windows  → HKEY_CURRENT_USER\\Software\\Classes (pas besoin d'admin)
    macOS    → ~/Library/LaunchServices via duti (si installé)
    Linux    → ~/.local/share/mime/ + update-mime-database
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

# ── Chemins ─────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
HYDRA_ROOT = SCRIPT_DIR.parent
ICO_PATH   = HYDRA_ROOT / "studio" / "public" / "Hydra.ico"
PNG_PATH   = HYDRA_ROOT / "studio" / "public" / "Hydra.png"

UNDO = "--undo" in sys.argv


# ── Windows ──────────────────────────────────────────────────────────────────

def register_windows() -> None:
    import winreg

    if not ICO_PATH.exists():
        print(f"ERREUR: Icône introuvable : {ICO_PATH}")
        sys.exit(1)

    ico = str(ICO_PATH)
    base = r"Software\Classes"

    if UNDO:
        for sub in [
            r"Software\Classes\HydraDataRecipe\shell\open\command",
            r"Software\Classes\HydraDataRecipe\shell\open",
            r"Software\Classes\HydraDataRecipe\shell",
            r"Software\Classes\HydraDataRecipe\DefaultIcon",
            r"Software\Classes\HydraDataRecipe",
            r"Software\Classes\.hdr",
        ]:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                print(f"  Supprimé: {sub}")
            except FileNotFoundError:
                pass
        print("✅ Association .hdr supprimée.")
        return

    # .hdr → ProgID
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\.hdr") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "HydraDataRecipe")
        winreg.SetValueEx(k, "Content Type", 0, winreg.REG_SZ, "application/x-hydra-recipe")
        print(f"  Enregistré: HKCU\\{base}\\.hdr → HydraDataRecipe")

    # ProgID description
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\HydraDataRecipe") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Hydra Data Recipe")
        print(f"  Enregistré: HKCU\\{base}\\HydraDataRecipe")

    # Icône
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\HydraDataRecipe\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, ico)
        print(f"  Icône: {ico}")

    # Commande d'ouverture (ouvre avec Notepad par défaut — adapter si besoin)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\HydraDataRecipe\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, 'notepad.exe "%1"')
        print(f"  Ouvrir avec: notepad.exe")

    # Notifier Windows Explorer du changement
    try:
        from ctypes import windll
        windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # SHCNE_ASSOCCHANGED
        print("  Notification Explorer envoyée.")
    except Exception:
        pass

    print("\n✅ Association .hdr → icône Hydra enregistrée.")
    print("   Les fichiers .hdr affichent maintenant l'icône Hydra dans l'Explorateur.")


# ── macOS ────────────────────────────────────────────────────────────────────

def register_macos() -> None:
    # macOS utilise UTI (Uniform Type Identifier) via Info.plist
    # Pour une app non packagée, la méthode la plus simple est duti
    try:
        result = subprocess.run(["which", "duti"], capture_output=True, text=True)
        if result.returncode != 0:
            print("INFO: 'duti' non installé. Installez-le avec: brew install duti")
            print("      Ou associez manuellement .hdr avec votre éditeur de texte préféré.")
            return

        if UNDO:
            print("INFO: Suppression de l'association .hdr (macOS) non supportée automatiquement.")
            print("      Utilisez Finder → Info → Ouvrir avec pour modifier manuellement.")
            return

        # Associer .hdr à TextEdit (ou tout éditeur disponible)
        subprocess.run(["duti", "-s", "com.apple.TextEdit", ".hdr", "all"], check=True)
        print("✅ .hdr associé à TextEdit (macOS).")
        print("   Pour un autre éditeur, modifiez la commande avec l'identifiant bundle approprié.")

    except subprocess.CalledProcessError as e:
        print(f"ERREUR duti: {e}")


# ── Linux ─────────────────────────────────────────────────────────────────────

def register_linux() -> None:
    mime_dir  = Path.home() / ".local" / "share" / "mime"
    app_dir   = mime_dir / "packages"
    icons_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "mimetypes"

    if UNDO:
        xml_file = app_dir / "application-x-hydra-recipe.xml"
        if xml_file.exists():
            xml_file.unlink()
            subprocess.run(["update-mime-database", str(mime_dir)], check=False)
            print("✅ Association .hdr supprimée (Linux).")
        return

    # Créer les dossiers
    app_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Copier l'icône PNG
    import shutil
    if PNG_PATH.exists():
        shutil.copy(PNG_PATH, icons_dir / "application-x-hydra-recipe.png")
        print(f"  Icône copiée: {icons_dir}/application-x-hydra-recipe.png")
    else:
        print(f"  WARNING: PNG introuvable: {PNG_PATH}")

    # Écrire le fichier MIME XML
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-hydra-recipe">
    <comment>Hydra Data Recipe</comment>
    <glob pattern="*.hdr"/>
    <icon name="application-x-hydra-recipe"/>
  </mime-type>
</mime-info>
"""
    xml_file = app_dir / "application-x-hydra-recipe.xml"
    xml_file.write_text(xml_content, encoding="utf-8")
    print(f"  MIME XML: {xml_file}")

    # Mettre à jour la base MIME
    result = subprocess.run(["update-mime-database", str(mime_dir)], capture_output=True, text=True)
    if result.returncode == 0:
        print("  update-mime-database OK")
    else:
        print(f"  WARNING update-mime-database: {result.stderr}")

    print("\n✅ Type MIME application/x-hydra-recipe enregistré pour .hdr (Linux).")
    print("   Redémarrez votre gestionnaire de fichiers pour voir l'icône.")


# ── Dispatch ──────────────────────────────────────────────────────────────────

def main() -> None:
    action = "Suppression" if UNDO else "Enregistrement"
    print(f"\nHydra — {action} de l'association .hdr")
    print(f"Plateforme : {platform.system()}")
    print(f"Icône ICO  : {ICO_PATH}")
    print(f"Icône PNG  : {PNG_PATH}")
    print()

    system = platform.system()
    if system == "Windows":
        register_windows()
    elif system == "Darwin":
        register_macos()
    elif system == "Linux":
        register_linux()
    else:
        print(f"Plateforme non supportée : {system}")
        sys.exit(1)


if __name__ == "__main__":
    main()
