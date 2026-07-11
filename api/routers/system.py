"""
api/routers/system.py — Sélecteur de fichiers natif cross-platform.

Windows  : PowerShell + System.Windows.Forms (dialog natif, premier plan garanti)
macOS    : osascript (AppleScript)
Linux    : zenity → kdialog → tkinter subprocess
"""
from __future__ import annotations

import sys
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from fastapi import APIRouter, Query

router = APIRouter()
_ui_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hydra-ui")


# ---------------------------------------------------------------------------
# Windows : PowerShell + System.Windows.Forms
# ---------------------------------------------------------------------------

def _ps_filter(ext: str) -> str:
    m = {
        ".csv":     "CSV (*.csv)|*.csv|Tous (*.*)|*.*",
        ".json":    "JSON (*.json)|*.json|Tous (*.*)|*.*",
        ".parquet": "Parquet (*.parquet)|*.parquet|Tous (*.*)|*.*",
        ".py":      "Python (*.py)|*.py|Tous (*.*)|*.*",
        ".yaml":    "YAML (*.yaml)|*.yaml|Tous (*.*)|*.*",
        ".yml":     "YAML (*.yml)|*.yml|Tous (*.*)|*.*",
    }
    return m.get(ext, "Tous fichiers (*.*)|*.*|CSV (*.csv)|*.csv|JSON (*.json)|*.json|Parquet (*.parquet)|*.parquet")


def _powershell_dialog(dialog_type: str, ext: str) -> dict:
    """Windows : dialog natif via PowerShell + System.Windows.Forms."""
    filt = _ps_filter(ext)
    ext_clean = ext.lstrip(".")

    if dialog_type == "directory":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
            "$f.Description = 'Selectionnez un dossier';"
            "$f.ShowNewFolderButton = $true;"
            "$r = $f.ShowDialog();"
            "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"
        )
    elif dialog_type == "save_file":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            f"$f = New-Object System.Windows.Forms.SaveFileDialog;"
            "$f.Title = 'Enregistrer sous';"
            f"$f.Filter = '{filt}';"
            f"$f.DefaultExt = '{ext_clean}';"
            "$r = $f.ShowDialog();"
            "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }"
        )
    else:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$f = New-Object System.Windows.Forms.OpenFileDialog;"
            "$f.Title = 'Selectionnez un fichier';"
            f"$f.Filter = '{filt}';"
            "$f.Multiselect = $false;"
            "$r = $f.ShowDialog();"
            "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }"
        )

    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=120,
    )
    path = r.stdout.strip()
    if path:
        return {"path": path, "cancelled": False}
    return {"path": None, "cancelled": True}


# ---------------------------------------------------------------------------
# macOS : osascript
# ---------------------------------------------------------------------------

def _osascript_dialog(dialog_type: str) -> dict:
    if dialog_type == "directory":
        script = 'choose folder with prompt "Selectionnez un dossier"'
    else:
        script = 'choose file with prompt "Selectionnez un fichier"'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        raw = r.stdout.strip()
        conv = subprocess.run(["osascript", "-e", f"POSIX path of ({repr(raw)})"],
                               capture_output=True, text=True)
        path = conv.stdout.strip()
        return {"path": path, "cancelled": False} if path else {"path": None, "cancelled": True}
    return {"path": None, "cancelled": True}


# ---------------------------------------------------------------------------
# Linux : zenity puis kdialog
# ---------------------------------------------------------------------------

def _zenity_dialog(dialog_type: str) -> dict:
    args = ["zenity", "--file-selection"]
    if dialog_type == "directory":
        args.append("--directory")
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    path = r.stdout.strip()
    return {"path": path, "cancelled": False} if path else {"path": None, "cancelled": True}


def _kdialog_dialog(dialog_type: str) -> dict:
    args = (["kdialog", "--getexistingdirectory", "."] if dialog_type == "directory"
            else ["kdialog", "--getopenfilename", "."])
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    path = r.stdout.strip()
    return {"path": path, "cancelled": False} if path else {"path": None, "cancelled": True}


# ---------------------------------------------------------------------------
# Fallback : tkinter subprocess (tous OS)
# ---------------------------------------------------------------------------

_TKINTER_SCRIPT = """\
import sys, json, tkinter as tk
from tkinter import filedialog
dt  = sys.argv[1]
ext = sys.argv[2] if len(sys.argv) > 2 else ""
def ft(e):
    m = {".py":[("Python","*.py"),("Tous","*.*")],".csv":[("CSV","*.csv"),("Tous","*.*")],
         ".json":[("JSON","*.json"),("Tous","*.*")],".parquet":[("Parquet","*.parquet"),("Tous","*.*")]}
    return m.get(e,[("Tous","*.*")])
root = tk.Tk(); root.withdraw(); root.wm_attributes("-topmost",1); root.update()
if dt=="directory": p=filedialog.askdirectory(parent=root,mustexist=True)
elif dt=="save_file": p=filedialog.asksaveasfilename(parent=root,defaultextension=ext,filetypes=ft(ext))
else: p=filedialog.askopenfilename(parent=root,filetypes=ft(ext))
root.destroy(); print(json.dumps(str(p) if p else None))
"""


def _tkinter_subprocess(dialog_type: str, ext: str) -> dict:
    try:
        r = subprocess.run(
            [sys.executable, "-c", _TKINTER_SCRIPT, dialog_type, ext],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0:
            path = __import__("json").loads(r.stdout.strip())
            return {"path": path, "cancelled": False} if path else {"path": None, "cancelled": True}
    except Exception:
        pass
    return {"path": None, "cancelled": True, "error": "tkinter unavailable"}


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def _open_dialog(dialog_type: str, ext: str) -> dict:
    platform = sys.platform

    if platform == "win32":
        try:
            return _powershell_dialog(dialog_type, ext)
        except Exception:
            pass
        return _tkinter_subprocess(dialog_type, ext)

    if platform == "darwin":
        try:
            return _osascript_dialog(dialog_type)
        except Exception:
            pass
        return _tkinter_subprocess(dialog_type, ext)

    # Linux
    for fn in (_zenity_dialog, _kdialog_dialog):
        try:
            r = fn(dialog_type)
            if r.get("path"):
                return r
        except Exception:
            pass
    return _tkinter_subprocess(dialog_type, ext)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/info")
async def system_info():
    return {
        "platform":   sys.platform,
        "is_windows": sys.platform == "win32",
        "is_mac":     sys.platform == "darwin",
        "is_linux":   sys.platform.startswith("linux"),
    }


@router.get("/browse")
async def browse_path(
    type: str = Query("file", description="'file', 'directory' ou 'save_file'"),
    ext:  str = Query("",     description="Extension filtre ex: .csv"),
):
    """Ouvre le sélecteur de fichiers/dossiers natif. Retourne { path, cancelled }."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ui_executor, partial(_open_dialog, type, ext))
