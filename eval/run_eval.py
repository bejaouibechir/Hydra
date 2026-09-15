#!/usr/bin/env python3
"""
run_eval.py — Harnais d'évaluation de la génération de manifestes Hydra.

Rejoue les cas de `eval/generation/cases.json` contre un modèle Ollama, écrit
le job produit dans un dossier temporaire, le soumet à l'oracle
(`hdrctl validate`), et produit trois scores : validité, exactitude, sobriété.

Modes (cumulatifs, cf. feuille de route IA) :
  baseline     prompt simple, aucune contrainte               (étape A)
  constrained  sortie JSON imposée + schémas dans le contexte (étape B)
  repair       + boucle générer -> valider -> réparer         (étape C)

Usage :
  python eval/run_eval.py --model qwen3:1.7b
  python eval/run_eval.py --model qwen3:4b --mode constrained
  python eval/run_eval.py --model qwen3:1.7b --limit 5 --verbose

Aucune dépendance hors PyYAML : urllib suffit pour parler à Ollama.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
import guards  # noqa: E402

SCHEMAS = ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"
CASES = ROOT / "eval" / "generation" / "cases.json"
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"

JOB_FILES = ["sources.yaml", "transformations.yaml", "destinations.yaml", "pipeline.yaml"]
FORBIDDEN_KEYS = {"container", "containers", "errorscope", "retryscope"}


# ===========================================================================
# Spécification chargée depuis les schémas générés
# ===========================================================================

class Spec:
    def __init__(self) -> None:
        index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
        self.operations: Dict[str, List[str]] = {}
        self.op_schemas: Dict[str, Dict[str, Any]] = {}
        for e in index["schemas"]:
            if e["kind"] != "transformation":
                continue
            sch = json.loads((SCHEMAS / e["path"]).read_text(encoding="utf-8"))
            self.operations[e["dslName"]] = sch.get("required", [])
            for junk in ("$schema", "$id", "x-hydra"):
                sch.pop(junk, None)
            self.op_schemas[e["dslName"]] = sch
        self.connectors: List[str] = json.loads(
            (SCHEMAS / "connectors.schema.json").read_text(encoding="utf-8"))["enum"]
        self.actions: List[str] = json.loads(
            (SCHEMAS / "actions.schema.json").read_text(encoding="utf-8"))["enum"]


# ===========================================================================
# Prompt
# ===========================================================================

RESPONSE_CONTRACT = """Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"refuse": false, "reason": "", "files": {"sources.yaml": "<yaml>", "destinations.yaml": "<yaml>", "pipeline.yaml": "<yaml>"}}
Ajoute "transformations.yaml" dans "files" dès que la demande implique une
opération sur les données. Sélectionner des colonnes, filtrer, renommer,
convertir un type, calculer, nettoyer, dédoublonner, trier, agréger, joindre :
ce sont toutes des transformations. Ne l'omets que pour une copie pure, d'une
source vers une destination, sans aucune modification.

N'utilise "refuse": true QUE si la demande exige quelque chose qui n'existe pas
dans les listes ci-dessus (connecteur, opération, action) ou une exécution
distribuée. Toute demande réalisable avec les éléments listés DOIT produire des
fichiers :
{"refuse": true, "reason": "<pourquoi, en une phrase>", "files": {}}"""


def build_response_schema(spec: Spec) -> Dict[str, Any]:
    """
    Schéma de la réponse en mode contraint.

    Le modèle ne produit **plus de YAML** : il produit un objet JSON, et c'est
    nous qui sérialisons. Deux classes d'erreurs disparaissent — la syntaxe
    YAML inventée et les étapes glissées dans le mauvais fichier.

    Trois branches exclusives, et l'ordre compte : le décodage contraint suit
    l'ordre des propriétés déclarées. Une première version plaçait `refuse` en
    tête, seul champ obligatoire : le modèle décidait donc de refuser AVANT
    d'avoir rien produit, et `{"refuse": true}` suffisait à satisfaire le
    schéma. Il a refusé les 29 cas réalisables. Ici, la branche de refus est
    la dernière, porte une clé distincte, et les branches productives exigent
    leurs manifestes — le chemin le moins coûteux est désormais de produire.
    """
    connector = {"type": "string", "enum": spec.connectors}
    load_mode = {"type": "string", "enum": ["append", "replace", "upsert"]}

    source_def = {
        "type": "object",
        "properties": {
            "type": connector,
            "connection": {"type": "object"},
            "extract": {
                "type": "object",
                "properties": {"table": {"type": "string"},
                               "batch_size": {"type": "integer"}},
                "required": ["table"],
            },
        },
        "required": ["type", "extract"],
    }
    dest_def = {
        "type": "object",
        "properties": {
            "type": connector,
            "connection": {"type": "object"},
            "load": {
                "type": "object",
                "properties": {"table": {"type": "string"}, "mode": load_mode},
                "required": ["table", "mode"],
            },
        },
        "required": ["type", "load"],
    }

    op_variants = []
    for name, sch in sorted(spec.op_schemas.items()):
        op_variants.append({
            "type": "object", "title": name,
            "properties": {name: sch},
            "required": [name], "additionalProperties": False,
        })

    job_branch = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["job"]},
            "sources": {"type": "object", "additionalProperties": source_def,
                        "minProperties": 1},
            "transformations": {"type": "array", "items": {"anyOf": op_variants}},
            "destinations": {"type": "object", "additionalProperties": dest_def,
                             "minProperties": 1},
            "pipeline": {
                "type": "object",
                "properties": {"name": {"type": "string"},
                               "from": {"type": "string"},
                               "to": {"type": "string"}},
                "required": ["from", "to"],
            },
        },
        "required": ["kind", "sources", "destinations", "pipeline"],
        "additionalProperties": False,
    }

    workflow_branch = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["workflow"]},
            "workflow": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trigger": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string",
                                     "enum": ["manual", "schedule", "webhook"]},
                            "cron": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                    "steps": {
                        "type": "array", "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["job", "action"]},
                                "job": {"type": "string"},
                                "action": {"type": "string", "enum": spec.actions},
                                "params": {"type": "object"},
                                "depends_on": {"type": "array",
                                               "items": {"type": "string"}},
                                "on_failure": {"type": "string",
                                               "enum": ["fail", "skip", "continue"]},
                                "retry": {
                                    "type": "object",
                                    "properties": {
                                        "max": {"type": "integer"},
                                        "delay": {"type": "number"},
                                        "backoff": {"type": "string",
                                                    "enum": ["fixed", "exponential"]},
                                    },
                                },
                            },
                            "required": ["name", "type"],
                        },
                    },
                },
                "required": ["name", "steps"],
            },
        },
        "required": ["kind", "workflow"],
        "additionalProperties": False,
    }

    refusal_branch = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["impossible"]},
            "reason": {"type": "string"},
        },
        "required": ["kind", "reason"],
        "additionalProperties": False,
    }

    return {"anyOf": [job_branch, workflow_branch, refusal_branch]}


def build_portable_schema(spec: Spec) -> Dict[str, Any]:
    """
    Variante **portable** du schéma de réponse.

    La version stricte (anyOf de 3 branches, anyOf de 18 opérations, clés
    dynamiques pour les sources) passe avec la grammaire d'Ollama, qui compile
    un JSON Schema complet. Les fournisseurs compatibles OpenAI — Gemini, Groq,
    NVIDIA — implémentent un sous-ensemble : `anyOf` imbriqué et
    `additionalProperties` typé y sont fragiles.

    On aplatit donc : plus d'alternatives, plus de clés dynamiques. Les sources
    et destinations deviennent des tableaux d'objets portant leur `id`, et une
    étape devient {op, params} au lieu de {nom: params}. La validation fine des
    paramètres est perdue au niveau du schéma — elle est reprise ensuite par
    `hdrctl validate` et par les garde-fous, qui sont de toute façon plus sûrs.
    """
    connector = {"type": "string", "enum": spec.connectors}
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["job", "workflow", "impossible"]},
            "reason": {"type": "string",
                       "description": "Rempli uniquement si kind vaut 'impossible'."},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": connector,
                        "table": {"type": "string"},
                        "batch_size": {"type": "integer"},
                    },
                    "required": ["id", "type", "table"],
                },
            },
            "transformations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": sorted(spec.operations)},
                        "params": {"type": "object"},
                    },
                    "required": ["op", "params"],
                },
            },
            "destinations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": connector,
                        "table": {"type": "string"},
                        "mode": {"type": "string",
                                 "enum": ["append", "replace", "upsert"]},
                    },
                    "required": ["id", "type", "table", "mode"],
                },
            },
            "pipeline": {
                "type": "object",
                "properties": {"name": {"type": "string"},
                               "from": {"type": "string"},
                               "to": {"type": "string"}},
                "required": ["from", "to"],
            },
            "workflow": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trigger_type": {"type": "string",
                                     "enum": ["manual", "schedule", "webhook"]},
                    "cron": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["job", "action"]},
                                "job": {"type": "string"},
                                "action": {"type": "string", "enum": spec.actions},
                                "params": {"type": "object"},
                                "depends_on": {"type": "array",
                                               "items": {"type": "string"}},
                                "on_failure": {"type": "string",
                                               "enum": ["fail", "skip", "continue"]},
                                "retry_max": {"type": "integer"},
                                "retry_delay": {"type": "number"},
                            },
                            "required": ["name", "type"],
                        },
                    },
                },
                "required": ["name", "steps"],
            },
        },
        "required": ["kind"],
    }


def _normalize_structured(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Ramène la forme portable (tableaux, op/params) à la forme stricte."""
    out = dict(obj)

    for key in ("sources", "destinations"):
        val = obj.get(key)
        if isinstance(val, list):
            mapped: Dict[str, Any] = {}
            for i, item in enumerate(val):
                if not isinstance(item, dict):
                    continue
                ident = item.get("id") or f"{key[:-1]}_{i + 1}"
                entry: Dict[str, Any] = {"type": item.get("type"), "connection": {}}
                if key == "sources":
                    extract = {"table": item.get("table")}
                    if item.get("batch_size"):
                        extract["batch_size"] = item["batch_size"]
                    entry["extract"] = extract
                else:
                    entry["load"] = {"table": item.get("table"),
                                     "mode": item.get("mode", "replace")}
                mapped[ident] = entry
            out[key] = mapped

    steps = obj.get("transformations")
    if isinstance(steps, list) and any(isinstance(s, dict) and "op" in s for s in steps):
        out["transformations"] = [
            {s["op"]: s.get("params") or {}}
            for s in steps if isinstance(s, dict) and s.get("op")
        ]

    wf = obj.get("workflow")
    if isinstance(wf, dict) and ("trigger_type" in wf or "cron" in wf):
        new_wf = {k: v for k, v in wf.items()
                  if k not in ("trigger_type", "cron")}
        trigger = {"type": wf.get("trigger_type", "manual")}
        if wf.get("cron"):
            trigger["cron"] = wf["cron"]
        new_wf["trigger"] = trigger
        for st in new_wf.get("steps") or []:
            if isinstance(st, dict) and (st.get("retry_max") or st.get("retry_delay")):
                st["retry"] = {"max": st.pop("retry_max", 0),
                               "delay": st.pop("retry_delay", 0)}
            if isinstance(st, dict):
                st.pop("retry_max", None)
                st.pop("retry_delay", None)
        out["workflow"] = new_wf

    return out


def files_from_structured(obj: Dict[str, Any]) -> Dict[str, str]:
    """Sérialise la réponse structurée en manifestes YAML. Le modèle n'écrit
    jamais de YAML : c'est nous qui le faisons, donc il est toujours valide."""
    obj = _normalize_structured(obj)

    def dump(payload: Dict[str, Any]) -> str:
        return "version: \"1.0\"\n" + yaml.safe_dump(
            payload, sort_keys=False, allow_unicode=True, default_flow_style=False)

    files: Dict[str, str] = {}
    if obj.get("sources"):
        files["sources.yaml"] = dump({"sources": obj["sources"]})
    if obj.get("destinations"):
        files["destinations.yaml"] = dump({"destinations": obj["destinations"]})
    if obj.get("transformations"):
        files["transformations.yaml"] = dump({"steps": obj["transformations"]})
    if obj.get("pipeline"):
        files["pipeline.yaml"] = dump({"pipeline": obj["pipeline"]})
    if obj.get("workflow"):
        files["workflow.yaml"] = dump({"workflow": obj["workflow"]})
    return files


STRUCTURED_CONTRACT = """Tu ne produis PAS de YAML. Tu produis un objet JSON que
le système convertit lui-même en manifestes.

Commence TOUJOURS par le champ "kind", qui vaut :
  "job"        un pipeline source -> destination        <- le cas courant
  "workflow"   un enchaînement de plusieurs jobs, uniquement si la demande
               parle d'ordonnancement, de dépendances ou de plusieurs jobs
  "impossible" en dernier recours seulement

Pour un JOB ("kind": "job"), produis :
  {"kind": "job", "sources": {...}, "transformations": [...], "destinations": {...},
   "pipeline": {"from": "<id de source>", "to": "<id de destination>"}}
  - `sources` et `destinations` : identifiant -> définition
  - `transformations` : tableau d'étapes, chacune un objet à UNE clé
  - `pipeline` ne contient JAMAIS d'étapes

Pour un WORKFLOW, produis :
  {"kind": "workflow", "workflow": {"name": "...", "trigger": {...}, "steps": [...]}}

Presque toute demande se traite ainsi. En dernier recours seulement, si elle
exige un connecteur, une opération ou une action absents des listes ci-dessus,
ou une exécution distribuée, produis :
  {"kind": "impossible", "reason": "<en une phrase>"}"""


PORTABLE_CONTRACT = """Tu ne produis PAS de YAML. Tu produis un objet JSON que
le système convertit lui-même en manifestes.

Commence TOUJOURS par "kind" :
  "job"        un pipeline source -> destination        <- le cas courant
  "workflow"   un enchaînement de plusieurs jobs, uniquement si la demande
               parle d'ordonnancement, de dépendances ou de plusieurs jobs
  "impossible" en dernier recours seulement

Pour un JOB :
  {"kind": "job",
   "sources": [{"id": "src_x", "type": "csv", "table": "entree.csv"}],
   "transformations": [{"op": "cast", "params": {"mapping": {"montant": "float"}}},
                       {"op": "filter", "params": {"expr": "montant > 100"}}],
   "destinations": [{"id": "dst_y", "type": "csv", "table": "sortie.csv",
                     "mode": "replace"}],
   "pipeline": {"from": "src_x", "to": "dst_y"}}

  - `pipeline.from` reprend un `id` de `sources`, `pipeline.to` un `id` de
    `destinations`. Les étapes ne vont JAMAIS dans `pipeline`.
  - `params` contient les paramètres de l'opération, tels que décrits plus haut.

Pour un WORKFLOW :
  {"kind": "workflow",
   "workflow": {"name": "...", "trigger_type": "schedule", "cron": "0 8 * * *",
                "steps": [{"name": "extraire", "type": "job", "job": "./jobs/e",
                           "depends_on": []}]}}

En dernier recours, si la demande exige un connecteur, une opération ou une
action absents des listes ci-dessus, ou une exécution distribuée :
  {"kind": "impossible", "reason": "<en une phrase>"}"""


def build_system_prompt(spec: Spec, examples: List[Dict[str, Any]],
                        structured: bool = False, portable: bool = False) -> str:
    ops = "\n".join(
        f"  {name}" + (f" (requis: {', '.join(req)})" if req else "")
        for name, req in sorted(spec.operations.items())
    )
    ex_txt = ""
    if structured or portable:
        examples = []          # en mode structure, les exemples YAML nuisent
    for ex in examples:
        ex_txt += "\n--- exemple ---\n"
        for fname, content in ex["manifests"].items():
            ex_txt += f"# {fname}\n{content}\n"

    return f"""Tu génères des manifestes Hydra ETL. Hydra est un moteur ETL déclaratif : un job est un dossier de fichiers YAML.

STRUCTURE D'UN JOB — 4 fichiers
  sources.yaml         les entrées      (racine: sources)
  transformations.yaml les étapes       (racine: steps)          — facultatif
  destinations.yaml    les sorties      (racine: destinations)
  pipeline.yaml        le câblage       (racine: pipeline, clés: from, to)
`pipeline.from` doit être un identifiant déclaré dans sources.yaml,
`pipeline.to` un identifiant déclaré dans destinations.yaml.
`pipeline.yaml` ne contient JAMAIS d'étapes : les étapes vont dans
transformations.yaml, et nulle part ailleurs.

FORME D'UNE ÉTAPE — un objet à UNE seule clé :
  steps:
    - filter:
        expr: "amount > 0"

CONNECTEURS AUTORISÉS (clé `type`) — aucun autre n'existe :
  {', '.join(spec.connectors)}

OPÉRATIONS AUTORISÉES — aucune autre n'existe :
{ops}

ACTIONS DE WORKFLOW AUTORISÉES — aucune autre n'existe :
  {', '.join(spec.actions)}

MODES DE CHARGEMENT : append, replace, upsert

RÈGLES
1. Un CSV ne porte aucun type : place `cast` AVANT toute comparaison numérique.
2. Les conteneurs (Sequence, Error Scope, Retry Scope) appartiennent à
   l'éditeur visuel Hydra Studio. Ils N'EXISTENT PAS dans le YAML.
3. N'invente jamais un connecteur, une opération ou une action. Si la demande
   en exige un qui n'est pas listé, refuse et explique. Mais ne refuse JAMAIS
   une demande réalisable : copier un fichier, filtrer, agréger, charger dans
   une base — tout cela se fait avec les éléments listés.
4. Hydra s'exécute sur une seule machine. Pas d'exécution distribuée.
5. Aucun secret en clair : utilise {{{{ env:NOM }}}}.
{ex_txt}\n{PORTABLE_CONTRACT if portable else (STRUCTURED_CONTRACT if structured else RESPONSE_CONTRACT)}"""


def load_examples(n: int) -> List[Dict[str, Any]]:
    """Exemples few-shot : les plus petits jobs valides, choix déterministe."""
    if not CORPUS.exists() or n <= 0:
        return []
    entries = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["kind"] == "job" and e["valid"] and not e.get("expectedInvalid") and e.get("wiringOk"):
            size = sum(len(v) for v in e["manifests"].values())
            entries.append((size, e["id"], e))
    entries.sort(key=lambda t: (t[0], t[1]))
    return [e for _, _, e in entries[:n]]


# ===========================================================================
# Ollama
# ===========================================================================

def ollama_chat(url: str, model: str, system: str, user: str,
                force_json: Any, timeout: int, think: bool,
                num_predict: int = 1200, api_key: str = "") -> Tuple[str, float]:
    """
    Appelle Ollama. Le raisonnement est coupé de DEUX façons, parce qu'aucune
    n'est portable seule : le champ natif `think: false` (Ollama récent) et le
    marqueur `/nothink` dans le message (convention Qwen3). Un serveur qui ne
    connaît pas `think` renvoie 400 : on réessaie alors sans lui.
    """
    def build(with_think_field: bool) -> Dict[str, Any]:
        p: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user if think else user + " /nothink"},
            ],
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,   # borne la generation : evite les reponses qui n'en finissent pas
                "num_ctx": 8192,
            },
        }
        if force_json:
            # Ollama accepte "json" ou un schema JSON complet : le schema
            # contraint le decodage token par token, le modele ne PEUT pas
            # produire une structure invalide.
            p["format"] = force_json
        if with_think_field and not think:
            p["think"] = False
        return p

    def call(payload: Dict[str, Any]) -> str:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            url.rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body.get("message", {}).get("content", "")

    t0 = time.monotonic()
    try:
        content = call(build(True))
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        content = call(build(False))
    return content, time.monotonic() - t0


def openai_chat(url: str, model: str, system: str, user: str,
                schema: Any, timeout: int, api_key: str,
                num_predict: int = 4096) -> Tuple[str, float]:
    """
    Client pour tout point d'entrée **compatible OpenAI** : Gemini via son
    adaptateur, Groq, NVIDIA, OpenRouter, Mistral. Un seul code pour cinq
    fournisseurs, et le même schéma contraint que localement.
    """
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": num_predict,
    }
    if schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "hydra_job", "schema": schema, "strict": False},
        }

    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {exc.code} — {detail}") from None
    choices = body.get("choices") or [{}]
    content = (choices[0].get("message") or {}).get("content") or ""
    return content, time.monotonic() - t0


# ===========================================================================
# Extraction de la réponse
# ===========================================================================

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_FENCE_RE = re.compile(r"```(?:yaml|yml)?\s*(?:#\s*(?P<name>[\w.]+\.yaml)\s*)?\n(?P<body>.*?)```", re.S)


def extract(raw: str) -> Dict[str, Any]:
    """Retourne {'refuse': bool, 'reason': str, 'files': {nom: texte}}."""
    text = _THINK_RE.sub("", raw).strip()

    # 1. JSON, éventuellement entouré de texte
    for candidate in _json_candidates(text):
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict) and ("files" in obj or "refuse" in obj):
            files = obj.get("files") or {}
            if isinstance(files, dict):
                return {
                    "refuse": bool(obj.get("refuse")),
                    "reason": str(obj.get("reason") or ""),
                    "files": {k: v for k, v in files.items() if isinstance(v, str)},
                }

    # 2. Repli : blocs YAML balisés
    files: Dict[str, str] = {}
    for m in _FENCE_RE.finditer(text):
        body = m.group("body")
        name = m.group("name") or _guess_name(body)
        if name:
            files[name] = body
    refuse = not files and bool(re.search(
        r"\b(impossible|n'existe pas|non support|pas de connecteur|ne permet pas|refus)\b",
        text, re.I))
    return {"refuse": refuse, "reason": text[:300] if refuse else "", "files": files}


def _json_candidates(text: str) -> List[str]:
    out = [text]
    start, depth = None, 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(text[start:i + 1])
    return out


def _guess_name(body: str) -> Optional[str]:
    try:
        doc = yaml.safe_load(body)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    for key, name in (("sources", "sources.yaml"), ("destinations", "destinations.yaml"),
                      ("pipeline", "pipeline.yaml"), ("workflow", "workflow.yaml"),
                      ("steps", "transformations.yaml"), ("transformations", "transformations.yaml")):
        if key in doc:
            return name
    return None


# ===========================================================================
# Oracle : hdrctl validate
# ===========================================================================

def _oracle_env() -> Dict[str, str]:
    """
    Sous Windows, la console d'un sous-processus est en cp1252 : `hdrctl` y
    plante avec UnicodeEncodeError dès qu'il imprime un emoji. On force donc
    l'UTF-8 dans le processus fils — sans quoi TOUTE validation échoue, quel
    que soit le YAML produit.
    """
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_oracle(files: Dict[str, str]) -> Tuple[bool, str]:
    tmp = Path(tempfile.mkdtemp(prefix="hydra_eval_"))
    try:
        for name, content in files.items():
            (tmp / name).write_text(content, encoding="utf-8")

        if "workflow.yaml" in files and "pipeline.yaml" not in files:
            cmd = [sys.executable, "-m", "hydra_etl.cli.hdrctl", "workflow", "validate",
                   str(tmp / "workflow.yaml")]
        else:
            cmd = [sys.executable, "-m", "hydra_etl.cli.hdrctl", "validate", str(tmp)]

        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env=_oracle_env(), timeout=120)
        out = (proc.stdout + proc.stderr)
        return proc.returncode == 0, out[-600:]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# Notation
# ===========================================================================

def parse_files(files: Dict[str, str]) -> Dict[str, Any]:
    docs = {}
    for name, content in files.items():
        try:
            docs[name] = yaml.safe_load(content)
        except Exception:
            docs[name] = None
    return docs


def step_names(doc: Any) -> List[str]:
    if not isinstance(doc, dict):
        return []
    steps = doc.get("steps")
    if steps is None and isinstance(doc.get("transformations"), dict):
        steps = doc["transformations"].get("steps")
    names = []
    for s in steps or []:
        if isinstance(s, dict) and len(s) == 1:
            names.append(next(iter(s)))
        elif isinstance(s, dict) and "op" in s:
            names.append(s["op"])
    return names


def score_sobriety(files: Dict[str, str], docs: Dict[str, Any], spec: Spec) -> Tuple[float, List[str]]:
    faults: List[str] = []

    # Un manifeste illisible ne doit PAS passer pour sobre : sans analyse
    # possible, on ne peut affirmer que rien n'a été inventé.
    for name, content in files.items():
        if docs.get(name) is None and content.strip():
            faults.append(f"{name} : YAML syntaxiquement invalide")

    # Les étapes glissées dans pipeline.yaml sont silencieusement ignorées
    # à l'exécution : donnée fausse, sans message. Faute grave.
    pipe = docs.get("pipeline.yaml")
    if isinstance(pipe, dict):
        t = (pipe.get("pipeline") or {}).get("transformations")
        if isinstance(t, (dict, list)):
            faults.append("étapes placées dans pipeline.yaml (ignorées à l'exécution)")

    blob = "\n".join(files.values()).lower()
    for key in FORBIDDEN_KEYS:
        if re.search(rf"^\s*{key}\s*:", blob, re.M):
            faults.append(f"conteneur '{key}' dans le YAML")

    for op in step_names(docs.get("transformations.yaml")):
        if op not in spec.operations:
            faults.append(f"opération inexistante '{op}'")

    for fname, root in (("sources.yaml", "sources"), ("destinations.yaml", "destinations")):
        doc = docs.get(fname)
        if isinstance(doc, dict):
            for defn in (doc.get(root) or {}).values():
                if isinstance(defn, dict) and defn.get("type") not in spec.connectors:
                    faults.append(f"connecteur inexistant '{defn.get('type')}'")

    wf = docs.get("workflow.yaml")
    if isinstance(wf, dict):
        for s in ((wf.get("workflow") or wf).get("steps") or []):
            if isinstance(s, dict) and s.get("action") and s["action"] not in spec.actions:
                faults.append(f"action inexistante '{s['action']}'")

    return (1.0 if not faults else 0.0), faults


def score_exactness(case: Dict[str, Any], files: Dict[str, str],
                    docs: Dict[str, Any], refused: bool) -> Tuple[float, List[str]]:
    exp = case.get("expect", {})
    misses: List[str] = []

    if exp.get("mustRefuse"):
        return (1.0, []) if refused else (0.0, ["aurait dû refuser"])
    if refused:
        return 0.0, ["refus injustifié"]

    checks = 0
    passed = 0

    for f in exp.get("files", []):
        checks += 1
        if f in files:
            passed += 1
        else:
            misses.append(f"{f} manquant")

    src = docs.get("sources.yaml")
    sources = (src.get("sources") or {}) if isinstance(src, dict) else {}
    dst = docs.get("destinations.yaml")
    dests = (dst.get("destinations") or {}) if isinstance(dst, dict) else {}

    if exp.get("sourceTypes"):
        checks += 1
        got = {v.get("type") for v in sources.values() if isinstance(v, dict)}
        if got & set(exp["sourceTypes"]):
            passed += 1
        else:
            misses.append(f"type de source attendu {exp['sourceTypes']}, obtenu {sorted(got)}")

    if exp.get("destType"):
        checks += 1
        allowed = {exp["destType"]} | set(exp.get("destTypeAlt", []))
        got = {v.get("type") for v in dests.values() if isinstance(v, dict)}
        if got & allowed:
            passed += 1
        else:
            misses.append(f"type de destination attendu {sorted(allowed)}, obtenu {sorted(got)}")

    if exp.get("destMode"):
        checks += 1
        got = {(v.get("load") or {}).get("mode") for v in dests.values()
               if isinstance(v, dict) and isinstance(v.get("load"), dict)}
        if exp["destMode"] in got:
            passed += 1
        else:
            misses.append(f"mode attendu '{exp['destMode']}', obtenu {sorted(x for x in got if x)}")

    if exp.get("sourceCount"):
        checks += 1
        if len(sources) >= exp["sourceCount"]:
            passed += 1
        else:
            misses.append(f"{exp['sourceCount']} sources attendues, {len(sources)} déclarée(s)")

    expected_ops = exp.get("ops") or []
    if expected_ops:
        got_ops = step_names(docs.get("transformations.yaml"))
        alt = set(exp.get("opsAny") or [])
        for op in expected_ops:
            checks += 1
            if op in got_ops or (alt and set(got_ops) & alt):
                passed += 1
            else:
                misses.append(f"opération '{op}' absente")
        if exp.get("opsOrdered") and all(o in got_ops for o in expected_ops):
            checks += 1
            idx = [got_ops.index(o) for o in expected_ops]
            if idx == sorted(idx):
                passed += 1
            else:
                misses.append(f"ordre des opérations incorrect : {got_ops}")

    if exp.get("wiring"):
        checks += 1
        pipe = (docs.get("pipeline.yaml") or {}).get("pipeline") or {}
        if pipe.get("from") in sources and pipe.get("to") in dests:
            passed += 1
        else:
            misses.append(f"câblage incorrect : from={pipe.get('from')} to={pipe.get('to')}")

    for token in exp.get("mustContain", []):
        checks += 1
        if any(token in c for c in files.values()):
            passed += 1
        else:
            misses.append(f"'{token}' absent")

    wf_exp = exp.get("workflow")
    if wf_exp:
        wf_doc = docs.get("workflow.yaml") or {}
        wf = wf_doc.get("workflow") if isinstance(wf_doc, dict) and "workflow" in wf_doc else wf_doc
        wf = wf if isinstance(wf, dict) else {}
        steps = wf.get("steps") or []
        for key, ok, label in (
            ("stepCount", len(steps) >= wf_exp.get("stepCount", 0), f"{wf_exp.get('stepCount')} steps attendus, {len(steps)}"),
            ("hasDependsOn", any(s.get("depends_on") for s in steps if isinstance(s, dict)), "aucun depends_on"),
            ("triggerType", (wf.get("trigger") or {}).get("type") == wf_exp.get("triggerType"), "trigger incorrect"),
            ("hasCron", bool((wf.get("trigger") or {}).get("cron")), "cron absent"),
            ("hasRetry", any(s.get("retry") for s in steps if isinstance(s, dict)), "retry absent"),
            ("hasFanIn", any(len(s.get("depends_on") or []) >= 2 for s in steps if isinstance(s, dict)), "aucun fan-in"),
        ):
            if key in wf_exp:
                checks += 1
                if ok:
                    passed += 1
                else:
                    misses.append(label)
        for a in wf_exp.get("actions", []):
            checks += 1
            if any(isinstance(s, dict) and s.get("action") == a for s in steps):
                passed += 1
            else:
                misses.append(f"action '{a}' absente")

    return (passed / checks if checks else 0.0), misses


# ===========================================================================
# Boucle principale
# ===========================================================================

def run_case(case, spec, system, args) -> Dict[str, Any]:
    user = case["prompt"]
    attempts: List[Dict[str, Any]] = []
    structured = args.mode in ("constrained", "repair", "verify")
    if not structured:
        schema = False
    elif args.provider == "openai":
        schema = build_portable_schema(spec)   # sous-ensemble supporté partout
    else:
        schema = build_response_schema(spec)   # grammaire complète d'Ollama
    force_json = schema
    max_tries = 3 if args.mode == "repair" else 1

    files: Dict[str, str] = {}
    refused = False
    reason = ""
    valid = False
    oracle_out = ""
    elapsed = 0.0

    for attempt in range(max_tries):
        try:
            if args.provider == "openai":
                raw, dt = openai_chat(args.url, args.model, system, user,
                                      schema, args.timeout, args.api_key,
                                      args.num_predict)
            else:
                raw, dt = ollama_chat(args.url, args.model, system, user,
                                      force_json, args.timeout, args.think,
                                      args.num_predict, args.api_key)
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            return {"id": case["id"], "level": case["level"],
                    "error": f"fournisseur injoignable: {exc}",
                    "validity": 0.0, "exactness": 0.0, "sobriety": 0.0, "seconds": 0.0}
        elapsed += dt
        if structured:
            try:
                obj = json.loads(raw)
            except Exception:
                obj = {}
            refused = obj.get("kind") == "impossible" or bool(obj.get("impossible"))
            files = {} if refused else files_from_structured(obj)
            reason = str(obj.get("reason") or "")
        else:
            parsed = extract(raw)
            files, refused, reason = parsed["files"], parsed["refuse"], parsed["reason"]
        attempts.append({"raw": raw[:2500], "files": sorted(files)})

        if refused or not files:
            break
        valid, oracle_out = run_oracle(files)
        if valid or attempt == max_tries - 1:
            break
        user = (f"{case['prompt']}\n\nLa tentative précédente a été rejetée par "
                f"`hdrctl validate` :\n{oracle_out[-500:]}\n"
                f"Corrige l'erreur et renvoie l'objet JSON complet.")

    docs = parse_files(files)
    must_refuse = case.get("expect", {}).get("mustRefuse", False)
    validity = 1.0 if (must_refuse and refused) else (1.0 if valid else 0.0)
    exactness, misses = score_exactness(case, files, docs, refused)
    sobriety, faults = score_sobriety(files, docs, spec)
    if must_refuse and refused:
        sobriety = 1.0

    alerts: List[str] = []
    if args.mode == "verify":
        if refused:
            alerts = ["refus explicite — visible par l'utilisateur"]
        else:
            try:
                alerts = guards.check(case["prompt"], files, docs)
            except Exception as exc:                      # un garde-fou ne doit jamais
                alerts = [f"garde-fou en erreur : {exc}"]  # faire tomber l'évaluation

    # Une erreur SILENCIEUSE est le seul défaut inacceptable : le résultat est
    # faux et rien ne l'a signalé à l'utilisateur.
    silent = (exactness < 1.0) and not alerts
    failed = not (validity and exactness == 1.0 and sobriety)
    return {
        "id": case["id"], "level": case["level"], "prompt": case["prompt"],
        "raw": attempts[-1]["raw"] if (args.keep_raw or failed) and attempts else "",
        "validity": validity, "exactness": round(exactness, 3), "sobriety": sobriety,
        "refused": refused, "reason": reason[:200],
        "filesProduced": sorted(files), "misses": misses, "faults": faults,
        "oracle": oracle_out[-300:] if not valid else "",
        "alerts": alerts, "silent": silent,
        "seconds": round(elapsed, 1), "attempts": len(attempts),
    }


def report(results: List[Dict[str, Any]], args) -> str:
    levels: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        levels.setdefault(r["level"], []).append(r)

    def avg(rows, key):
        return sum(r.get(key, 0.0) for r in rows) / len(rows) if rows else 0.0

    lines = [
        f"# Évaluation — {args.model} — mode `{args.mode}`",
        "",
        f"- Cas joués : **{len(results)}**",
        f"- Temps total : **{sum(r.get('seconds', 0) for r in results):.0f} s**",
        f"- Few-shot : {args.examples} exemple(s) · thinking : {'on' if args.think else 'off'}",
        "",
        "| Niveau | Cas | Validité | Exactitude | Sobriété | s/cas |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    if args.mode == "verify":
        silent_n = sum(1 for r in results if r.get("silent"))
        flagged = sum(1 for r in results if r.get("alerts"))
        lines.insert(4, f"- **Taux d'erreur silencieuse : "
                        f"{silent_n / len(results):.0%}** ({silent_n}/{len(results)}) "
                        f"— cas faux qu'aucun garde-fou n'a signalés")
        lines.insert(5, f"- Cas assortis d'au moins une alerte : {flagged}")
    for level in sorted(levels):
        rows = levels[level]
        lines.append(
            f"| {level} | {len(rows)} | {avg(rows,'validity'):.0%} | "
            f"{avg(rows,'exactness'):.0%} | {avg(rows,'sobriety'):.0%} | "
            f"{avg(rows,'seconds'):.1f} |")
    lines.append(
        f"| **total** | **{len(results)}** | **{avg(results,'validity'):.0%}** | "
        f"**{avg(results,'exactness'):.0%}** | **{avg(results,'sobriety'):.0%}** | "
        f"**{avg(results,'seconds'):.1f}** |")

    silents = [r for r in results if r.get("silent")]
    if args.mode == "verify":
        lines += ["", "## Erreurs silencieuses", ""]
        if silents:
            for r in silents:
                lines.append(f"- `{r['id']}` — {'; '.join(r.get('misses') or [])[:160]}")
        else:
            lines.append("Aucune. Tout écart a été signalé à l'utilisateur.")

    fails = [r for r in results if r["validity"] < 1 or r["exactness"] < 1 or r["sobriety"] < 1]
    if fails:
        lines += ["", f"## Échecs ({len(fails)})", ""]
        for r in fails:
            detail = "; ".join((r.get("misses") or []) + (r.get("faults") or [])) or r.get("error", "")
            lines.append(f"- `{r['id']}` ({r['level']}) — V{r['validity']:.0f} "
                         f"E{r['exactness']:.2f} S{r['sobriety']:.0f} — {detail[:180]}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Harnais d'évaluation de la génération Hydra.")
    ap.add_argument("--model", required=True, help="ex. qwen3:1.7b")
    ap.add_argument("--mode", choices=["baseline", "constrained", "repair", "verify"],
                    default="baseline",
                    help="verify = constrained + garde-fous déterministes")
    ap.add_argument("--provider", choices=["ollama", "openai"], default="ollama",
                    help="openai = tout point d'entrée compatible OpenAI "
                         "(Gemini, Groq, NVIDIA, OpenRouter, Mistral)")
    ap.add_argument("--url", default="",
                    help="URL du serveur. Défaut : Ollama local, ou "
                         "l'adaptateur OpenAI de Gemini si --provider openai")
    ap.add_argument("--api-key",
                    default=(os.environ.get("GEMINI_API_KEY")
                             or os.environ.get("OPENAI_API_KEY")
                             or os.environ.get("OLLAMA_API_KEY", "")),
                    help="clé du fournisseur (défaut : $GEMINI_API_KEY, "
                         "$OPENAI_API_KEY ou $OLLAMA_API_KEY)")
    ap.add_argument("--examples", type=int, default=1, help="exemples few-shot (0 = aucun)")
    ap.add_argument("--limit", type=int, default=0, help="n'exécuter que les N premiers cas")
    ap.add_argument("--level", default="", help="ne jouer qu'un niveau")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--think", action="store_true", help="laisser le mode raisonnement (défaut: /nothink)")
    ap.add_argument("--keep-raw", action="store_true",
                    help="conserver toutes les réponses brutes (les échecs le sont toujours)")
    ap.add_argument("--num-predict", type=int, default=1200,
                    help="plafond de jetons générés par réponse")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not args.url:
        args.url = ("https://generativelanguage.googleapis.com/v1beta/openai"
                    if args.provider == "openai" else "http://localhost:11434")
    if args.provider == "openai" and not args.api_key:
        print("Aucune clé API. Définissez $GEMINI_API_KEY ou passez --api-key.")
        return 2

    spec = Spec()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if args.level:
        cases = [c for c in cases if c["level"] == args.level]
    if args.limit:
        cases = cases[:args.limit]

    structured_mode = args.mode in ("constrained", "repair", "verify")
    system = build_system_prompt(spec, load_examples(args.examples),
                                 structured=structured_mode,
                                 portable=structured_mode and args.provider == "openai")

    where = "local" if "localhost" in args.url else args.url.split("//")[-1].split("/")[0]
    print(f"Modele {args.model} | mode {args.mode} | {where} | {len(cases)} cas | "
          f"{args.examples} exemple(s) few-shot")
    results = []
    for i, case in enumerate(cases, 1):
        r = run_case(case, spec, system, args)
        results.append(r)
        if r["validity"] and r["exactness"] == 1 and r["sobriety"]:
            flag = "ok "
        elif r.get("silent"):
            flag = "!! "          # faux ET silencieux : le seul cas inacceptable
        else:
            flag = "KO "
        print(f"  [{i:>2}/{len(cases)}] {flag} {r['id']:<9} "
              f"V{r['validity']:.0f} E{r['exactness']:.2f} S{r['sobriety']:.0f} "
              f"{r['seconds']:>5.1f}s")
        if args.verbose and (r.get("misses") or r.get("faults") or r.get("error")):
            for m in (r.get("misses") or []) + (r.get("faults") or []):
                print(f"          - {m}")
            if r.get("error"):
                print(f"          ! {r['error']}")
            for a in r.get("alerts", []):
                print(f"          ⚑ {a}")
            if r.get("oracle"):
                print(f"          oracle: {r['oracle'].strip()[-200:]}")
        if r.get("error", "").startswith("Ollama injoignable"):
            print("\nArrêt : Ollama ne répond pas. Vérifiez `ollama serve`.")
            break

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    host = "" if "localhost" in args.url else "_" + args.provider
    tag = f"{args.model.replace(':','-').replace('/','-')}_{args.mode}{host}"
    (RESULTS_DIR / f"{tag}.json").write_text(
        json.dumps({"model": args.model, "mode": args.mode, "examples": args.examples,
                    "think": args.think, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    md = report(results, args)
    (RESULTS_DIR / f"{tag}.md").write_text(md, encoding="utf-8")

    print()
    print(md)
    print(f"Ecrit : eval/results/{tag}.md et {tag}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
