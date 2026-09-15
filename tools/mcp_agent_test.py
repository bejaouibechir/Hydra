#!/usr/bin/env python3
"""
mcp_agent_test.py — Éprouve le serveur MCP avec un vrai modèle.

L'Inspector vérifie la plomberie ; ce script vérifie autre chose : **un modèle
choisit-il le bon outil, et remplit-il correctement ses paramètres ?**

C'est la seule façon de savoir si les descriptions d'outils sont claires. Et
c'est pour cela qu'on le lance de préférence avec un PETIT modèle : si
qwen3:1.7b s'en sort, n'importe quel assistant s'en sortira. Un gros modèle
compense les descriptions approximatives et les cache jusqu'à la production.

Usage :
    python tools/mcp_agent_test.py --model qwen3:1.7b
    python tools/mcp_agent_test.py --model gemini-flash-latest --provider openai
    python tools/mcp_agent_test.py --model qwen3:1.7b --scenario 2

Aucune dépendance hors le SDK MCP : urllib suffit pour parler aux modèles.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ModuleNotFoundError:                     # pragma: no cover
    raise SystemExit("SDK MCP absent : pip install \"hydra-etl[mcp]\"")


SYSTEM = """Tu pilotes Hydra, un moteur ETL déclaratif, à travers les outils
fournis. Réponds en te servant des outils : ne rédige pas de YAML dans ta
réponse, écris-le avec l'outil prévu.

Méthode : commence par découvrir le vocabulaire (opérations, connecteurs), et
regarde les données avant d'écrire un job qui manipule des colonnes. N'exécute
jamais un job sans que l'utilisateur l'ait demandé."""

SCENARIOS = [
    # (intitulé, demande, outils qu'un agent avisé devrait appeler)
    ("Découverte",
     "Quelles opérations de transformation Hydra propose-t-il, et quels "
     "connecteurs puis-je utiliser ?",
     {"hydra_list_operations", "hydra_list_connectors"}),

    ("Inspection de données",
     "J'ai un fichier ventes.csv à la racine. Quelles colonnes contient-il ?",
     {"hydra_preview_data"}),

    ("Écriture d'un job",
     "Depuis ventes.csv, garde seulement les lignes dont le montant dépasse "
     "100, et écris le résultat dans sortie.csv. Appelle le job jobs/filtre.",
     {"hydra_write_job"}),

    ("Correction après refus",
     "Écris un job jobs/casse dont le pipeline part d'une source appelée "
     "'inexistante' vers une destination 'dst'. S'il est refusé, corrige-le.",
     {"hydra_write_job"}),

    ("Vérification de cohérence",
     "Le job jobs/filtre répond-il bien à ma demande : filtrer les montants "
     "supérieurs à 100 et trier par montant décroissant ?",
     {"hydra_check_job"}),

    ("Demande impossible",
     "Crée un job qui lit depuis un bucket S3 et écrit dans BigQuery.",
     set()),          # un agent avisé refuse et explique
]


# ---------------------------------------------------------------------------

def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Sans le corps de la reponse, un 400 ne dit rien. Or c'est presque
        # toujours le schema d'un outil que le fournisseur refuse.
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise RuntimeError(f"HTTP {exc.code} — {detail}") from None


# Les fournisseurs compatibles OpenAI n'acceptent qu'un sous-ensemble de JSON
# Schema dans `parameters`. Gemini, notamment, refuse additionalProperties,
# title, default et les alternatives imbriquees. On ne garde donc que ce qui
# est universellement compris.
_SCHEMA_KEYS = {"type", "description", "properties", "required", "items",
                "enum", "minimum", "maximum"}


def sanitize_schema(node: Any) -> Any:
    """Réduit un JSON Schema au sous-ensemble accepté partout."""
    if isinstance(node, list):
        return [sanitize_schema(x) for x in node]
    if not isinstance(node, dict):
        return node

    for alt in ("anyOf", "oneOf", "allOf"):
        if alt in node and isinstance(node[alt], list) and node[alt]:
            merged = dict(node)
            merged.pop(alt)
            branch = node[alt][0]
            if isinstance(branch, dict):
                merged.update(branch)
            return sanitize_schema(merged)

    out: dict = {}
    for key, value in node.items():
        if key == "properties":
            # `properties` associe des NOMS a des schemas : ses cles ne sont
            # pas des mots-cles et ne doivent surtout pas etre filtrees.
            out["properties"] = {name: sanitize_schema(sub)
                                 for name, sub in (value or {}).items()}
        elif key in _SCHEMA_KEYS:
            out[key] = sanitize_schema(value)
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def chat(args, messages: list[dict], tools: list[dict]) -> dict:
    """Un tour de conversation. Retourne le message du modèle."""
    if args.provider == "openai":
        body = _post(
            args.url.rstrip("/") + "/chat/completions",
            {"model": args.model, "messages": messages, "tools": tools,
             "temperature": 0},
            {"Content-Type": "application/json",
             "Authorization": f"Bearer {args.api_key}"},
            args.timeout,
        )
        return (body.get("choices") or [{}])[0].get("message") or {}

    body = _post(
        args.url.rstrip("/") + "/api/chat",
        {"model": args.model, "messages": messages, "tools": tools,
         "stream": False, "think": False,
         "options": {"temperature": 0, "num_ctx": 8192}},
        {"Content-Type": "application/json"},
        args.timeout,
    )
    return body.get("message") or {}


def to_tool_schema(tool: Any) -> dict:
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {})
    cleaned = sanitize_schema(schema or {"type": "object", "properties": {}})
    return {"type": "function",
            "function": {"name": tool.name,
                         "description": tool.description or "",
                         "parameters": cleaned}}


def tool_calls_of(message: dict) -> list[dict]:
    calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw = fn.get("arguments")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        calls.append({"id": call.get("id", fn.get("name", "")),
                      "name": fn.get("name", ""),
                      "arguments": raw or {}})
    return calls


# ---------------------------------------------------------------------------

async def run_scenario(session: ClientSession, tools: list[dict],
                       args, titre: str, demande: str,
                       attendus: set[str]) -> dict:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": demande}]
    appeles: list[str] = []
    final = ""

    for _ in range(args.max_steps):
        try:
            message = chat(args, messages, tools)
        except (urllib.error.URLError, OSError, RuntimeError) as exc:
            return {"titre": titre, "erreur": f"{exc}",
                    "appeles": appeles, "final": ""}

        calls = tool_calls_of(message)
        if not calls:
            final = (message.get("content") or "").strip()
            break

        messages.append({"role": "assistant",
                         "content": message.get("content") or "",
                         "tool_calls": message.get("tool_calls")})
        for call in calls:
            appeles.append(call["name"])
            try:
                result = await session.call_tool(call["name"], call["arguments"])
                texte = "\n".join(c.text for c in result.content
                                  if getattr(c, "text", None))
            except Exception as exc:
                texte = f"Erreur d'outil : {type(exc).__name__}: {exc}"
            messages.append({"role": "tool", "name": call["name"],
                             "tool_call_id": call["id"],
                             "content": texte[:4000]})

    manquants = attendus - set(appeles)
    inconnus = [n for n in appeles if n not in {t["function"]["name"] for t in tools}]
    return {"titre": titre, "appeles": appeles, "final": final,
            "manquants": sorted(manquants), "inconnus": inconnus, "erreur": ""}


async def main_async(args) -> int:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "hydra_etl.mcp"],
        env={**os.environ, "HYDRA_MCP_WORKSPACE": str(Path(args.workspace).resolve())},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = (await session.list_tools()).tools
            tools = [to_tool_schema(t) for t in listed]
            if args.dump_tools:
                for t in tools:
                    f = t["function"]
                    params = f["parameters"]
                    print(f"{f['name']:<26} "
                          f"params={list(params.get('properties', {}))} "
                          f"requis={params.get('required', [])}")
                return 0
            print(f"{len(tools)} outils exposés · modèle {args.model} · "
                  f"espace de travail {args.workspace}\n")

            scenarios = SCENARIOS
            if args.scenario:
                scenarios = [SCENARIOS[args.scenario - 1]]

            resultats = []
            for titre, demande, attendus in scenarios:
                print(f"── {titre}")
                print(f"   demande : {demande[:90]}")
                r = await run_scenario(session, tools, args, titre, demande, attendus)
                resultats.append(r)
                if r["erreur"]:
                    print(f"   ERREUR : {r['erreur']}\n")
                    continue
                print(f"   outils appelés : {' → '.join(r['appeles']) or 'aucun'}")
                if r["manquants"]:
                    print(f"   ATTENDUS NON APPELÉS : {', '.join(r['manquants'])}")
                if r["inconnus"]:
                    print(f"   OUTILS INVENTÉS : {', '.join(r['inconnus'])}")
                if r["final"]:
                    print(f"   réponse : {r['final'][:220]}")
                print()

    ok = sum(1 for r in resultats
             if not r["erreur"] and not r["manquants"] and not r["inconnus"])
    print(f"── Bilan : {ok}/{len(resultats)} scénarios menés comme attendu")
    if any(r.get("inconnus") for r in resultats):
        print("   Des outils ont été inventés : les descriptions sont ambiguës.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Éprouve le serveur MCP de Hydra avec un vrai modèle.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--provider", choices=["ollama", "openai"], default="ollama")
    ap.add_argument("--url", default="")
    ap.add_argument("--api-key",
                    default=(os.environ.get("GEMINI_API_KEY")
                             or os.environ.get("OPENAI_API_KEY", "")))
    ap.add_argument("--workspace", default=str(ROOT / "test_scenarios"))
    ap.add_argument("--scenario", type=int, default=0,
                    help="ne jouer qu'un scénario (1 à 6)")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dump-tools", action="store_true",
                    help="afficher les schémas envoyés au modèle, puis quitter")
    args = ap.parse_args()

    if not args.url:
        args.url = ("https://generativelanguage.googleapis.com/v1beta/openai"
                    if args.provider == "openai" else "http://localhost:11434")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
