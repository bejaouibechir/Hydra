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

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hydra_etl import __version__

try:
    from mcp.types import ToolAnnotations
except ModuleNotFoundError:                             # pragma: no cover
    ToolAnnotations = None                              # type: ignore[assignment]

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

# La spécification est embarquée dans le paquet ; la copie du dépôt sert de
# repli quand on travaille depuis les sources. Sans la première, tout ce qui
# lit la spécification échoue une fois `pip install` fait.
_PACKAGE_SCHEMAS = Path(__file__).resolve().parent.parent / "ai" / "schemas"
_REPO_SCHEMAS = ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"
SCHEMAS = _PACKAGE_SCHEMAS if (_PACKAGE_SCHEMAS / "index.json").exists() else _REPO_SCHEMAS

JOB_FILES = ("sources.yaml", "transformations.yaml",
             "destinations.yaml", "pipeline.yaml")


def _annot(*, readonly: bool = False, destructive: bool = False,
           title: str = "") -> Any:
    """
    Annotations lues par le client MCP.

    Une consigne écrite dans une description ne retient pas un agent : à
    l'essai, un modèle a exécuté un job sans qu'on le lui demande, alors que la
    description l'interdisait. Les annotations, elles, sont lues par le client,
    qui peut demander confirmation avant une action destructive — c'est une
    barrière de protocole, pas une prière.
    """
    if ToolAnnotations is None:                         # pragma: no cover
        return None
    return ToolAnnotations(
        title=title or None,
        readOnlyHint=readonly,
        destructiveHint=destructive,
        idempotentHint=readonly,
        openWorldHint=False,
    )


LECTURE = dict(readonly=True)
ECRITURE = dict(destructive=False)
EXECUTION = dict(destructive=True)

CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"


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


def _outputs_summary(job_dir: Path) -> str:
    """
    Décrit ce que le job a produit : fichier, lignes, colonnes.

    Sans cela, l'agent ne dispose que d'un journal d'exécution — de quoi dire
    « ça a marché », pas de quoi rédiger un rapport ni repérer une incohérence
    (zéro ligne écrite, par exemple, alors que la source en contenait).
    """
    manifest = job_dir / "destinations.yaml"
    if not manifest.exists():
        return ""
    try:
        doc = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        dests = doc.get("destinations") or {}
    except Exception:
        return ""

    lignes = []
    for name, defn in dests.items():
        if not isinstance(defn, dict):
            continue
        load = defn.get("load") or {}
        table = load.get("table")
        if not table:
            continue
        if defn.get("type") not in ("csv", "json", "parquet"):
            lignes.append(f"- {name} : {defn.get('type')} → {table}")
            continue
        path = (job_dir / str(table)) if not Path(str(table)).is_absolute() else Path(str(table))
        if not path.exists():
            lignes.append(f"- {name} : {table} — fichier introuvable après exécution")
            continue
        try:
            import pandas as pd
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path)
            elif path.suffix.lower() == ".json":
                df = pd.read_json(path)
            else:
                df = pd.read_parquet(path)
            lignes.append(
                f"- {name} : {table} — {len(df)} lignes, {len(df.columns)} colonnes "
                f"({', '.join(map(str, df.columns[:8]))})"
            )
            if len(df) == 0:
                lignes.append("  ATTENTION : zéro ligne écrite. Un filtre est "
                              "probablement trop strict, ou le `cast` manque.")
        except Exception as exc:
            lignes.append(f"- {name} : {table} — lecture impossible ({type(exc).__name__})")

    if not lignes:
        return ""
    return "\n\nRésultat produit :\n" + "\n".join(lignes)


# ---------------------------------------------------------------------------

def build_server() -> Any:
    kwargs: dict[str, Any] = {
        "name": "hydra-etl",
        "instructions": (
            "Hydra ETL is a declarative ETL engine. A job is a folder holding "
            "four YAML manifests: sources.yaml, transformations.yaml "
            "(optional), destinations.yaml and pipeline.yaml.\n\n"
            "Recommended method: call hydra_list_operations and "
            "hydra_list_connectors first to learn the exact vocabulary, then "
            "write the job with hydra_write_job — it validates before writing "
            "and hands back the errors if anything is wrong. Never run a job "
            "unless the user asked for it.\n\n"
            "Never invent a connector, an operation or an action: if it is "
            "not in the lists, it does not exist."
        ),
    }
    # Champs portés par serverInfo dans le SDK 2.x. Le repli 1.x ne les
    # connaît pas et les refuserait : on ne les passe que s'ils existent.
    _accepted = inspect.signature(MCPServer.__init__).parameters
    for _key, _value in (("title", "Hydra ETL"),
                         ("version", __version__),
                         ("website_url", "https://hydraetl.com")):
        if _key in _accepted:
            kwargs[_key] = _value
    server = MCPServer(**kwargs)

    # -- Découverte du DSL ---------------------------------------------------

    @server.tool(
        description=(
            "List the 18 transformation operations of Hydra ETL with their "
            "required parameters. Call this BEFORE writing a "
            "transformations.yaml: any operation missing from this list does "
            "not exist and will be rejected."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
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
            "Return the full JSON schema of one transformation operation: "
            "every parameter, its type and its default value. Call this when "
            "hydra_list_operations is not enough."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
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
            "List the connector types accepted by the 'type' key of a source "
            "or a destination. Any other type fails at run time: S3, BigQuery "
            "and Snowflake are not supported."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_list_connectors() -> str:
        sch = _spec("connectors.schema.json")
        return ", ".join(sch["enum"])

    @server.tool(
        description=(
            "List the actions usable in a workflow step of type 'action'. "
            "Any other name is rejected: the workflow fails validation and "
            "does not run."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_list_actions() -> str:
        sch = _spec("actions.schema.json")
        return ", ".join(sch["enum"])

    # -- Lecture -------------------------------------------------------------

    @server.tool(
        description=(
            "List the Hydra ETL jobs present in the workspace. A job is a "
            "folder holding a pipeline.yaml. Returns relative paths, usable "
            "as they are in the other tools."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
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
            "Read the manifests of an existing job. Call this before "
            "modifying a job, so you start from its real content instead of "
            "rewriting it from memory."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
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
            "Validate a job with the official Hydra ETL validator: the "
            "structure of the four manifests, and the resolution of "
            "pipeline.from to a declared source and of pipeline.to to a "
            "declared destination. This is the ground truth — if this tool "
            "refuses, the job will not run."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_validate_job(job_path: str) -> str:
        try:
            d = safe_path(job_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        ok, output = _hdrctl("validate", str(d))
        return ("VALIDE\n" if ok else "INVALIDE\n") + output

    @server.tool(
        description=(
            "Write the manifests of a job, AFTER validation. Each manifest "
            "is passed as YAML text. If validation fails, nothing is written "
            "and the errors are returned: fix them and call the tool again. "
            "Writing does not run the job."
        )
    ,
        annotations=_annot(**ECRITURE, title="Writes files, after validation"))
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
            "Run a Hydra ETL job and return the execution log. Only call "
            "this tool if the user explicitly asked for the run: it writes "
            "real data to the destination."
        )
    ,
        annotations=_annot(**EXECUTION, title="Runs the pipeline — writes real data"))
    def hydra_run_job(job_path: str) -> str:
        try:
            d = safe_path(job_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        ok, output = _hdrctl("run", str(d))
        if not ok:
            return "ÉCHEC\n" + output
        return "EXÉCUTION RÉUSSIE\n" + output + _outputs_summary(d)

    @server.tool(
        description=(
            "Explain a Hydra ETL validation error in plain language and "
            "propose the fix. Use this when hydra_validate_job or "
            "hydra_write_job returns a message you cannot interpret."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
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

    # -- Workflows -----------------------------------------------------------

    @server.tool(
        description=(
            "List the workflows in the workspace. A workflow orchestrates "
            "several jobs: dependencies, parallel execution, retries, cron "
            "triggering. Use this as soon as the request chains several jobs."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_list_workflows() -> str:
        base = workspace()
        found = []
        for f in base.rglob("*.yaml"):
            if f.name in JOB_FILES or "_archive" in f.parts or "_backups" in f.parts:
                continue
            try:
                doc = yaml.safe_load(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(doc, dict) and "workflow" in doc:
                found.append(f.relative_to(base).as_posix())
        return "\n".join(sorted(found)) or "Aucun workflow trouvé."

    @server.tool(
        description=(
            "Read an existing workflow.yaml file and return its raw YAML. "
            "Call this before modifying a workflow, so you start from its "
            "real content instead of rewriting it from memory."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_read_workflow(workflow_path: str) -> str:
        try:
            f = safe_path(workflow_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        if not f.is_file():
            return f"Fichier introuvable : {workflow_path}"
        return f.read_text(encoding="utf-8")

    @server.tool(
        description=(
            "Write a workflow, AFTER validation. A step is either "
            "type='job' with the path of a job folder, or type='action'. "
            "`depends_on` is ALWAYS a list: steps with no dependency in "
            "common run in parallel. If validation fails, nothing is "
            "written."
        )
    ,
        annotations=_annot(**ECRITURE, title="Writes files, after validation"))
    def hydra_write_workflow(workflow_path: str, workflow_yaml: str) -> str:
        import shutil
        import tempfile

        try:
            yaml.safe_load(workflow_yaml)
        except Exception as exc:
            return f"REFUSÉ — le YAML est invalide : {exc}"

        tmp = Path(tempfile.mkdtemp(prefix="hydra_mcp_wf_"))
        try:
            candidate = tmp / "workflow.yaml"
            candidate.write_text(workflow_yaml, encoding="utf-8")
            ok, output = _hdrctl("workflow", "validate", str(candidate))
            if not ok:
                return ("REFUSÉ — rien n'a été écrit. Le validateur signale :\n"
                        + output)
            try:
                target = safe_path(workflow_path)
            except ValueError as exc:
                return f"REFUSÉ — {exc}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(workflow_yaml, encoding="utf-8")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        return (f"ÉCRIT : {workflow_path}. Le workflow est valide et n'a pas "
                f"été exécuté.")

    @server.tool(
        description=(
            "Run a workflow and return the trace, step by step. Only call "
            "this tool if the user asked for the run: the jobs it contains "
            "write real data to their destinations."
        )
    ,
        annotations=_annot(**EXECUTION, title="Runs the pipeline — writes real data"))
    def hydra_run_workflow(workflow_path: str) -> str:
        try:
            f = safe_path(workflow_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        ok, output = _hdrctl("workflow", "run", str(f))
        return ("EXÉCUTION RÉUSSIE\n" if ok else "ÉCHEC\n") + output

    # -- Voir les données ----------------------------------------------------

    @server.tool(
        description=(
            "Show the columns and the first rows of a data file (CSV, JSON, "
            "Parquet). Call this BEFORE writing a job, to learn the real "
            "column names instead of guessing them — and AFTER a run, to "
            "check the result."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_preview_data(file_path: str, rows: int = 5) -> str:
        try:
            f = safe_path(file_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        if not f.is_file():
            return f"Fichier introuvable : {file_path}"
        try:
            import pandas as pd
        except ModuleNotFoundError:
            return "pandas est requis pour prévisualiser des données."

        rows = max(1, min(int(rows), 50))
        suffix = f.suffix.lower()
        try:
            if suffix == ".csv":
                df = pd.read_csv(f, nrows=rows)
                total = sum(1 for _ in f.open(encoding="utf-8", errors="replace")) - 1
            elif suffix == ".json":
                df = pd.read_json(f).head(rows)
                total = None
            elif suffix in (".parquet", ".pq"):
                df = pd.read_parquet(f).head(rows)
                total = None
            else:
                return (f"Format non pris en charge : {suffix}. "
                        "Formats lisibles : .csv, .json, .parquet")
        except Exception as exc:
            return f"Lecture impossible : {type(exc).__name__}: {exc}"

        cols = ", ".join(f"{c} ({df[c].dtype})" for c in df.columns)
        head = df.to_string(index=False, max_colwidth=30)
        compte = f"\nLignes au total : {total}" if total is not None else ""
        return (f"Fichier : {file_path}\nColonnes : {cols}{compte}\n\n"
                f"{rows} premières lignes :\n{head}\n\n"
                "Rappel : un CSV ne porte aucun type. Les types ci-dessus sont "
                "déduits par la lecture, pas garantis — place un `cast` avant "
                "toute comparaison numérique.")

    # -- Vérifier la cohérence avec la demande -------------------------------

    @server.tool(
        description=(
            "Check that a job does what the user actually asked for. This "
            "completes hydra_validate_job: that one says whether the YAML is "
            "correct, this one whether the job answers the request. Twelve "
            "deterministic rules: operation requested but missing, numeric "
            "comparison without a `cast`, load mode contradicted, "
            "inconsistent file extension, plaintext secret, unsupported "
            "technology. Call this AFTER writing a job, before presenting "
            "it."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_check_job(user_request: str, job_path: str) -> str:
        from hydra_etl.ai.guards import check

        try:
            d = safe_path(job_path)
        except ValueError as exc:
            return f"REFUSÉ — {exc}"
        if not d.is_dir():
            return f"Dossier introuvable : {job_path}"

        files, docs = {}, {}
        for name in (*JOB_FILES, "workflow.yaml"):
            f = d / name
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8")
            files[name] = text
            try:
                docs[name] = yaml.safe_load(text)
            except Exception:
                docs[name] = None

        alerts = check(user_request, files, docs)
        if not alerts:
            return ("AUCUNE ALERTE — le job paraît conforme à la demande. "
                    "Présente-le à l'utilisateur.")
        return ("ALERTES — à examiner avant de présenter le job :\n"
                + "\n".join(f"- {a}" for a in alerts))

    # -- S'inspirer des jobs existants ---------------------------------------

    @server.tool(
        description=(
            "Find, among real Hydra ETL jobs, the ones closest to the "
            "request, and return their manifests. Call this BEFORE writing "
            "an unusual job: an example that runs beats a reconstruction "
            "from memory."
        )
    ,
        annotations=_annot(**LECTURE, title="Read-only"))
    def hydra_find_example(user_request: str, count: int = 2) -> str:
        from hydra_etl.ai.guards import OP_HINTS, _norm

        if not CORPUS.exists():
            return ("Aucun corpus d'exemples. Générez-le avec "
                    "`python eval/corpus/harvest.py`.")

        besoin = {op for op, hints in OP_HINTS.items()
                  if any(h in _norm(user_request) for h in hints)}

        entries = []
        for line in CORPUS.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            if not e.get("valid") or e.get("expectedInvalid"):
                continue
            ops = set(e.get("features", {}).get("ops", []))
            score = len(besoin & ops) * 10

            # Sans indice d'opération, on retombe sur les mots de la demande :
            # un modèle qui demande « postgres » doit voir un exemple postgres.
            if not besoin:
                blob = json.dumps(e, ensure_ascii=False).lower()
                score = sum(2 for mot in _norm(user_request).split()
                            if len(mot) > 4 and mot in blob)

            # Un job vaut mieux qu'un workflow quand rien n'indique le contraire.
            if e.get("kind") == "job":
                score += 3
            score -= abs(len(ops) - len(besoin))
            entries.append((score, len(json.dumps(e)), e))

        if not entries:
            return "Aucun exemple exploitable dans le corpus."
        entries.sort(key=lambda t: (-t[0], t[1]))   # meilleur score, puis plus court

        count = max(1, min(int(count), 3))
        out = []
        for _, _, e in entries[:count]:
            manifests = "\n".join(f"# {n}\n{c}" for n, c in e["manifests"].items())
            out.append(f"### Exemple : {e['id']}\n{manifests}")
        return "\n\n".join(out)

    return server


def main() -> None:
    """
    Point d'entrée `hydra-mcp`.

    Deux transports, pour deux usages :

    - **stdio** (défaut) — le client démarre le serveur lui-même. C'est le mode
      des clients de bureau : Claude Desktop, Cursor, VS Code. Rien n'écoute
      sur le réseau.
    - **streamable-http** — le serveur écoute, le client s'y connecte. C'est ce
      qu'exigent les clients qui ne lancent pas de processus local, ChatGPT par
      exemple.

    Le mode HTTP n'a AUCUNE authentification : il est prévu pour la machine de
    l'utilisateur ou un tunnel maîtrisé, pas pour une exposition publique. Le
    serveur MCP distant, authentifié et multi-locataire, relève de l'édition
    commerciale.
    """
    import argparse

    ap = argparse.ArgumentParser(
        prog="hydra-mcp",
        description="Hydra ETL MCP server — exposes the engine to an AI agent.")
    ap.add_argument("--transport", choices=["stdio", "streamable-http", "sse"],
                    default="stdio",
                    help="stdio for a desktop client, streamable-http for a "
                         "remote client")
    ap.add_argument("--host", default="127.0.0.1",
                    help="listen address in HTTP mode (default: local only)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--workspace", default="",
                    help="working directory; same as HYDRA_MCP_WORKSPACE")
    args = ap.parse_args()

    if args.workspace:
        os.environ["HYDRA_MCP_WORKSPACE"] = args.workspace

    server = build_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
        return

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"Warning: listening on {args.host} with no authentication. "
              f"Do not expose this port publicly.", file=sys.stderr)
    # Le SDK 2.x ne porte plus host/port dans les réglages : ils se passent
    # au lancement, et sont relayés à l'application ASGI.
    server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
