"""
api/routers/transform.py — Preview & validation de la transformation 'script'.

Endpoint autonome : exécute UNIQUEMENT l'op 'script' sur un petit échantillon
fourni par le client (mini-table du Studio). Sert aussi au bouton 'Parse'
(validation AST sans données).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ScriptPreviewRequest(BaseModel):
    inputs: List[str] = []
    outputs: Dict[str, str] = {}
    code: str = ""
    mode: str = "vectorized"
    rows: List[Dict[str, Any]] = []


class ScriptPreviewResponse(BaseModel):
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    error: Optional[str] = None


def _clean(v: Any) -> Any:
    """Rend une valeur pandas/numpy sérialisable en JSON."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


@router.post("/script/preview", response_model=ScriptPreviewResponse)
def script_preview(req: ScriptPreviewRequest) -> ScriptPreviewResponse:
    # Import tardif : garde le router léger et évite les imports circulaires.
    from internal.engines.pandas_engine import PandasEngine, _validate_script_ast

    if not req.code.strip():
        return ScriptPreviewResponse(error="script.code est vide")

    # 1) Validation syntaxe + sandbox (sert au bouton 'Parse')
    try:
        _validate_script_ast(req.code)
        compile(req.code, "<hydra-script>", "exec")
    except Exception as e:  # noqa: BLE001 - message renvoyé tel quel au Studio
        return ScriptPreviewResponse(error=str(e))

    # Pas de données -> mode 'parse' : on confirme juste la validité + colonnes.
    if not req.rows:
        return ScriptPreviewResponse(columns=list(req.outputs.keys()), rows=[], error=None)

    # 2) Exécution du script sur l'échantillon
    try:
        df = pd.DataFrame(req.rows)
        # Coercition numérique douce des colonnes input (l'UI saisit du texte) :
        # ne convertit que si TOUTES les valeurs de la colonne sont numériques.
        for c in req.inputs:
            if c in df.columns:
                conv = pd.to_numeric(df[c], errors="coerce")
                if conv.notna().all():
                    df[c] = conv
        step = {
            "op": "script",
            "params": {
                "inputs": req.inputs,
                "outputs": req.outputs,
                "code": req.code,
                "mode": req.mode,
            },
        }
        out = PandasEngine().apply_step(df, step).output.head(10)
        rows = [{k: _clean(v) for k, v in rec.items()} for rec in out.to_dict("records")]
        return ScriptPreviewResponse(columns=[str(c) for c in out.columns], rows=rows, error=None)
    except Exception as e:  # noqa: BLE001
        return ScriptPreviewResponse(error=str(e))
