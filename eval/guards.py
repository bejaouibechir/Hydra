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
import unicodedata
from typing import Any, Dict, List


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# --- Ce qui, dans une demande, réclame une opération ------------------------
# Volontairement large : mieux vaut une alerte de trop qu'une erreur silencieuse.
OP_HINTS: Dict[str, List[str]] = {
    "select":      ["ne garde que", "garde seulement", "seules les colonnes", "colonnes ", "selectionne"],
    "filter":      ["filtre", "garde les", "seulement les lignes", "dont le", "superieur", "depasse", "inferieur", "= error", "uniquement les", "de 2026", "de 2025"],
    "cast":        ["convertis", "en float", "en int", "en datetime", "type"],
    "calculate":   ["calcule", "ajoute une colonne", "egale au", "divise", "multiplie"],
    "sort":        ["trie", "classe", "du plus", "croissant", "decroissant", "ordre"],
    "deduplicate": ["doublon", "dedoublonne", "unique"],
    "fill_null":   ["valeurs manquantes", "valeur manquante", "remplace les vides", "null"],
    "clean":       ["nettoie", "minuscule", "majuscule", "espaces en trop"],
    "trim":        ["espaces en trop", "rogne"],
    "aggregate":   ["total par", "somme par", "par pays", "par statut", "compte le nombre", "chiffre d'affaires", "agrege", "moyenne par"],
    "rename":      ["renomme", "en 'amount'", "appelle plutot"],
    "join":        ["associe", "joins", "jointure", "rattache", "enrichi"],
    "union":       ["empile", "un seul fichier", "concatene", "ajoute les lignes de"],
    "merge":       ["fusionne"],
    "pivot":       ["tableau croise", "en lignes", "en colonnes"],
    "unpivot":     ["format long", "une ligne par couple", "colonne par mois"],
    "transpose":   ["transpose"],
    "script":      ["script python", "code personnalise"],
}

MODE_HINTS = {
    "append":  ["a la fin", "ajoute les lignes", "sans l'ecraser", "sans ecraser", "ajoute a"],
    "upsert":  ["mettant a jour", "met a jour", "upsert", "lignes existantes"],
    "replace": ["remplace le contenu", "ecrase", "remplacant"],
}

EXT_TO_TYPE = {".csv": "csv", ".json": "json", ".parquet": "parquet"}

# Technologies et notions citees en clair mais absentes du DSL : si l'une
# apparait dans la demande, le manifeste ne peut pas y repondre — il faut le
# dire a l'utilisateur au lieu de lui rendre un pipeline qui fait autre chose.
UNSUPPORTED = {
    "s3": "connecteur S3", "bigquery": "connecteur BigQuery",
    "snowflake": "connecteur Snowflake", "redshift": "connecteur Redshift",
    "kafka": "connecteur Kafka", "teams": "action Teams",
    "slack": "action Slack", "cluster": "execution distribuee",
    "distribu": "execution distribuee", "spark": "Spark",
    "conteneur": "conteneur (notion Studio, absente du DSL)",
    "sequence": "conteneur Sequence (notion Studio)",
    "error scope": "conteneur Error Scope (notion Studio)",
    "retry scope": "conteneur Retry Scope (notion Studio)",
    "lowercase": "operation 'lowercase' (c'est 'clean' avec case: lower)",
}

NUMERIC_AGG = re.compile(r"(somme|total|moyenne|chiffre d'affaires|montants?)", re.I)

NUMERIC_COMPARE = re.compile(
    r"(depasse|superieur|inferieur|plus de|moins de|>|<|>=|<=)", re.I)


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
        return ["aucun manifeste produit pour une demande réalisable"]

    # R10 — la demande cite une technologie absente du DSL
    for needle, label in UNSUPPORTED.items():
        if needle in p:
            alerts.append(f"la demande mentionne {label} : Hydra ne le prend pas "
                          f"en charge, le manifeste produit répond à autre chose")

    # R11 — un workflow rendu pour une demande qui n'en réclame pas
    if is_workflow:
        orchestration = ("workflow", "enchain", "puis ", "ordonnance", "planifi",
                         "quotidien", "cron", "plusieurs jobs", "depend",
                         "en parallele", "retente", "reessay")
        if not any(h in p for h in orchestration):
            alerts.append("un workflow a été produit alors que la demande décrit "
                          "un job simple source -> destination")

    # R1 — opération réclamée par la demande mais absente des étapes
    for op, hints in OP_HINTS.items():
        if op in ops or is_workflow:
            continue
        if any(h in p for h in hints):
            alerts.append(f"la demande semble réclamer '{op}', absent des étapes")

    # R2 — comparaison numérique sur un CSV sans cast préalable
    if not is_workflow and NUMERIC_COMPARE.search(p):
        csv_source = any(isinstance(v, dict) and v.get("type") in ("csv", "json")
                         for v in sources.values())
        if csv_source and ("filter" in ops or "calculate" in ops):
            first_num = min([ops.index(o) for o in ("filter", "calculate") if o in ops]
                            or [len(ops)])
            if "cast" not in ops or ops.index("cast") > first_num:
                alerts.append("comparaison numérique sur une source non typée "
                              "sans 'cast' préalable : la comparaison portera sur du texte")

    # R2b — agrégation numérique sur une source non typée sans cast
    if not is_workflow and NUMERIC_AGG.search(p) and ("aggregate" in ops or "pivot" in ops):
        untyped = any(isinstance(v, dict) and v.get("type") in ("csv", "json")
                      for v in sources.values())
        first = min([ops.index(o) for o in ("aggregate", "pivot") if o in ops]
                    or [len(ops)])
        if untyped and ("cast" not in ops or ops.index("cast") > first):
            alerts.append("agrégation numérique sur une source non typée sans "
                          "'cast' préalable : la somme portera sur du texte")

    # R3 — mode de chargement contredit par la demande
    for mode, hints in MODE_HINTS.items():
        if not any(h in p for h in hints):
            continue
        got = {(v.get("load") or {}).get("mode") for v in dests.values()
               if isinstance(v, dict) and isinstance(v.get("load"), dict)}
        if got and mode not in got:
            alerts.append(f"la demande suggère le mode '{mode}', "
                          f"le manifeste utilise {sorted(x for x in got if x)}")

    # R3b — aucune intention de mode exprimée : tout sauf 'replace' est suspect
    if not is_workflow and not any(h in p for hs in MODE_HINTS.values() for h in hs):
        got = {(v.get("load") or {}).get("mode") for v in dests.values()
               if isinstance(v, dict) and isinstance(v.get("load"), dict)}
        other = {g for g in got if g and g != "replace"}
        if other:
            alerts.append(f"aucun mode n'est demandé explicitement mais le "
                          f"manifeste utilise {sorted(other)} au lieu de 'replace'")

    # R4b — extension du fichier d'entrée incohérente avec le type de source
    for ext, expected in EXT_TO_TYPE.items():
        head = p.split("dans", 1)[0] if "dans" in p else p
        if ext not in head:
            continue
        got = {v.get("type") for v in sources.values() if isinstance(v, dict)}
        if got and expected not in got:
            alerts.append(f"l'entrée demandée est en '{ext}' mais la source "
                          f"est de type {sorted(x for x in got if x)}")

    # R4 — extension du fichier de sortie incohérente avec le type de destination
    for ext, expected in EXT_TO_TYPE.items():
        if ext not in p:
            continue
        # l'extension doit apparaître du côté sortie de la phrase
        tail = p.split("dans", 1)[-1] if "dans" in p else p
        if ext not in tail:
            continue
        got = {v.get("type") for v in dests.values() if isinstance(v, dict)}
        if got and expected not in got:
            alerts.append(f"la sortie demandée est en '{ext}' mais la destination "
                          f"est de type {sorted(x for x in got if x)}")

    # R5 — plusieurs fichiers nommés, une seule source déclarée
    named = set(re.findall(r"[\w\-]+\.(?:csv|json|parquet)", p))
    if not is_workflow and len(named) >= 3 and len(sources) < 2:
        alerts.append(f"{len(named)} fichiers nommés dans la demande, "
                      f"{len(sources)} source(s) déclarée(s)")

    # R6 — secret en clair
    if any(h in p for h in ("mot de passe", "secret", "identifiant de connexion")):
        blob = "\n".join(files.values())
        if "env:" not in blob and "${" not in blob:
            alerts.append("la demande parle de secret mais aucun "
                          "{{ env:NOM }} n'apparaît dans les manifestes")

    # R7 — planification demandée, trigger absent
    if any(h in p for h in ("quotidien", "chaque jour", "tous les jours", "a 8h", "cron", "planifi")):
        wf = docs.get("workflow.yaml") or {}
        wf = wf.get("workflow", wf) if isinstance(wf, dict) else {}
        trig = (wf.get("trigger") or {}) if isinstance(wf, dict) else {}
        if trig.get("type") != "schedule" or not trig.get("cron"):
            alerts.append("planification demandée mais aucun trigger "
                          "'schedule' avec cron n'est déclaré")

    # R8 — re-tentatives demandées, retry absent
    if any(h in p for h in ("retente", "reessay", "re-tent", "trois fois", "retry")):
        wf = docs.get("workflow.yaml") or {}
        wf = wf.get("workflow", wf) if isinstance(wf, dict) else {}
        steps = wf.get("steps") or [] if isinstance(wf, dict) else []
        if not any(isinstance(s, dict) and s.get("retry") for s in steps):
            alerts.append("re-tentatives demandées mais aucun 'retry' n'est déclaré")

    # R9 — dépendances demandées, DAG plat
    if any(h in p for h in ("puis ", "une fois", "depend", "attend")):
        wf = docs.get("workflow.yaml") or {}
        wf = wf.get("workflow", wf) if isinstance(wf, dict) else {}
        steps = wf.get("steps") or [] if isinstance(wf, dict) else []
        if steps and not any(isinstance(s, dict) and s.get("depends_on") for s in steps):
            alerts.append("un enchaînement est demandé mais aucun step "
                          "ne déclare de 'depends_on'")

    return alerts
