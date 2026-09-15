#!/usr/bin/env python3
"""
harvest.py — Récolte les jobs et workflows réels du dépôt pour en faire un
corpus exploitable : exemples few-shot, contexte RAG, et, le jour venu, base
d'un jeu d'entraînement.

Principe : ne retenir que ce qui **passe la validation**. Les manifestes du
dépôt sont exécutés en test, donc réputés corrects ; on le vérifie quand même,
parce qu'un corpus qui contient une erreur l'enseigne.

Séparation stricte :
  - ce corpus     -> exemples montrés au modèle (few-shot, RAG, entraînement)
  - cases.json    -> mesure. JAMAIS montré au modèle.

Sorties (eval/corpus/) :
  corpus.jsonl     un objet par job/workflow, manifestes + caractéristiques
  coverage.md      ce que le corpus couvre, et surtout ce qu'il ne couvre pas

Usage : python eval/corpus/harvest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
SCHEMAS = ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"

SEARCH_ROOTS = ["test_scenarios", "examples", "tests/fixtures"]
EXCLUDE_PARTS = {"_archive", "_backups", "_bak_safe_write", "__pycache__",
                 "backup", "node_modules", "output", "out"}
EXCLUDE_NAME_HINTS = ("- copie", "- copy")

MANIFESTS = ["sources.yaml", "transformations.yaml", "destinations.yaml", "pipeline.yaml"]

# tests/fixtures/dsl_cases/ko_* : cas INVALIDES par construction. Ils ne sont
# pas des défauts du corpus, ce sont des exemples négatifs — précieux pour
# apprendre à expliquer une erreur plutôt qu'à la produire.
def expected_invalid(job_id: str) -> bool:
    return "/ko_" in job_id.replace("\\", "/")


def excluded(p: Path) -> bool:
    parts = [x.lower() for x in p.parts]
    if any(x in EXCLUDE_PARTS for x in parts):
        return True
    return any(h in x for x in parts for h in EXCLUDE_NAME_HINTS)


def read_yaml(p: Path):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------

def job_features(docs: Dict[str, Any]) -> Dict[str, Any]:
    src = docs.get("sources.yaml") or {}
    dst = docs.get("destinations.yaml") or {}
    trs = docs.get("transformations.yaml") or {}

    sources = (src.get("sources") or {}) if isinstance(src, dict) else {}
    dests = (dst.get("destinations") or {}) if isinstance(dst, dict) else {}

    steps = []
    if isinstance(trs, dict):
        raw = trs.get("steps")
        if raw is None and isinstance(trs.get("transformations"), dict):
            raw = trs["transformations"].get("steps")
        for s in raw or []:
            if isinstance(s, dict) and s:
                steps.append(next(iter(s)))

    return {
        "sourceIds": sorted(sources),
        "sourceTypes": sorted({v.get("type") for v in sources.values()
                               if isinstance(v, dict) and v.get("type")}),
        "destIds": sorted(dests),
        "destTypes": sorted({v.get("type") for v in dests.values()
                             if isinstance(v, dict) and v.get("type")}),
        "loadModes": sorted({(v.get("load") or {}).get("mode") for v in dests.values()
                             if isinstance(v, dict) and isinstance(v.get("load"), dict)
                             and (v.get("load") or {}).get("mode")}),
        "ops": steps,
        "opCount": len(steps),
    }


def validate_job(docs: Dict[str, Any]) -> List[str]:
    """Valide avec les vrais modèles du moteur. Retourne la liste des erreurs."""
    from hydra_etl.internal.parser.source import SourceParser
    from hydra_etl.internal.parser.destination import DestinationParser
    from hydra_etl.internal.parser.transform import TransformParser
    from hydra_etl.internal.parser.pipeline import PipelineConfig

    # On passe par les PARSEURS, pas par les modèles : la forme écrite dans le
    # fichier (`- filter: {...}`) n'est pas la forme interne (`op`/`params`).
    checks = [
        ("sources.yaml", lambda d: SourceParser().parse(d)),
        ("destinations.yaml", lambda d: DestinationParser().parse(d)),
        ("transformations.yaml", lambda d: TransformParser().parse(d)),
        ("pipeline.yaml", lambda d: PipelineConfig.model_validate(d)),
    ]
    errors: List[str] = []
    for fname, check in checks:
        doc = docs.get(fname)
        if doc is None:
            continue
        try:
            check(doc)
        except Exception as exc:
            msg = str(exc).splitlines()[0][:120]
            errors.append(f"{fname}: {msg}")
    return errors


def wiring_ok(docs: Dict[str, Any], feats: Dict[str, Any]) -> bool:
    pipe = (docs.get("pipeline.yaml") or {}).get("pipeline") or {}
    return pipe.get("from") in feats["sourceIds"] and pipe.get("to") in feats["destIds"]


def harvest_jobs() -> List[Dict[str, Any]]:
    out = []
    for root in SEARCH_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for pipe in base.rglob("pipeline.yaml"):
            d = pipe.parent
            if excluded(d):
                continue
            docs = {}
            for m in MANIFESTS:
                f = d / m
                if f.exists():
                    doc = read_yaml(f)
                    if doc is not None:
                        docs[m] = doc
            if "pipeline.yaml" not in docs or "sources.yaml" not in docs:
                continue
            feats = job_features(docs)
            errors = validate_job(docs)
            out.append({
                "kind": "job",
                "id": str(d.relative_to(ROOT)).replace("\\", "/"),
                "manifests": {k: yaml.safe_dump(v, sort_keys=False, allow_unicode=True)
                              for k, v in docs.items()},
                "features": feats,
                "wiringOk": wiring_ok(docs, feats),
                "valid": not errors,
                "errors": errors,
                "expectedInvalid": expected_invalid(str(d.relative_to(ROOT))),
            })
    return out


def harvest_workflows() -> List[Dict[str, Any]]:
    from hydra_etl.workflow.models import WorkflowDef
    out = []
    for root in SEARCH_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for f in base.rglob("*.yaml"):
            if excluded(f) or f.name in MANIFESTS:
                continue
            doc = read_yaml(f)
            if not isinstance(doc, dict) or "workflow" not in doc:
                continue
            wf = doc["workflow"]
            errors = []
            try:
                WorkflowDef.model_validate(wf)
            except Exception as exc:
                errors.append(f"workflow: {type(exc).__name__}")
            steps = wf.get("steps") or []
            out.append({
                "kind": "workflow",
                "id": str(f.relative_to(ROOT)).replace("\\", "/"),
                "manifests": {"workflow.yaml": yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)},
                "features": {
                    "stepCount": len(steps),
                    "stepTypes": sorted({s.get("type") for s in steps if isinstance(s, dict)}),
                    "actions": sorted({s.get("action") for s in steps
                                       if isinstance(s, dict) and s.get("action")}),
                    "triggerType": (wf.get("trigger") or {}).get("type", "manual"),
                    "hasRetry": any(isinstance(s, dict) and s.get("retry") for s in steps),
                    "onFailure": sorted({s.get("on_failure") for s in steps
                                         if isinstance(s, dict) and s.get("on_failure")}),
                },
                "valid": not errors,
                "errors": errors,
            })
    return out


def coverage(entries: List[Dict[str, Any]]) -> str:
    known_ops = sorted({e["dslName"] for e in json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))["schemas"]
                        if e["kind"] == "transformation"})
    known_conn = json.loads((SCHEMAS / "connectors.schema.json").read_text(encoding="utf-8"))["enum"]
    known_act = json.loads((SCHEMAS / "actions.schema.json").read_text(encoding="utf-8"))["enum"]

    jobs = [e for e in entries if e["kind"] == "job"]
    wfs = [e for e in entries if e["kind"] == "workflow"]

    op_count: Dict[str, int] = {o: 0 for o in known_ops}
    conn_count: Dict[str, int] = {c: 0 for c in known_conn}
    act_count: Dict[str, int] = {a: 0 for a in known_act}
    modes: Dict[str, int] = {}

    for j in jobs:
        for o in j["features"]["ops"]:
            op_count[o] = op_count.get(o, 0) + 1
        for t in j["features"]["sourceTypes"] + j["features"]["destTypes"]:
            conn_count[t] = conn_count.get(t, 0) + 1
        for m in j["features"]["loadModes"]:
            modes[m] = modes.get(m, 0) + 1
    for w in wfs:
        for a in w["features"]["actions"]:
            act_count[a] = act_count.get(a, 0) + 1

    def table(title, counts):
        lines = [f"### {title}", "", "| Élément | Occurrences |", "|---|---:|"]
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| `{k}` | {v if v else '**0 — non couvert**'} |")
        lines.append("")
        return lines

    negatives = [e for e in entries if e.get("expectedInvalid")]
    invalid = [e for e in entries if not e["valid"] and not e.get("expectedInvalid")]
    caught = [e for e in negatives if not e["valid"]]
    unwired = [e for e in jobs if not e.get("wiringOk")]

    lines = [
        "# Couverture du corpus",
        "",
        "> Fichier généré par `eval/corpus/harvest.py`.",
        "",
        f"- Jobs récoltés : **{len(jobs)}**",
        f"- Workflows récoltés : **{len(wfs)}**",
        f"- Exemples négatifs (`ko_*`, invalides par construction) : **{len(negatives)}**, "
        f"dont **{len(caught)}** effectivement rejetés par les parseurs",
        f"- Entrées invalides non voulues : **{len(invalid)}**",
        f"- Jobs au câblage from/to incohérent : **{len(unwired)}**",
        "",
        "Un `0` signale un élément du DSL qu'**aucun exemple n'illustre** : c'est",
        "exactement là qu'un modèle se trompera, et là qu'il faut écrire un exemple.",
        "",
    ]
    lines += table(f"Opérations ({len(known_ops)})", op_count)
    lines += table(f"Connecteurs ({len(known_conn)})", conn_count)
    lines += table(f"Actions de workflow ({len(known_act)})", act_count)
    lines += table("Modes de chargement", modes)

    if invalid:
        lines += ["### Entrées invalides non voulues", "",
                  "Stubs vides ou incomplets du dépôt. À exclure du few-shot.", ""]
        for e in invalid:
            lines.append(f"- `{e['id']}` — {', '.join(e['errors'])}")
        lines.append("")
    if unwired:
        lines += ["### Câblage incohérent (pipeline.from / pipeline.to)", ""]
        for e in unwired:
            lines.append(f"- `{e['id']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    entries = harvest_jobs() + harvest_workflows()
    entries.sort(key=lambda e: (e["kind"], e["id"]))

    (OUT_DIR / "corpus.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
        encoding="utf-8")
    (OUT_DIR / "coverage.md").write_text(coverage(entries), encoding="utf-8")

    jobs = sum(1 for e in entries if e["kind"] == "job")
    wfs = len(entries) - jobs
    neg = sum(1 for e in entries if e.get("expectedInvalid"))
    bad = sum(1 for e in entries if not e["valid"] and not e.get("expectedInvalid"))
    good = sum(1 for e in entries if e["valid"] and not e.get("expectedInvalid"))
    print(f"corpus.jsonl : {jobs} jobs, {wfs} workflows")
    print(f"  exploitables (valides)  : {good}")
    print(f"  exemples negatifs ko_*  : {neg}")
    print(f"  invalides non voulus    : {bad}")
    print(f"coverage.md  : {OUT_DIR / 'coverage.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
