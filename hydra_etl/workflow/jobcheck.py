"""
Contrôle de pipeline.yaml d'un job et de ses renvois, sans lire de données.

Même lecture que l'exécuteur (`JobExecutor._resolve_pipeline_ids`) :
`pipeline:` à la racine, ou l'ancien format imbriqué `job: pipeline:`.
Utilisé par `hdrctl validate`, `hdrctl run <job> --dry-run` et la préparation
d'un projet (`hdrctl run <projet>`), pour qu'un `pipeline.from` cassé soit
signalé avant tout lancement.

Résultat : liste de (niveau, code, paramètres), niveau ∈ ok | err | info.
Codes : read_error, section_missing, invalid, ref_empty, ref_param,
from_missing, to_missing, resolved. Une valeur `${param}` n'est résolue qu'au
lancement : elle est signalée (info) sans être une erreur.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

Check = Tuple[str, str, Dict[str, str]]

MESSAGES_EN = {
    "read_error": "pipeline.yaml: {error}",
    "section_missing": "pipeline.yaml: 'pipeline:' section missing (expected: pipeline: from / to)",
    "invalid": "pipeline.yaml: {field} — {error}",
    "ref_empty": "{ref} is missing or empty",
    "ref_param": "{ref} resolved at run time ({value})",
    "from_missing": "pipeline.from='{id}' not found in sources.yaml",
    "to_missing": "pipeline.to='{id}' not found in destinations.yaml",
    "resolved": "{ref} resolved: {id}",
}


def read_yaml_text(path: Path) -> str:
    """Lit un YAML en gérant les encodages Windows (UTF-8, UTF-8-BOM, UTF-16)."""
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError(f"{path.name}: unreadable encoding")


def _section(path: Path, name: str) -> Optional[dict]:
    try:
        doc = yaml.safe_load(read_yaml_text(path)) or {}
    except Exception:
        return None
    sec = doc.get(name) if isinstance(doc, dict) else None
    return sec if isinstance(sec, dict) else None


def pipeline_checks(files: Dict[str, Path]) -> List[Check]:
    """files : chemins 'pipeline', 'sources', 'destinations' du job."""
    from pydantic import ValidationError
    from hydra_etl.internal.parser.pipeline import PipelineDefinition

    try:
        raw = yaml.safe_load(read_yaml_text(files["pipeline"])) or {}
    except Exception as e:
        return [("err", "read_error", {"error": str(e)})]
    pipe = raw.get("pipeline") if isinstance(raw, dict) else None
    if not isinstance(pipe, dict) and isinstance(raw, dict) and isinstance(raw.get("job"), dict):
        pipe = raw["job"].get("pipeline")
    if not isinstance(pipe, dict):
        return [("err", "section_missing", {})]

    out: List[Check] = []
    try:
        PipelineDefinition.model_validate(pipe)
    except ValidationError as e:
        for er in e.errors():
            if er.get("type") == "missing":
                continue                    # signalé ci-dessous avec le renvoi
            field = ".".join(str(x) for x in er.get("loc", ())) or "pipeline"
            out.append(("err", "invalid", {"field": field, "error": er.get("msg", "")}))

    for ref, key, missing in (("from", "sources", "from_missing"),
                              ("to", "destinations", "to_missing")):
        label = f"pipeline.{ref}"
        val = pipe.get(ref)
        if not isinstance(val, str) or not val.strip():
            out.append(("err", "ref_empty", {"ref": label}))
            continue
        val = val.strip()
        if "${" in val:
            out.append(("info", "ref_param", {"ref": label, "value": val}))
            continue
        declared = _section(files[key], key)
        if declared is None or val not in declared:
            out.append(("err", missing, {"ref": label, "id": val}))
        else:
            out.append(("ok", "resolved", {"ref": label, "id": val}))
    return out


def pipeline_errors(job_dir: Path) -> List[str]:
    """Erreurs (en anglais) de pipeline.yaml d'un dossier de job."""
    job_dir = Path(job_dir)
    files = {k: job_dir / f"{k}.yaml" for k in ("pipeline", "sources", "destinations")}
    if not files["pipeline"].exists():
        return ["pipeline.yaml not found"]
    return [MESSAGES_EN[code].format(**params)
            for level, code, params in pipeline_checks(files) if level == "err"]
