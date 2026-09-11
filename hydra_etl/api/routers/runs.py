"""
api/routers/runs.py -- Execution de workflows et suivi des runs.

POST /api/runs           -> lance un workflow complet
POST /api/runs/inline    -> lance un job depuis contenu HDR inline
POST /api/runs/step      -> lance jusqu\'a un step precis (debug)
GET  /api/runs           -> liste les runs (volatile, en memoire)
GET  /api/runs/{run_id}  -> statut + resultats d\'un run
GET  /api/runs/{run_id}/logs -> logs bruts du run
"""
from __future__ import annotations

import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from hydra_etl.api import store
from hydra_etl.api.models import MessageResponse, RunRequest, RunResponse, InlineJobRequest, ActionNodeRequest, PeekRequest

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Execution asynchrone (thread background) -- Workflow complet
# ---------------------------------------------------------------------------

def _execute_workflow(run_id: str, workflow_path: str, step: Optional[str], env: Optional[str] = None) -> None:
    """Execute le workflow dans un thread -- met a jour le store a la fin."""
    from hydra_etl.workflow.parser import load_workflow
    from hydra_etl.workflow.runner import WorkflowRunner

    run = store.get_run(run_id)
    if not run:
        return

    wf_path_str = run.workflow_path or workflow_path
    trig = run.trigger or "manual"

    run = RunResponse(
        run_id=run.run_id,
        workflow_name=run.workflow_name,
        workflow_path=wf_path_str,
        status="running",
        started_at=run.started_at,
        trigger=trig,
    )
    store.save_run(run)

    try:
        wf_path = Path(workflow_path)
        base_dir = wf_path.parent if wf_path.is_file() else wf_path
        wf_def = load_workflow(str(wf_path) if wf_path.is_file() else str(wf_path / "workflow.yaml"))

        runner = WorkflowRunner(wf_def, base_dir=base_dir, env=env)

        if step:
            step_names = [s.name for s in wf_def.steps]
            if step not in step_names:
                raise ValueError(f"Step \'{step}\' introuvable dans le workflow")
            cut = step_names.index(step) + 1
            wf_def.steps = wf_def.steps[:cut]

        # Progression live : persiste l'avancement apres chaque groupe de steps,
        # pour que le polling du Studio voie les steps se terminer un a un
        # (au lieu de tout d'un bloc a la fin). N'altere pas l'execution.
        from hydra_etl.workflow.models import WorkflowResult as _WFR

        def _progress(partial_steps) -> None:
            snapshot = _WFR(
                workflow_name=run.workflow_name,
                success=False,
                duration=0.0,
                steps=partial_steps,
            ).to_dict()["steps"]
            store.save_run(RunResponse(
                run_id=run_id,
                workflow_name=run.workflow_name,
                workflow_path=wf_path_str,
                status="running",
                started_at=run.started_at,
                steps=snapshot,
                trigger=trig,
            ))

        result = runner.run(on_progress=_progress)

        run = RunResponse(
            run_id=run_id,
            workflow_name=result.workflow_name,
            workflow_path=wf_path_str,
            status="success" if result.success else "failed",
            started_at=run.started_at,
            finished_at=_now(),
            duration=result.duration,
            error=result.error,
            steps=result.to_dict()["steps"],
            trigger=trig,
        )
    except Exception as exc:
        run = RunResponse(
            run_id=run_id,
            workflow_name=run.workflow_name,
            workflow_path=wf_path_str,
            status="failed",
            started_at=run.started_at,
            finished_at=_now(),
            error=str(exc),
            trigger=trig,
        )

    store.save_run(run)


# ---------------------------------------------------------------------------
# Execution inline d\'un job HDR (sans fichier sur disk)
# ---------------------------------------------------------------------------

def _resolve_paths_in_section(section: dict, base: "Path") -> dict:
    import copy
    from pathlib import Path as _Path

    resolved = copy.deepcopy(section)
    for _name, connector in resolved.items():
        if not isinstance(connector, dict):
            continue
        conn = connector.get("connection", {})
        if not isinstance(conn, dict):
            continue
        for field in ("path", "file"):
            val = conn.get(field)
            if val and not _Path(val).is_absolute():
                conn[field] = str((_Path(str(base)) / val).resolve())
    return resolved


def _execute_inline_job(run_id: str, hdr_content: str, job_name: str, work_dir: Optional[str], preview_up_to: Optional[int] = None) -> None:
    """Convertit un .hdr en job temporaire et l\'execute via JobExecutor."""
    import shutil
    import tempfile

    import yaml
    from hydra_etl.internal.runner.executor import JobExecutor

    run = store.get_run(run_id)
    if not run:
        return

    run = RunResponse(
        run_id=run.run_id,
        workflow_name=job_name,
        status="running",
        started_at=run.started_at,
    )
    store.save_run(run)

    tmp_dir = None
    try:
        doc = yaml.safe_load(hdr_content)
        if not doc or "job" not in doc:
            raise ValueError("Format HDR invalide : cle \'job:\' attendue")

        job = doc["job"]
        effective_name = job.get("name", job_name)

        sources_raw = job.get("sources", {})
        dests_raw   = job.get("destinations", {})
        if work_dir:
            _base = Path(work_dir)
            sources_raw = _resolve_paths_in_section(sources_raw, _base)
            dests_raw   = _resolve_paths_in_section(dests_raw,   _base)

        sources_doc = {"version": "1.0", "sources": sources_raw}
        dests_doc   = {"version": "1.0", "destinations": dests_raw}
        pipe_raw    = job.get("pipeline", {})
        pipeline_doc = {
            "version": "1.0",
            "pipeline": {
                "name": effective_name,
                "from": pipe_raw.get("from", ""),
                "to":   pipe_raw.get("to",   ""),
            },
        }
        if job.get("transformations"):
            pipeline_doc["pipeline"]["transformations"] = "transformations"

        tmp_dir = Path(tempfile.mkdtemp(prefix="hydra_inline_"))

        with open(tmp_dir / "sources.yaml", "w", encoding="utf-8") as f:
            yaml.dump(sources_doc, f, allow_unicode=True, default_flow_style=False)
        with open(tmp_dir / "destinations.yaml", "w", encoding="utf-8") as f:
            yaml.dump(dests_doc, f, allow_unicode=True, default_flow_style=False)
        with open(tmp_dir / "pipeline.yaml", "w", encoding="utf-8") as f:
            yaml.dump(pipeline_doc, f, allow_unicode=True, default_flow_style=False)

        raw_transforms = job.get("transformations") or []
        if preview_up_to is not None:
            # transformations peut etre une liste OU un dict ordonne (selon le HDR)
            if isinstance(raw_transforms, dict):
                raw_transforms = dict(list(raw_transforms.items())[: preview_up_to + 1])
            else:
                raw_transforms = raw_transforms[: preview_up_to + 1]
            dests_raw = {"preview_sink": {"type": "csv", "path": str(tmp_dir / "_preview_sink.csv")}}
            dests_doc = {"version": "1.0", "destinations": dests_raw}
            pipe_raw["to"] = "preview_sink"
            pipeline_doc["pipeline"]["to"] = "preview_sink"
            with open(tmp_dir / "destinations.yaml", "w", encoding="utf-8") as f:
                yaml.dump(dests_doc, f, allow_unicode=True, default_flow_style=False)

        if raw_transforms:
            pipeline_doc["pipeline"]["transformations"] = "transformations"
            transforms_doc = {"version": "1.0", "transformations": raw_transforms}
            with open(tmp_dir / "transformations.yaml", "w", encoding="utf-8") as f:
                yaml.dump(transforms_doc, f, allow_unicode=True, default_flow_style=False)
        else:
            pipeline_doc["pipeline"].pop("transformations", None)
        with open(tmp_dir / "pipeline.yaml", "w", encoding="utf-8") as f:
            yaml.dump(pipeline_doc, f, allow_unicode=True, default_flow_style=False)

        root = Path(work_dir) if work_dir else tmp_dir
        executor = JobExecutor(
            job_dir=tmp_dir,
            root_dir=root,
            path_base=Path(work_dir) if work_dir else None,
        )
        result = executor.run()

        run = RunResponse(
            run_id=run_id,
            workflow_name=effective_name,
            status="success" if result.success else "failed",
            started_at=run.started_at,
            finished_at=_now(),
            duration=result.duration,
            error=result.error,
            steps=[{
                "step_name":      effective_name,
                "success":        result.success,
                "duration":       result.duration,
                "rows_in":        result.rows_in,
                "rows_out":       result.rows_out,
                "error":          result.error,
                "logs":           [],
                "output_sample":  result.output_sample,
                "output_columns": result.output_columns,
            }],
        )

    except Exception as exc:
        run = RunResponse(
            run_id=run_id,
            workflow_name=job_name,
            status="failed",
            started_at=run.started_at,
            finished_at=_now(),
            error=str(exc),
        )
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    store.save_run(run)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=RunResponse, status_code=202)
def run_workflow(body: RunRequest, background_tasks: BackgroundTasks):
    """Lance l\'execution d\'un workflow (asynchrone)."""
    wf_path = Path(body.workflow_path)
    if not wf_path.exists():
        raise HTTPException(status_code=404, detail=f"Chemin introuvable : {body.workflow_path}")

    wf_name = wf_path.stem if wf_path.is_file() else wf_path.name

    run_id = str(uuid.uuid4())[:8]
    run = RunResponse(
        run_id=run_id,
        workflow_name=wf_name,
        workflow_path=str(wf_path.resolve()),
        status="pending",
        started_at=_now(),
    )
    store.save_run(run)
    background_tasks.add_task(_execute_workflow, run_id, str(wf_path), body.step, body.env)
    return run


@router.post("/inline", response_model=RunResponse, status_code=202)
def run_inline_job(body: InlineJobRequest, background_tasks: BackgroundTasks):
    """Execute un job HDR passe directement en JSON (sans fichier sur disk)."""
    if not body.hdr_content.strip():
        raise HTTPException(status_code=400, detail="hdr_content ne peut pas etre vide")

    job_name = body.job_name or "inline_job"
    run_id   = str(uuid.uuid4())[:8]
    run      = RunResponse(
        run_id=run_id,
        workflow_name=job_name,
        status="pending",
        started_at=_now(),
    )
    store.save_run(run)
    background_tasks.add_task(_execute_inline_job, run_id, body.hdr_content, job_name, body.work_dir, body.preview_up_to)
    return run


@router.post("/step", response_model=RunResponse, status_code=202)
def run_workflow_step(body: RunRequest, background_tasks: BackgroundTasks):
    """Lance le workflow jusqu\'au step indique dans body.step."""
    if not body.step:
        raise HTTPException(status_code=400, detail="Le champ \'step\' est requis pour /runs/step")
    return run_workflow(body, background_tasks)


# ---------------------------------------------------------------------------
# Endpoints GET
# ---------------------------------------------------------------------------

@router.get("", response_model=list)
def list_runs(workflow_name: Optional[str] = None):
    runs = store.list_runs()
    if workflow_name:
        runs = [r for r in runs if r.workflow_name == workflow_name]
    return runs


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} introuvable")
    return run


@router.get("/{run_id}/logs", response_model=RunResponse)
def get_run_logs(run_id: str):
    return get_run(run_id)


# ---------------------------------------------------------------------------
# Endpoint POST /inline/action
# ---------------------------------------------------------------------------

@router.post("/inline/action", response_model=RunResponse, status_code=202)
def run_inline_action(body: ActionNodeRequest, background_tasks: BackgroundTasks):
    """Lance un noeud action (bash, powershell, ssh) en background."""
    run_id = str(uuid.uuid4())
    run    = RunResponse(
        run_id=run_id,
        workflow_name=body.job_name or body.node_type,
        status="pending",
        started_at=_now(),
    )
    store.save_run(run)
    background_tasks.add_task(
        _execute_action_node,
        run_id,
        body.node_type,
        body.command,
        body.working_dir,
        body.timeout or 60,
        body.job_name or body.node_type,
        body.params,
    )
    return run


# ---------------------------------------------------------------------------
# Endpoint POST /peek -- lecture directe du top N d'une destination (sans re-run)
# ---------------------------------------------------------------------------

@router.post("/peek")
def peek_destination(body: PeekRequest):
    """Lit les N premieres lignes d'une destination (fichier ou base) directement,
    sans rejouer le pipeline. Renvoie {columns, rows, error}."""
    import json as _json
    d = body.dest or {}
    ctype = str(d.get("type") or "").strip().lower()
    limit = max(1, min(1000, int(body.limit or 10)))

    def _resolve(path_str: str) -> Path:
        p = Path(path_str)
        if not p.is_absolute() and body.work_dir:
            p = Path(body.work_dir) / path_str
        return p

    try:
        if ctype in ("csv", "json", "parquet"):
            import pandas as pd
            raw_path = d.get("path") or d.get("table") or ""
            if not raw_path:
                return {"columns": [], "rows": [], "error": "Chemin de destination manquant."}
            p = _resolve(str(raw_path))
            if not p.exists():
                return {"columns": [], "rows": [], "error": f"Fichier destination introuvable : {p}"}
            if ctype == "csv":
                sep = d.get("delimiter") or ","
                df = pd.read_csv(p, nrows=limit, sep=sep)
            elif ctype == "json":
                df = pd.read_json(p).head(limit)
            else:
                df = pd.read_parquet(p).head(limit)
            df = df.head(limit)
            cols = [str(c) for c in df.columns]
            rows = _json.loads(df.to_json(orient="records", date_format="iso"))
            return {"columns": cols, "rows": rows, "error": None}

        # DB / autres : via le connector registry
        from hydra_etl.internal.connector.registry import build_connector
        config = {"type": ctype}
        if d.get("connection"):
            config["connection"] = d["connection"]
        conn = build_connector(name="peek", config=config)
        table = d.get("table") or d.get("collection")
        rows = []
        for batch in conn.extract_batches(table=table, batch_size=limit, query=None):
            rows.extend(batch)
            if len(rows) >= limit:
                break
        rows = rows[:limit]
        cols = list(rows[0].keys()) if rows else []
        return {"columns": cols, "rows": rows, "error": None}
    except Exception as exc:
        return {"columns": [], "rows": [], "error": f"{exc.__class__.__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Execution d\'un noeud action (bash / powershell / ssh)
# ---------------------------------------------------------------------------

def _execute_action_node(
    run_id: str,
    node_type: str,
    command: str,
    working_dir: Optional[str],
    timeout: int,
    job_name: str,
    params: Optional[dict] = None,
) -> None:
    """Execute une commande shell et stocke stdout dans output_text."""
    import subprocess

    run = store.get_run(run_id)
    if not run:
        return

    run = RunResponse(
        run_id=run.run_id,
        workflow_name=job_name,
        status="running",
        started_at=run.started_at,
    )
    store.save_run(run)

    t0 = _now()
    output_text = ""
    success = False
    error = None

    try:
        is_windows = sys.platform == "win32"

        if node_type == "action_powershell" and not is_windows:
            raise ValueError("Le noeud PowerShell n\'est pas disponible sur Linux/macOS. Utilisez le noeud Bash.")
        if node_type == "action_bash" and is_windows:
            raise ValueError("Le noeud Bash n\'est pas disponible sur Windows. Utilisez le noeud PowerShell.")

        if node_type == "action_powershell":
            args = ["powershell.exe", "-NonInteractive", "-Command", command]
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=working_dir or None)
            output_text = proc.stdout
            if proc.returncode != 0:
                output_text += ("\n" if output_text else "") + proc.stderr
            success = proc.returncode == 0
            error   = proc.stderr.strip() if not success else None

        elif node_type == "action_bash":
            args = ["bash", "-c", command]
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=working_dir or None)
            output_text = proc.stdout
            if proc.returncode != 0:
                output_text += ("\n" if output_text else "") + proc.stderr
            success = proc.returncode == 0
            error   = proc.stderr.strip() if not success else None

        elif node_type == "action_python":
            import tempfile, os as _os

            # Interpréteur : python3 sur Linux/macOS, py sur Windows
            interpreter = "py" if is_windows else "python3"

            p         = params or {}
            file_path = p.get("file_path", "").strip()

            if file_path:
                # Mode fichier — exécuter directement le .py existant
                if not _os.path.isfile(file_path):
                    raise ValueError(f"Fichier introuvable : {file_path}")
                proc = subprocess.run(
                    [interpreter, file_path],
                    capture_output=True, text=True,
                    timeout=timeout, cwd=working_dir or None,
                )
                tmp_path = None
            else:
                # Mode inline — écrire dans un fichier temporaire (indentation préservée)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(command)
                    tmp_path = tmp.name
                try:
                    proc = subprocess.run(
                        [interpreter, tmp_path],
                        capture_output=True, text=True,
                        timeout=timeout, cwd=working_dir or None,
                    )
                finally:
                    _os.unlink(tmp_path)

            output_text = proc.stdout
            if proc.returncode != 0:
                output_text += ("\n" if output_text else "") + proc.stderr
            success = proc.returncode == 0
            error   = proc.stderr.strip() if not success else None

        elif node_type == "action_ssh":
            try:
                import paramiko
            except ImportError:
                raise ValueError("paramiko non installe. Lancez : pip install paramiko")

            p        = params or {}
            host     = p.get("host", "").strip()
            username = p.get("username", "").strip()
            password = p.get("password", "").strip() or None
            key_path = p.get("key_path", "").strip() or None
            port     = int(p.get("port", 22) or 22)

            if not host:
                raise ValueError("SSH : le champ \'host\' est requis.")
            if not username:
                raise ValueError("SSH : le champ \'username\' est requis.")

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict = dict(hostname=host, port=port, username=username, timeout=timeout)
            if key_path:
                connect_kwargs["key_filename"] = key_path
            elif password:
                connect_kwargs["password"] = password

            client.connect(**connect_kwargs)
            _, stdout_f, stderr_f = client.exec_command(command, timeout=timeout)
            exit_code  = stdout_f.channel.recv_exit_status()
            stdout_str = stdout_f.read().decode("utf-8", errors="replace")
            stderr_str = stderr_f.read().decode("utf-8", errors="replace")
            client.close()

            output_text = stdout_str
            if exit_code != 0:
                output_text += ("\n" if output_text else "") + stderr_str
            success = exit_code == 0
            error   = stderr_str.strip() if not success else None

        elif node_type == "action_webhook":
            import json as _json
            import urllib.request as _urllib

            p       = params or {}
            url     = command  # command contient l'URL
            method  = p.get("method", "POST").upper()
            raw_body    = p.get("body", "").strip()
            raw_headers = p.get("headers", "").strip()

            # Parser les headers JSON optionnels
            extra_headers: dict = {}
            if raw_headers:
                try:
                    extra_headers = _json.loads(raw_headers)
                except Exception:
                    raise ValueError(f"Headers JSON invalide : {raw_headers}")

            # Encoder le body
            body_bytes: bytes | None = None
            if raw_body:
                try:
                    _json.loads(raw_body)  # validation
                except Exception:
                    raise ValueError(f"Body JSON invalide : {raw_body}")
                body_bytes = raw_body.encode("utf-8")
                extra_headers.setdefault("Content-Type", "application/json")

            req = _urllib.Request(url, data=body_bytes, method=method)
            for k, v in extra_headers.items():
                req.add_header(k, v)

            with _urllib.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                resp_body   = resp.read().decode("utf-8", errors="replace")

            success     = 200 <= status_code < 300

            output_text = f"HTTP {status_code}\n\n{resp_body}"
            error       = f"HTTP {status_code}" if not success else None

        else:
            raise ValueError(f"Type de noeud action inconnu : {node_type}")

        from datetime import datetime as _dt
        t1  = _now()
        dur = (_dt.fromisoformat(t1) - _dt.fromisoformat(t0)).total_seconds()

        run = RunResponse(
            run_id=run_id,
            workflow_name=job_name,
            status="success" if success else "failed",
            started_at=t0,
            finished_at=t1,
            duration=dur,
            error=error,
            steps=[{
                "step_name":      job_name,
                "success":        success,
                "duration":       dur,
                "rows_in":        None,
                "rows_out":       None,
                "error":          error,
                "logs":           [],
                "output_text":    output_text,
                "output_sample":  None,
                "output_columns": None,
            }],
        )

    except subprocess.TimeoutExpired:
        run = RunResponse(
            run_id=run_id,
            workflow_name=job_name,
            status="failed",
            started_at=t0,
            finished_at=_now(),
            error=f"Timeout ({timeout}s) depasse",
        )
    except Exception as exc:
        run = RunResponse(
            run_id=run_id,
            workflow_name=job_name,
            status="failed",
            started_at=t0,
            finished_at=_now(),
            error=str(exc),
        )

    store.save_run(run)
