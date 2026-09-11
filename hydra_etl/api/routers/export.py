"""
api/routers/export.py — Sauvegarde native via boîte de dialogue Windows (tkinter).

POST /api/export/save   -> ouvre SaveAs dialog, écrit le fichier, retourne le chemin
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Literal, Optional

from hydra_etl.internal.fs_atomic import atomic_write_text

router = APIRouter()


class ExportRequest(BaseModel):
    content: str
    suggested_name: str = "output.csv"
    fmt: Literal["csv", "txt"] = "csv"


class ExportResponse(BaseModel):
    saved: bool
    path: Optional[str] = None
    cancelled: bool = False


@router.post("/save", response_model=ExportResponse)
def export_save(body: ExportRequest) -> ExportResponse:
    """Ouvre une boîte de dialogue Windows 'Enregistrer sous' et écrit le fichier."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()          # cacher la fenêtre principale Tk
    root.attributes("-topmost", True)   # dialog au premier plan

    if body.fmt == "csv":
        filetypes = [("CSV files", "*.csv"), ("All files", "*.*")]
        default_ext = ".csv"
    else:
        filetypes = [("Text files", "*.txt"), ("TSV files", "*.tsv"), ("All files", "*.*")]
        default_ext = ".txt"

    path = filedialog.asksaveasfilename(
        parent=root,
        title="Enregistrer les données",
        initialfile=body.suggested_name,
        defaultextension=default_ext,
        filetypes=filetypes,
    )
    root.destroy()

    if not path:
        return ExportResponse(saved=False, cancelled=True)

    atomic_write_text(path, body.content)

    return ExportResponse(saved=True, path=path)
