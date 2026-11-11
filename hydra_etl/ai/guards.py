#!/usr/bin/env python3
"""
guards.py — Garde-fous déterministes sur un job généré.

Ils comparent la **demande en langage naturel** aux **manifestes produits** et
signalent ce que l'oracle ne peut pas voir : du YAML parfaitement valide qui
fait autre chose que ce qui était demandé.

Aucun modèle n'intervient ici : ce sont des règles, elles sont reproductibles,
et elles ne dépendent pas du jeu d'évaluation — elles lisent la demande de
l'utilisateur, donc elles fonctionnent en production telles quelles.

Vocation : migrer dans le produit (Studio + API) une fois éprouvées.

Chaque règle retourne des alertes ; une alerte n'est pas une erreur certaine,
c'est un point que l'utilisateur doit regarder avant d'exécuter.
"""
from __future__ import annotations

import re
from pathlib import Path
import unicodedata
from typing import Any, Dict, List


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# --- Ce qui, dans une demande, réclame une opération ------------------------
# Volontairement large : mieux vaut une alerte de trop qu'une erreur silencieuse.
OP_HINTS: Dict[str, List[str]] = {
    "select":      ["ne garde que", "garde seulement", "seules les colonnes", "colonnes ", "selectionne", "keep only the columns", "only the columns", "select the columns"],
    "filter":      ["filtre", "garde les", "seulement les lignes", "dont le", "superieur", "depasse", "inferieur", "= error", "uniquement les", "de 2026", "de 2025", "only the rows", "keep the rows", "where the", "greater than", "less than", "more than", "only paid", "only the paid", "excluding", "except"],
    "cast":        ["convertis", "en float", "en int", "en datetime", "type", "convert to", "as float", "as int", "as a date", "as datetime"],
    "calculate":   ["calcule", "ajoute une colonne", "egale au", "divise", "multiplie", "compute a column", "add a column", "derived column", "divided by", "multiplied by"],
    "sort":        ["trie", "classe", "du plus", "croissant", "decroissant", "ordre", "sort by", "sorted by", "sort the", "order by", "ordered by", "highest first", "descending", "ascending", "ranked by"],
    "deduplicate": ["doublon", "dedoublonne", "unique", "duplicate", "deduplicate", "distinct"],
    "fill_null":   ["valeurs manquantes", "valeur manquante", "remplace les vides", "null", "missing values", "missing value", "replace nulls", "fill the empty"],
    "clean":       ["nettoie", "minuscule", "majuscule", "espaces en trop", "clean up", "lowercase", "uppercase", "extra spaces"],
    "trim":        ["espaces en trop", "rogne", "trim the", "trim spaces", "extra spaces"],
    "aggregate":   ["total par", "somme par", "par pays", "par statut", "compte le nombre", "chiffre d'affaires", "agrege", "moyenne par", "total per", "sum per", "per country", "by country", "per month", "by month", "per status", "per customer", "count the number", "revenue", "average per", "group by"],
    "rename":      ["renomme", "en 'amount'", "appelle plutot", "rename", "call it"],
    "join":        ["associe", "joins", "joindre", "jointure", "rattache", "enrichi",
                    "produit cartesien", "toutes les combinaisons", "cross join", "chaque combinaison", "join", "joined", "enrich", "match each", "look up", "lookup"],
    "union":       ["empile", "un seul fichier", "concatene", "ajoute les lignes de", "stack", "append the rows of", "combine the files", "concatenate"],
    "merge":       ["fusionne", "merge"],
    "pivot":       ["tableau croise", "en lignes", "en colonnes", "pivot", "crosstab", "one column per"],
    "unpivot":     ["format long", "une ligne par couple", "colonne par mois", "long format", "one row per pair", "unpivot"],
    "transpose":   ["transpose"],
    "script":      ["script python", "code personnalise"],
    "text_to_rows": ["une ligne par valeur", "une ligne par tag", "eclate", "separe en lignes",
                     "decoupe en lignes", "split into rows", "one row per value"],
    "window":      ["rang ", "numero de ligne", "row_number", "classement par", "cumul", "total cumule",
                    "somme cumulee", "ligne precedente", "valeur precedente", "ligne suivante",
                    "running total", "fonction de fenetre", "window function"],
}

MODE_HINTS = {
    "append":  ["a la fin", "ajoute les lignes", "sans l'ecraser", "sans ecraser", "ajoute a",
                "append", "add the rows", "without overwriting"],
    "upsert":  ["mettant a jour", "met a jour", "upsert", "lignes existantes",
                "update existing", "insert or update", "updating the existing",
                "update the existing", "existing rows", "never duplicate", "is the key"],
    "replace": ["remplace le contenu", "ecrase", "remplacant", "overwrite", "replace the content"],
}

EXT_TO_TYPE = {".csv": "csv", ".json": "json", ".parquet": "parquet"}

# Technologies et notions citees en clair mais absentes du DSL : si l'une
# apparait dans la demande, le manifeste ne peut pas y repondre — il faut le
# dire a l'utilisateur au lieu de lui rendre un pipeline qui fait autre chose.
UNSUPPORTED = {
    "s3": "an S3 connector", "bigquery": "a BigQuery connector",
    "redshift": "a Redshift connector",
    "kafka": "a Kafka connector", "teams": "a Teams action",
    "slack": "a Slack action", "cluster": "distributed execution",
    "distribu": "distributed execution", "spark": "Spark",
    "conteneur": "a container (a Studio notion, not in the DSL)",
    "sequence": "a Sequence container (a Studio notion)",
    "error scope": "an Error Scope container (a Studio notion)",
    "retry scope": "a Retry Scope container (a Studio notion)",
}

NUMERIC_AGG = re.compile(r"(somme|total|moyenne|chiffre d'affaires|montants?|sum|average|revenue|amounts?)", re.I)

NUMERIC_COMPARE = re.compile(
    r"(depasse|superieur|inferieur|plus de|moins de|greater than|less than|more than|above|below|>|<|>=|<=)", re.I)


def _split_output(p: str):
    """(côté entrée, côté sortie) d'une demande : « … dans X » / « … into X »."""
    for word in ("dans", " into ", " to "):
        if word in p:
            head, tail = p.split(word, 1)
            return head, tail
    return p, p


def _steps(docs: Dict[str, Any]) -> List[str]:
    doc = docs.get("transformations.yaml")
    if not isinstance(doc, dict):
        return []
    steps = doc.get("steps")
    if steps is None and isinstance(doc.get("transformations"), dict):
        steps = doc["transformations"].get("steps")
    out = []
    for s in steps or []:
        if isinstance(s, dict) and len(s) == 1:
            out.append(next(iter(s)))
    return out


def check(prompt: str, files: Dict[str, str], docs: Dict[str, Any]) -> List[str]:
    """Retourne la liste des alertes. Liste vide = rien de suspect détecté."""
    alerts: List[str] = []
    p = _norm(prompt)
    ops = _steps(docs)

    src_doc = docs.get("sources.yaml")
    sources = (src_doc.get("sources") or {}) if isinstance(src_doc, dict) else {}
    dst_doc = docs.get("destinations.yaml")
    dests = (dst_doc.get("destinations") or {}) if isinstance(dst_doc, dict) else {}
    is_workflow = "workflow.yaml" in files

    # R0 — rien produit du tout
    if not files:
        return ["no manifest produced for a request that Hydra can handle"]

    # R10 — la demande cite une technologie absente du DSL
    for needle, label in UNSUPPORTED.items():
        if needle in p:
            alerts.append(f"the request mentions {label}: Hydra does not support "
                          f"it, so the manifests answer something else")

    # R11 — un workflow rendu pour une demande qui n'en réclame pas
    if is_workflow:
        orchestration = ("workflow", "enchain", "puis ", "ordonnance", "planifi",
                         "quotidien", "cron", "plusieurs jobs", "depend",
                         "en parallele", "retente", "reessay",
                         "schedule", "several jobs", "in parallel", "retry")
        if not any(h in p for h in orchestration):
            alerts.append("a workflow was produced although the request describes "
                          "a simple source -> destination job")

    # R1 — opération réclamée par la demande mais absente des étapes
    upsert = any(isinstance(v, dict) and isinstance(v.get("load"), dict)
                 and v["load"].get("mode") == "upsert" for v in dests.values())
    for op, hints in OP_HINTS.items():
        if op in ops or is_workflow:
            continue
        if op == "deduplicate" and upsert:
            continue  # an upsert on a key already keeps one row per key
        if any(h in p for h in hints):
            alerts.append(f"the request seems to need '{op}', which is not in the steps")

    # R2 — comparaison numérique sur un CSV sans cast préalable
    if not is_workflow and NUMERIC_COMPARE.search(p):
        csv_source = any(isinstance(v, dict) and v.get("type") in ("csv", "json")
                         for v in sources.values())
        if csv_source and ("filter" in ops or "calculate" in ops):
            first_num = min([ops.index(o) for o in ("filter", "calculate") if o in ops]
                            or [len(ops)])
            if "cast" not in ops or ops.index("cast") > first_num:
                alerts.append("numeric comparison on an untyped source without a "
                              "'cast' before it: the comparison will be on text")

    # R2b — agrégation numérique sur une source non typée sans cast
    if not is_workflow and NUMERIC_AGG.search(p) and ("aggregate" in ops or "pivot" in ops):
        untyped = any(isinstance(v, dict) and v.get("type") in ("csv", "json")
                      for v in sources.values())
        first = min([ops.index(o) for o in ("aggregate", "pivot") if o in ops]
                    or [len(ops)])
        if untyped and ("cast" not in ops or ops.index("cast") > first):
            alerts.append("numeric aggregation on an untyped source without a "
                          "'cast' before it: the sum will be on text")

    # R12 — un connecteur est nommé dans la demande mais absent des manifestes
    named_connectors = {
        "parquet": "parquet", "postgres": "postgres", "postgresql": "postgres",
        "mysql": "mysql", "mariadb": "mariadb", "mongo": "mongodb",
        "sql server": "sqlserver", "sqlserver": "sqlserver", "mssql": "sqlserver",
        "mongodb": "mongodb", "csv": "csv", "json": "json", "sqlite": "sqlite",
        "snowflake": "snowflake", "cdc": "postgresql_cdc",
        "api web": "web_api", "api": "web_api",
    }
    used = {v.get("type") for v in list(sources.values()) + list(dests.values())
            if isinstance(v, dict) and v.get("type")}
    if used:
        aliases = {"postgres": {"postgres", "postgresql"},
                   "sqlserver": {"sqlserver", "mssql"},
                   "mysql": {"mysql", "mariadb"},
                   "mariadb": {"mysql", "mariadb"}}
        for mot, attendu in named_connectors.items():
            if mot not in p:
                continue
            acceptes = aliases.get(attendu, {attendu})
            if not (used & acceptes):
                alerts.append(f"the request mentions '{mot}' but no "
                              f"'{attendu}' connector is declared")

    # R3 — mode de chargement contredit par la demande
    for mode, hints in MODE_HINTS.items():
        if not any(h in p for h in hints):
            continue
        got = {(v.get("load") or {}).get("mode") for v in dests.values()
               if isinstance(v, dict) and isinstance(v.get("load"), dict)}
        if got and mode not in got:
            alerts.append(f"the request suggests the '{mode}' mode, "
                          f"the manifests use {sorted(x for x in got if x)}")

    # R3b — aucune intention de mode exprimée : tout sauf 'replace' est suspect
    if not is_workflow and not any(h in p for hs in MODE_HINTS.values() for h in hs):
        got = {(v.get("load") or {}).get("mode") for v in dests.values()
               if isinstance(v, dict) and isinstance(v.get("load"), dict)}
        other = {g for g in got if g and g != "replace"}
        if other:
            alerts.append(f"no mode is asked for explicitly but the "
                          f"manifests use {sorted(other)} instead of 'replace'")

    # R4b — extension du fichier d'entrée incohérente avec le type de source
    dest_paths = " ".join(
        str(x) for v in dests.values() if isinstance(v, dict)
        for x in ((v.get("load") or {}).get("table") if isinstance(v.get("load"), dict) else None,
                  (v.get("connection") or {}).get("path") if isinstance(v.get("connection"), dict) else None)
        if x).lower()
    for ext, expected in EXT_TO_TYPE.items():
        head = _split_output(p)[0]
        named = [f for f in re.findall(r"[\w./\\-]+" + re.escape(ext), head)
                 if Path(f.replace("\\", "/")).name.lower() not in dest_paths]  # an output file is not an input
        if ext not in head or (re.findall(r"[\w./\\-]+" + re.escape(ext), head) and not named):
            continue
        got = {v.get("type") for v in sources.values() if isinstance(v, dict)}
        if got and expected not in got:
            alerts.append(f"the requested input is '{ext}' but the source "
                          f"is of type {sorted(x for x in got if x)}")

    # R4 — extension du fichier de sortie incohérente avec le type de destination
    for ext, expected in EXT_TO_TYPE.items():
        if ext not in p:
            continue
        # l'extension doit apparaître du côté sortie de la phrase
        tail = _split_output(p)[1]
        if ext not in tail:
            continue
        got = {v.get("type") for v in dests.values() if isinstance(v, dict)}
        if got and expected not in got:
            alerts.append(f"the requested output is '{ext}' but the destination "
                          f"is of type {sorted(x for x in got if x)}")

    # R5 — plusieurs fichiers nommés, une seule source déclarée
    named = set(re.findall(r"[\w\-]+\.(?:csv|json|parquet)", p))
    if not is_workflow and len(named) >= 3 and len(sources) < 2:
        alerts.append(f"{len(named)} files named in the request, "
                      f"{len(sources)} source(s) declared")

    # R6 — secret en clair
    if any(h in p for h in ("mot de passe", "secret", "identifiant de connexion",
                            "password", "credential")):
        blob = "\n".join(files.values())
        if "env:" not in blob and "${" not in blob:
            alerts.append("the request mentions a secret but no "
                          "{{ env:NAME }} appears in the manifests")

    # R7 — planification demandée, trigger absent
    if any(h in p for h in ("quotidien", "chaque jour", "tous les jours", "a 8h", "cron", "planifi",
                            "every day", "daily", "every night", "nightly", "schedule")):
        wf = docs.get("workflow.yaml") or {}
        wf = wf.get("workflow", wf) if isinstance(wf, dict) else {}
        trig = (wf.get("trigger") or {}) if isinstance(wf, dict) else {}
        if trig.get("type") != "schedule" or not trig.get("cron"):
            alerts.append("a schedule is requested but no 'schedule' "
                          "trigger with a cron is declared")

    # R8 — re-tentatives demandées, retry absent
    if any(h in p for h in ("retente", "reessay", "re-tent", "trois fois", "retry", "three times")):
        wf = docs.get("workflow.yaml") or {}
        wf = wf.get("workflow", wf) if isinstance(wf, dict) else {}
        steps = wf.get("steps") or [] if isinstance(wf, dict) else []
        if not any(isinstance(s, dict) and s.get("retry") for s in steps):
            alerts.append("retries are requested but no 'retry' is declared")

    # R9 — dépendances demandées, DAG plat
    if any(h in p for h in ("puis ", "une fois", "depend", "attend", " then ", "once ", "after ")):
        wf = docs.get("workflow.yaml") or {}
        wf = wf.get("workflow", wf) if isinstance(wf, dict) else {}
        steps = wf.get("steps") or [] if isinstance(wf, dict) else []
        if steps and not any(isinstance(s, dict) and s.get("depends_on") for s in steps):
            alerts.append("a sequence is requested but no step "
                          "declares 'depends_on'")

    return alerts
