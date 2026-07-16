"""
workflow/runner.py — Exécuteur de workflows avec DAG et parallélisme.

Algorithme :
  1. Tri topologique (Kahn) → groupes de steps parallèles
  2. Chaque groupe s'exécute via ThreadPoolExecutor
  3. on_failure: fail | skip | continue
  4. Les dépendants d'un step échoué sont marqués skipped

Usage:
    from workflow.parser import load_workflow
    from workflow.runner import WorkflowRunner

    wf = load_workflow("./workflow.yaml")
    result = WorkflowRunner(wf, base_dir="./").run()
    print(result)
"""
from __future__ import annotations

import logging
import time
import uuid
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set


class _ListHandler(logging.Handler):
    """Capture les logs dans une liste en mémoire — attaché à un logger isolé par step."""
    def __init__(self) -> None:
        super().__init__()
        self.records: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def _make_step_logger(step_name: str) -> tuple[logging.Logger, _ListHandler]:
    """
    Crée un logger **isolé** pour un step donné.
    - Nommé de façon unique pour éviter toute collision entre threads parallèles.
    - `propagate=False` : les messages ne remontent PAS au root logger.
      → Aucun risque de contamination croisée entre steps parallèles.
    """
    unique_id = uuid.uuid4().hex[:8]
    step_logger = logging.getLogger(f"hydra.step.{step_name}.{unique_id}")
    step_logger.propagate = False          # isolation totale du root logger
    step_logger.setLevel(logging.DEBUG)

    handler = _ListHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    step_logger.addHandler(handler)

    return step_logger, handler

from workflow.models import WorkflowDef, WorkflowStep, StepResult, WorkflowResult

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """
    Exécute un WorkflowDef en respectant les contraintes depends_on.

    Parallélisme implicite : tous les steps d'un même groupe topologique
    (sans dépendances croisées) s'exécutent en parallèle.
    """

    def __init__(
        self,
        workflow: WorkflowDef,
        base_dir: Optional[Path] = None,
        env: Optional[str] = None,
    ) -> None:
        self.workflow = workflow
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self.env = env

    # -------------------------------------------------------------------------
    # Point d'entrée principal
    # -------------------------------------------------------------------------

    def run(self) -> WorkflowResult:
        """Exécute le workflow et retourne un WorkflowResult."""
        start = time.monotonic()
        step_results: Dict[str, StepResult] = {}
        skipped: Set[str] = set()

        logger.info(f"▶ Workflow '{self.workflow.name}' démarré")

        try:
            groups = self._build_execution_groups()

            for group in groups:
                # Enregistrer les steps skippés avec leur statut
                for s in group:
                    if s.name in skipped:
                        step_results[s.name] = StepResult(
                            step_name=s.name, success=False,
                            duration=0.0, skipped=True,
                            logs=[f"INFO [{s.name}] SKIPPED (dépendance échouée)"],
                        )

                # Ignorer les steps désactivés (enabled=False) — enregistrement silencieux
                for s in group:
                    if not s.enabled and s.name not in skipped:
                        step_results[s.name] = StepResult(
                            step_name=s.name, success=True,
                            duration=0.0, skipped=True,
                            logs=[f"INFO [{s.name}] DISABLED (enabled=false)"],
                        )

                runnable = [s for s in group if s.name not in skipped and s.enabled]

                if not runnable:
                    continue

                # Exécution parallèle si plusieurs steps dans le groupe
                if len(runnable) == 1:
                    sr = self._execute_step(runnable[0])
                    step_results[runnable[0].name] = sr
                else:
                    group_results = self._execute_parallel(runnable)
                    step_results.update(group_results)

                # Gestion des échecs
                for step in runnable:
                    sr = step_results.get(step.name)
                    if sr and not sr.success:
                        if step.on_failure == "fail":
                            self._mark_dependents_skipped(step.name, groups, skipped)
                            duration = time.monotonic() - start
                            logger.error(
                                f"✗ Workflow '{self.workflow.name}' échoué "
                                f"sur step '{step.name}': {sr.error}"
                            )
                            return WorkflowResult(
                                workflow_name=self.workflow.name,
                                success=False,
                                duration=duration,
                                steps=list(step_results.values()),
                                error=f"Step '{step.name}' failed: {sr.error}",
                            )
                        elif step.on_failure == "skip":
                            self._mark_dependents_skipped(step.name, groups, skipped)
                        # on_failure == "continue" → on passe à la suite sans rien faire

            duration = time.monotonic() - start
            all_success = all(sr.success for sr in step_results.values())

            status = "✅ terminé" if all_success else "⚠ terminé avec erreurs"
            logger.info(f"{status} — workflow '{self.workflow.name}' ({duration:.2f}s)")

            return WorkflowResult(
                workflow_name=self.workflow.name,
                success=all_success,
                duration=duration,
                steps=list(step_results.values()),
            )

        except Exception as e:
            duration = time.monotonic() - start
            logger.exception(f"✗ Workflow '{self.workflow.name}' exception inattendue")
            return WorkflowResult(
                workflow_name=self.workflow.name,
                success=False,
                duration=duration,
                steps=list(step_results.values()),
                error=f"{e.__class__.__name__}: {e}",
            )

    # -------------------------------------------------------------------------
    # Tri topologique
    # -------------------------------------------------------------------------

    def _build_execution_groups(self) -> List[List[WorkflowStep]]:
        """
        Algorithme de Kahn : retourne des groupes de steps pouvant
        s'exécuter en parallèle (même niveau topologique).
        """
        steps_by_name: Dict[str, WorkflowStep] = {
            s.name: s for s in self.workflow.steps
        }

        # Valider toutes les références depends_on
        for step in self.workflow.steps:
            for dep in step.depends_on:
                if dep not in steps_by_name:
                    raise ValueError(
                        f"Step '{step.name}' dépend de '{dep}' qui n'existe pas"
                    )

        # Détection de cycles (DFS)
        self._detect_cycles(steps_by_name)

        # Kahn avec groupes
        completed: Set[str] = set()
        remaining: Set[str] = set(steps_by_name.keys())
        groups: List[List[WorkflowStep]] = []

        while remaining:
            ready = [
                steps_by_name[name]
                for name in remaining
                if all(dep in completed for dep in steps_by_name[name].depends_on)
            ]

            if not ready:
                raise ValueError(
                    f"Cycle détecté dans le workflow '{self.workflow.name}' — "
                    f"steps bloqués : {remaining}"
                )

            groups.append(ready)
            for step in ready:
                remaining.remove(step.name)
                completed.add(step.name)

        return groups

    def _detect_cycles(self, steps_by_name: Dict[str, WorkflowStep]) -> None:
        """Détection de cycles par DFS (coloriage blanc/gris/noir)."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {name: WHITE for name in steps_by_name}

        def dfs(name: str) -> None:
            color[name] = GRAY
            for dep in steps_by_name[name].depends_on:
                if dep not in steps_by_name:
                    continue
                if color[dep] == GRAY:
                    raise ValueError(
                        f"Cycle détecté : '{dep}' → ... → '{name}' → '{dep}'"
                    )
                if color[dep] == WHITE:
                    dfs(dep)
            color[name] = BLACK

        for name in steps_by_name:
            if color[name] == WHITE:
                dfs(name)

    # -------------------------------------------------------------------------
    # Exécution des steps
    # -------------------------------------------------------------------------

    def _execute_step(self, step: WorkflowStep) -> StepResult:
        """Exécute un step individuel et retourne son résultat."""
        start = time.monotonic()

        # Logger isolé par step — propagate=False garantit qu'aucun log d'un
        # autre step parallèle ne peut contaminer ce handler (thread-safe).
        step_log, handler = _make_step_logger(step.name)
        step_log.info(f"[{step.name}] START type={step.type}")

        try:
            if step.type == "job":
                result = self._run_job(step, start, step_log)
            elif step.type == "action":
                result = self._run_action(step, start, step_log)
            else:
                raise ValueError(f"Type de step inconnu : '{step.type}'")
            result.logs = handler.records
            return result
        except Exception as e:
            duration = time.monotonic() - start
            step_log.error(f"[{step.name}] FAILED {e.__class__.__name__}: {e}")
            return StepResult(
                step_name=step.name,
                success=False,
                duration=duration,
                error=f"{e.__class__.__name__}: {e}",
                logs=handler.records,
            )
        finally:
            # Nettoyer le logger isolé pour éviter les fuites mémoire
            step_log.removeHandler(handler)
            logging.Logger.manager.loggerDict.pop(step_log.name, None)

    def _run_job(self, step: WorkflowStep, start: float,
                 step_log: logging.Logger) -> StepResult:
        """Exécute un step de type job via JobExecutor."""
        from internal.runner.executor import JobExecutor

        job_path = Path(step.job)  # type: ignore[arg-type]
        if not job_path.is_absolute():
            job_path = self.base_dir / job_path
        job_path = job_path.resolve()

        step_log.info(f"[{step.name}] job_path={job_path}")

        if not job_path.exists():
            raise FileNotFoundError(f"Job directory not found: {job_path}")

        executor = JobExecutor(job_dir=job_path, root_dir=self.base_dir, env=self.env)
        job_result = executor.run()
        duration = time.monotonic() - start

        if job_result.success:
            step_log.info(
                f"[{step.name}] OK rows_out={job_result.rows_out} duration={duration:.3f}s"
            )
        else:
            step_log.error(f"[{step.name}] FAILED {job_result.error}")

        return StepResult(
            step_name=step.name,
            success=job_result.success,
            duration=duration,
            error=job_result.error,
            job_result=job_result,
        )

    def _run_action(self, step: WorkflowStep, start: float,
                    step_log: logging.Logger) -> StepResult:
        """Exécute un step de type action."""
        action = step.action or ""
        params = step.params or {}

        action_handlers = {
            "webhook":    self._action_webhook,
            "log":        self._action_log,
            "bash":       self._action_shell,
            "powershell": self._action_shell,
            "ssh":        self._action_ssh,
            "email":      self._action_email,
        }

        handler_fn = action_handlers.get(action)
        if handler_fn is None:
            step_log.warning(
                f"[{step.name}] Action '{action}' non implémentée — ignorée"
            )
            return StepResult(
                step_name=step.name, success=True, duration=time.monotonic() - start
            )

        return handler_fn(step, params, start, step_log)

    def _action_webhook(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """POST HTTP vers une URL externe."""
        url = params.get("url", "")
        method = params.get("method", "POST").upper()
        body = params.get("body", {})

        if not url:
            raise ValueError(
                f"Action webhook '{step.name}' requiert le paramètre 'url'"
            )

        step_log.info(f"[{step.name}] webhook {method} {url}")
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=30) as resp:
            step_log.info(f"[{step.name}] HTTP {resp.status}")

        return StepResult(
            step_name=step.name,
            success=True,
            duration=time.monotonic() - start,
        )

    def _action_log(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Log un message."""
        message = params.get("message", f"Step '{step.name}' exécuté")
        step_log.info(f"[{step.name}] {message}")
        return StepResult(
            step_name=step.name,
            success=True,
            duration=time.monotonic() - start,
        )

    def _action_shell(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Exécute une commande Bash (Linux/macOS) ou PowerShell (Windows)."""
        import subprocess, sys as _sys

        action  = step.action or ""
        command = params.get("command", "")
        work_dir = params.get("working_dir") or None
        timeout  = int(params.get("timeout", 60))

        if not command:
            raise ValueError(f"Action '{step.name}' : paramètre 'command' requis")

        if action == "bash":
            if _sys.platform == "win32":
                raise RuntimeError("Action Bash non disponible sur Windows")
            shell_args = ["bash", "-c", command]
        else:  # powershell
            if _sys.platform != "win32":
                raise RuntimeError("Action PowerShell non disponible sur Linux/macOS")
            shell_args = ["powershell", "-NonInteractive", "-Command", command]

        step_log.info(f"[{step.name}] {action}: {command[:80]}{'…' if len(command) > 80 else ''}")

        result = subprocess.run(
            shell_args,
            capture_output=True, text=True,
            cwd=work_dir, timeout=timeout,
        )
        for line in (result.stdout + result.stderr).splitlines():
            step_log.info(f"  {line}")

        if result.returncode != 0:
            raise RuntimeError(
                f"Commande terminée avec code {result.returncode}\n{result.stderr[:500]}"
            )

        return StepResult(
            step_name=step.name, success=True,
            duration=time.monotonic() - start,
        )

    def _action_ssh(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Exécute une commande distante via SSH (paramiko)."""
        host     = params.get("host", "")
        port     = int(params.get("port", 22))
        username = params.get("username", "")
        password = params.get("password") or None
        key_path = params.get("key_path") or None
        command  = params.get("command", "")
        timeout  = int(params.get("timeout", 30))

        if not host or not username or not command:
            raise ValueError(f"Action SSH '{step.name}' : 'host', 'username' et 'command' requis")

        try:
            import paramiko  # type: ignore
        except ImportError:
            raise RuntimeError(
                "Dépendance manquante : installez paramiko → pip install paramiko"
            )

        step_log.info(f"[{step.name}] SSH {username}@{host}:{port} → {command[:60]}")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = dict(hostname=host, port=port, username=username, timeout=timeout)
        if key_path:
            connect_kwargs["key_filename"] = key_path
        elif password:
            connect_kwargs["password"] = password

        try:
            client.connect(**connect_kwargs)
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            rc  = stdout.channel.recv_exit_status()
        finally:
            client.close()

        for line in (out + err).splitlines():
            step_log.info(f"  {line}")

        if rc != 0:
            raise RuntimeError(f"Commande SSH terminée avec code {rc}\n{err[:500]}")

        return StepResult(
            step_name=step.name, success=True,
            duration=time.monotonic() - start,
        )

    def _action_email(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Envoie un email via SMTP (Mailhog par défaut, ou tout serveur SMTP)."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = params.get("smtp_host", "localhost")
        smtp_port = int(params.get("smtp_port", 1025))
        from_addr = params.get("from_addr", "hydra@localhost")
        to_addr   = params.get("to", "")
        subject   = params.get("subject", "(sans objet)")
        body      = params.get("body", "")
        username  = params.get("username") or None
        password  = params.get("password") or None
        use_tls   = str(params.get("use_tls", "false")).lower() == "true"

        if not to_addr:
            raise ValueError(f"Action email '{step.name}' : paramètre 'to' requis")

        step_log.info(f"[{step.name}] email → {to_addr} via {smtp_host}:{smtp_port}")

        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())

        step_log.info(f"[{step.name}] email envoyé ✓")
        return StepResult(
            step_name=step.name, success=True,
            duration=time.monotonic() - start,
        )

    # -------------------------------------------------------------------------
    # Parallélisme
    # -------------------------------------------------------------------------

    def _execute_parallel(
        self, steps: List[WorkflowStep]
    ) -> Dict[str, StepResult]:
        """Exécute une liste de steps en parallèle."""
        results: Dict[str, StepResult] = {}
        logger.info(
            f"  ⚡ Parallèle : {[s.name for s in steps]}"
        )

        with ThreadPoolExecutor(max_workers=len(steps)) as executor:
            futures = {
                executor.submit(self._execute_step, step): step
                for step in steps
            }
            for future in as_completed(futures):
                step = futures[future]
                try:
                    results[step.name] = future.result()
                except Exception as e:
                    results[step.name] = StepResult(
                        step_name=step.name,
                        success=False,
                        duration=0.0,
                        error=f"{e.__class__.__name__}: {e}",
                    )

        return results

    # -------------------------------------------------------------------------
    # Gestion des dépendants skippés
    # -------------------------------------------------------------------------

    def _mark_dependents_skipped(
        self,
        failed_step: str,
        groups: List[List[WorkflowStep]],
        skipped: Set[str],
    ) -> None:
        """Marque transitivement tous les steps dépendants comme skipped."""
        all_steps = [s for group in groups for s in group]

        # Carte : step → ses dépendants directs
        dependents: Dict[str, Set[str]] = {s.name: set() for s in all_steps}
        for step in all_steps:
            for dep in step.depends_on:
                if dep in dependents:
                    dependents[dep].add(step.name)

        # BFS transitif
        queue = [failed_step]
        while queue:
            current = queue.pop()
            for dep_name in dependents.get(current, set()):
                if dep_name not in skipped:
                    skipped.add(dep_name)
                    logger.warning(
                        f"  ⏭ Step '{dep_name}' skipped "
                        f"(dépend de '{failed_step}')"
                    )
                    queue.append(dep_name)
