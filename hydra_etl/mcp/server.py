"""
server.py — Serveur MCP local de Hydra.

Expose le moteur Hydra à l'assistant IA de l'utilisateur : découvrir le DSL,
lire et écrire des jobs, les **valider**, les exécuter. Le serveur ne contient
aucun modèle et n'émet aucune requête réseau — c'est le client qui apporte
l'intelligence.

Trois principes de conception, qui expliquent la forme des outils :

1. **Les descriptions sont l'interface.** Elles sont lues par un modèle, pas
   par un humain. Chacune dit ce que l'outil fait, quand s'en servir, et le
   piège à éviter.
2. **Aucune écriture sans validation.** `hydra_write_job` refuse d'écrire un
   job que l'oracle rejette : un agent ne peut pas laisser derrière lui un
   dossier invalide.
3. **Aucune exécution implicite.** Écrire n'exécute pas. `hydra_run_job` est un
   appel distinct, que l'utilisateur voit passer.

Lancement :
    hydra-mcp                 # transport stdio, pour un client MCP
    python -m hydra_etl.mcp   # équivalent
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer          # SDK MCP 2.x
except ModuleNotFoundError:                             # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer   # SDK MCP 1.x
    except ModuleNotFoundError:
        raise SystemExit(
            "Le SDK MCP est absent. Installez-le avec :\n"
            "    pip install \"hydra-etl[mcp]\"\n"
        ) from None

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"

JOB_FILES = ("sources.yaml", "transformations.yaml",
             "destinations.yaml", "pipeline.yaml")


# ---------------------------------------------------------------------------
# Racine de travail : l'agent ne sort pas du dossier autorisé
# ---------------------------------------------------------------------------

def workspace() -> Path:
    """Dossier dans lequel l'agent a le droit de lire et d'écrire."""
    return Path(os.environ.get("HYDRA_MCP_WORKSPACE", Path.cwd())).resolve()


def safe_path(relative: str) -> Path:
    """
    Résout un chemin **à l'intérieur** de l'espace de travail.

    Un agent peut se tromper, ou suivre une consigne malveillante trouvée dans
    un fichier de données. On refuse tout ce qui sort de la racine.

    Trois contrôles, et non un seul, parce qu'aucun ne suffit :

    1. Les séparateurs sont normalisés. Sans cela, une suite de ".." séparés
       par des antislashs s'évaderait sous
       Windows tout en passant pour un simple nom de fichier sous Linux — le
       serveur n'aurait pas le même comportement selon la machine.
    2. Les chemins absolus et les segments `..` sont refusés explicitement.
    3. Le résultat résolu doit rester sous la racine — dernier filet, qui
       attrape aussi les liens symboliques.
    """
    base = workspace()
    normalized = relative.replace("\\", "/").strip()

    if not normalized or normalized in (".", "./"):
        return base
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        raise ValueError(
            f"Chemin absolu refusé : {relative!r}. "
            f"Donne un chemin relatif à {base}"
        )
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError(
            f"Chemin hors de l'espace de travail : {relative!r}. "
            f"Racine autorisée : {base}"
        )

    target = (base / normalized).resolve()
    if base != target and base not in target.parents:
        raise ValueError(
            f"Chemin hors de l'espace de travail : {relative!r}. "
            f"Racine autorisée : {base}"
        )
    return target


def _spec(name: str) -> Any:
    path = SCHEMAS / name
    if not path.exists():
        raise FileNotFoundError(
            f"Spécification absente : {name}. "
            "Régénérez-la avec `python tools/spec_export.py`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


_NOISE = ("@", "─", "━", "│", "┌", "└", "├", "═", "╔", "╚", "║", "•", "▄", "▀")


def _clean(output: str) -> str:
    """
    Retire le bandeau ASCII et les filets décoratifs de la CLI.

    Ces lignes sont faites pour l'œil humain. Rendues à un modèle, elles
    coûtent des jetons et noient le message utile — or c'est le message utile
    qui lui permet de corriger son erreur.
    """
    kept = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        letters = sum(c.isalnum() for c in stripped)
        if letters < max(3, len(stripped) // 4):
            continue
        if stripped[0] in _NOISE:
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def _hdrctl(*args: str) -> tuple[bool, str]:
    """Appelle la CLI Hydra en sous-processus, sortie normalisée."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "hydra_etl.cli.hdrctl", *args],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=600,
    )
    ok = proc.returncode == 0
    output = _clean(proc.stdout + proc.stderr)
    if not ok:
        # En cas d'echec, on ne rend que les lignes d'erreur. Le bandeau, les
        # vingt lignes « ok » et le compteur (qui annonce « 0 error(s) » tout
        # en signalant une erreur — anomalie A8 du produit) n'aident pas le
        # modele a se corriger : ils le desorientent.
        errs = [l.strip()[4:].strip() if l.strip().startswith("err ") else l.strip()
                for l in output.splitlines() if l.strip().startswith("err ")]
        if errs:
            output = "\n".join(f"- {e}" for e in errs)
        else:
            output = "\n".join(
                l for l in output.splitlines()
                if not l.strip().lower().startswith("ok ")
                and "dsl validation" not in l.lower()
                and "error(s) detected" not in l.lower()
                and "devops edition" not in l.lower()
            )
    return ok, output


# ---------------------------------------------------------------------------

def build_server() -> Any:
    server = MCPServer(
        name="hydra",
        instructions=(
            "Hydra est un moteur ETL déclaratif. Un job est un dossier "
            "contenant quatre manifestes YAML : sources.yaml, "
            "transformations.yaml (facultatif), destinations.yaml et "
            "pipeline.yaml.\n\n"
            "Méthode recommandée : appelle d'abord hydra_list_operations et "
            "hydra_list_connectors pour connaître le vocabulaire exact, puis "
            "écris le job avec hydra_write_job — il valide avant d'écrire et "
            "te rend les erreurs si quelque chose ne va pas. N'exécute jamais "
            "un job sans que l'utilisateur l'ait demandé.\n\n"
            "N'invente jamais un connecteur, une opération ou une action : "
            "s'ils ne figurent pas dans les listes, ils n'existent pas."
        ),
    )

    # -- Découverte du DSL ---------------------------------------------------

    @server.tool(
        description=(
            "Liste les 18 opérations de transformation de Hydra avec leurs "
            "paramètres obligatoires. À appeler AVANT d'écrire un "
            "transformations.yaml : toute opération absente de cette liste "
            "n'existe pas et sera rejetée."
        )
    )
    def hydra_list_operations() -> str:
        index = _spec("index.json")
        rows = []
        for entry in index["schemas"]:
            if entry["kind"] != "transformation":
                continue
            sch = _spec(entry["path"])
            required = ", ".join(sch.get("required", [])) or "—"
            rows.append(f"{entry['dslName']:<14} requis: {required}")
        return "\n".join(sorted(rows))

    @server.tool(
        description=(
            "Donne le schéma JSON complet d'une opération de transformation : "
            "tous ses paramètres, leurs types, leurs valeurs par défaut. "
            "À appeler quand hydra_list_operations ne suffit pas."
        )
    )
    def hydra_describe_operation(operation: str) -> str:
        path = SCHEMAS / "operations" / f"{operation}.schema.json"
        if not path.exists():
            known = sorted(p.stem.replace(".schema", "")
                           for p in (SCHEMAS / "operations").glob("*.json"))
            return (f"Opération inconnue : {operation!r}.\n"
                    f"Opérations existantes : {', '.join(known)}")
        return json.dumps(_spec(f"operations/{operation}.schema.json"),
                          ensure_ascii=False, indent=2)

    @server.tool(
        description=(
            "Liste les types de connecteurs acceptés par la clé 'type' d'une "
            "source ou d'une destination. Tout autre type échouera à "
            "l'exécution : ni S3, ni BigQuery, ni Snowflake ne sont pris en "
            "charge."
        )
    )
    def hydra_list_connectors() -> str:
        sch = _spec("connectors.schema.json")
        return ", ".join(sch["enum"])

    @server.tool(
        description=(
            "Liste les actions utilisables dans un step de workflow de type "
            "'action'. Attention : une action inconnue est ignorée "
            "silencieusement à l'exécution et le step est compté comme "
            "réussi — vérifie donc le nom avant de l'écrire."
        )
    )
    def hydra_list_actions() -> str:
        sch = _spec("actions.schema.json")
        return ", ".join(sch["enum"])

    # -- Lecture -------------------------------------------------------------

    @server.tool(
        description=(
            "Liste les jobs Hydra présents dans l'espace de travail. Un job "
            "est un dossier contenant un pipeline.yaml. Renvoie les chemins "
            "relatifs, utilisables tels quels dans les autres outils."
        )
    )
    def hydra_list_jobs() -> str:
        base = workspace()
        jobs = sorted(p.parent.relative_to(base).as_posix()
                      for p in base.rglob("pipeline.yaml")
                      if "_archive" not in p.parts and "_backups" not in p.parts)
        if not jobs:
            return f"Aucun job trouvé sous {base}."
        return "\n".join(jobs)

    @server.tool(
        description=(
            "Lit les manifestes d'un job existant. À appeler avant de "
            "modifier un job, pour partir de son contenu réel plutôt que de le "
            "réécrire de mémoire."
        )
    )
    def hydra_read_job(job_path: str) -> str:
        try:
            d = safe_path(job_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        if not d.is_dir():
            return f"Dossier introuvable : {job_path}"
        out = []
        for name in JOB_FILES:
            f = d / name
            if f.exists():
                out.append(f"### {name}\n{f.read_text(encoding='utf-8')}")
        return "\n\n".join(out) or f"Aucun manifeste dans {job_path}."

    # -- Écriture, validation, exécution -------------------------------------

    @server.tool(
        description=(
            "Valide un job avec le validateur officiel de Hydra : structure "
            "des quatre manifestes, et résolution de pipeline.from vers une "
            "source déclarée et de pipeline.to vers une destination déclarée. "
            "C'est la vérité — si cet outil refuse, le job ne tournera pas."
        )
    )
    def hydra_validate_job(job_path: str) -> str:
        try:
            d = safe_path(job_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        ok, output = _hdrctl("validate", str(d))
        return ("VALIDE\n" if ok else "INVALIDE\n") + output

    @server.tool(
        description=(
            "Écrit les manifestes d'un job, APRÈS validation. Chaque manifeste "
            "est passé en texte YAML. Si la validation échoue, rien n'est "
            "écrit et les erreurs sont renvoyées : corrige-les et rappelle "
            "l'outil. Écrire n'exécute pas le job."
        )
    )
    def hydra_write_job(job_path: str,
                        sources_yaml: str,
                        destinations_yaml: str,
                        pipeline_yaml: str,
                        transformations_yaml: str = "") -> str:
        import shutil
        import tempfile

        files = {"sources.yaml": sources_yaml,
                 "destinations.yaml": destinations_yaml,
                 "pipeline.yaml": pipeline_yaml}
        if transformations_yaml.strip():
            files["transformations.yaml"] = transformations_yaml

        for name, content in files.items():
            try:
                yaml.safe_load(content)
            except Exception as exc:
                return f"REFUSÉ — {name} n'est pas du YAML valide : {exc}"

        tmp = Path(tempfile.mkdtemp(prefix="hydra_mcp_"))
        try:
            for name, content in files.items():
                (tmp / name).write_text(content, encoding="utf-8")
            ok, output = _hdrctl("validate", str(tmp))
            if not ok:
                return ("REFUSÉ — rien n'a été écrit. Le validateur signale :\n"
                        + output)
            try:
                target = safe_path(job_path)
            except ValueError as exc:
                return f"REFUSÉ — {exc}"
            target.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (target / name).write_text(content, encoding="utf-8")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        written = ", ".join(sorted(files))
        return (f"ÉCRIT dans {job_path} : {written}.\n"
                f"Le job est valide. Il n'a pas été exécuté — utilise "
                f"hydra_run_job si l'utilisateur le demande.")

    @server.tool(
        description=(
            "Exécute un job Hydra et renvoie le journal d'exécution. "
            "N'appelle cet outil que si l'utilisateur a explicitement demandé "
            "l'exécution : il écrit des données réelles dans la destination."
        )
    )
    def hydra_run_job(job_path: str) -> str:
        try:
            d = safe_path(job_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        ok, output = _hdrctl("run", str(d))
        return ("EXÉCUTION RÉUSSIE\n" if ok else "ÉCHEC\n") + output

    @server.tool(
        description=(
            "Explique une erreur de validation Hydra en langage clair et "
            "propose la correction. À utiliser quand hydra_validate_job ou "
            "hydra_write_job renvoient un message que tu ne sais pas traduire."
        )
    )
    def hydra_explain_error(error_message: str) -> str:
        hints = [
            ("cast", "Un CSV ne porte aucun type : place une étape `cast` "
                     "AVANT toute comparaison numérique ou agrégation."),
            ("from", "`pipeline.from` doit reprendre exactement un identifiant "
                     "déclaré dans sources.yaml."),
            ("to", "`pipeline.to` doit reprendre exactement un identifiant "
                   "déclaré dans destinations.yaml."),
            ("type", "La clé `type` doit valoir l'un des connecteurs listés "
                     "par hydra_list_connectors."),
            ("steps", "transformations.yaml attend une liste `steps`, chaque "
                      "étape étant un objet à UNE seule clé : le nom de "
                      "l'opération."),
            ("mode", "`load.mode` vaut append, replace ou upsert."),
        ]
        low = error_message.lower()
        found = [h for key, h in hints if key in low]
        if not found:
            found = ["Aucune règle connue ne correspond. Relis le schéma de "
                     "l'élément concerné avec hydra_describe_operation."]
        return "\n".join(f"- {h}" for h in found)

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
