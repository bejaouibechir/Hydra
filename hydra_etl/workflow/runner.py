"""
workflow/runner.py — Exécuteur de workflows avec DAG et parallélisme.

Algorithme :
  1. Tri topologique (Kahn) → groupes de steps parallèles
  2. Chaque groupe s'exécute via ThreadPoolExecutor
  3. on_failure: fail | skip | continue
  4. Les dépendants d'un step échoué sont marqués skipped

Usage:
    from hydra_etl.workflow.parser import load_workflow
    from hydra_etl.workflow.runner import WorkflowRunner

    wf = load_workflow("./workflow.yaml")
    result = WorkflowRunner(wf, base_dir="./").run()
    print(result)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class _ListHandler(logging.Handler):
    """Capture les logs dans une liste en mémoire — attaché à un logger isolé par step."""
    def __init__(self) -> None:
        super().__init__()
        self.records: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


class _JobLogCapture(logging.Handler):
    """Capture les logs INTERNES d'un job (executor, connecteurs, engines)
    émis dans le thread courant, et les reroute vers le logger du step.
    Filtré par thread -> les jobs parallèles ne se contaminent pas."""

    def __init__(self, step_log: logging.Logger, thread_id: int) -> None:
        super().__init__(logging.INFO)
        self._step_log = step_log
        self._thread_id = thread_id

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self._thread_id:
            return
        if not record.name.startswith(("hydra_etl.internal", "hydra_etl.plugins", "hydra_etl.etl", "internal", "plugins", "etl")):
            return
        try:
            self._step_log.log(record.levelno, f"  [job] {record.getMessage()}")
        except Exception:
            pass


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

from hydra_etl.workflow.models import WorkflowDef, WorkflowStep, StepResult, WorkflowResult

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
        # Paramètres runtime MUTABLES, partagés entre tous les steps d'un run.
        # Alimentés par les actions set_param / assign_param. Protégés par un
        # lock car les groupes de steps peuvent s'exécuter en parallèle.
        self.runtime_params: Dict[str, Any] = {}
        self._params_lock = threading.Lock()
        self._project_params_cache: Optional[Dict[str, Any]] = None

    # -------------------------------------------------------------------------
    # Point d'entrée principal
    # -------------------------------------------------------------------------

    def run(self, on_progress=None) -> WorkflowResult:
        """Exécute le workflow et retourne un WorkflowResult.

        on_progress : callback optionnel appelé après chaque groupe topologique
        avec la liste partielle des StepResult courants. Permet à l'appelant
        (API) de persister l'avancement en temps réel (progression live des runs)
        sans changer la logique d'exécution. Toute exception du callback est
        avalée pour ne jamais compromettre le run.
        """
        start = time.monotonic()
        step_results: Dict[str, StepResult] = {}
        skipped: Set[str] = set()

        def _emit() -> None:
            if on_progress:
                try:
                    on_progress(list(step_results.values()))
                except Exception:
                    pass

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

                # Garde conditionnelle `when` : step exécuté seulement si l'expression
                # est vraie. Faux -> SKIPPÉ (+ dépendants en cascade). Les paramètres
                # runtime posés par un nœud Condition en amont sont déjà disponibles.
                gated: List[WorkflowStep] = []
                for s in runnable:
                    if s.when:
                        try:
                            passed = self._eval_when(s.when)
                        except Exception as ex:
                            step_results[s.name] = StepResult(
                                step_name=s.name, success=False, duration=0.0,
                                error=f"when invalide: {ex}",
                                logs=[f"ERROR [{s.name}] garde 'when' invalide: {ex}"],
                            )
                            self._mark_dependents_skipped(s.name, groups, skipped)
                            continue
                        if not passed:
                            step_results[s.name] = StepResult(
                                step_name=s.name, success=True, duration=0.0, skipped=True,
                                logs=[f"INFO [{s.name}] SKIPPED (when=false: {s.when})"],
                            )
                            self._mark_dependents_skipped(s.name, groups, skipped)
                            continue
                    gated.append(s)
                runnable = gated

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

                # Progression live : groupe terminé → notifier l'appelant
                _emit()

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
        """Exécute un step avec re-tentatives (Retry-scope) — enveloppe _execute_step_once."""
        policy = step.retry
        max_retries = policy.max if policy else 0
        delay = policy.delay if policy else 0.0
        backoff = policy.backoff if policy else "fixed"

        accumulated: List[str] = []
        attempt = 0
        while True:
            sr = self._execute_step_once(step)
            accumulated.extend(sr.logs)
            if sr.success or attempt >= max_retries:
                if attempt > 0:
                    verb = "réussi" if sr.success else "abandonné"
                    accumulated.append(f"INFO [{step.name}] {verb} après {attempt} re-tentative(s)")
                sr.logs = accumulated
                return sr
            attempt += 1
            wait = delay * (2 ** (attempt - 1)) if backoff == "exponential" else delay
            accumulated.append(
                f"WARNING [{step.name}] échec, re-tentative {attempt}/{max_retries}"
                + (f" dans {wait:.0f}s" if wait > 0 else "")
            )
            if wait > 0:
                time.sleep(wait)

    def _execute_step_once(self, step: WorkflowStep) -> StepResult:
        """Exécute un step individuel (une seule tentative) et retourne son résultat."""
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

    @staticmethod
    def _precheck_job_configured(job_path: Path, step_name: str) -> None:
        """Vérification amont conviviale : un job requiert une source ET une
        destination configurées (table / query / collection non vides).
        Évite l'erreur Pydantic brute quand le job est un squelette vide
        (ex. un job créé dans Studio sans configurer sa source)."""
        import yaml as _yaml

        def _has_target(path: Path, root_key: str, sub_key: str) -> bool:
            f = path / f"{root_key}.yaml"
            if not f.exists():
                return True  # laissons JobExecutor gérer les fichiers manquants
            try:
                data = _yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                return True  # YAML illisible -> erreur détaillée par JobExecutor
            entries = data.get(root_key) or {}
            if not isinstance(entries, dict) or not entries:
                return False
            for cfg in entries.values():
                block = (cfg or {}).get(sub_key) or {}
                for key in ("table", "query", "collection"):
                    v = block.get(key)
                    if isinstance(v, str) and v.strip():
                        return True
                    if v not in (None, ""):
                        return True
            return False

        missing = []
        if not _has_target(job_path, "sources", "extract"):
            missing.append("source (fichier/table/query vide)")
        if not _has_target(job_path, "destinations", "load"):
            missing.append("destination (fichier/table vide)")
        if missing:
            raise ValueError(
                f"Job '{job_path.name}' non configuré : {' et '.join(missing)}. "
                f"Un job requiert une source et une destination configurées — "
                f"ouvrez le job dans Studio et renseignez ces champs. "
                f"(Pour une simple action log/script, utilisez un nœud Action "
                f"sur le canvas workflow, pas un job.)"
            )

    def _run_job(self, step: WorkflowStep, start: float,
                 step_log: logging.Logger) -> StepResult:
        """Exécute un step de type job via JobExecutor."""
        from hydra_etl.internal.runner.executor import JobExecutor

        job_path = Path(step.job)  # type: ignore[arg-type]
        if not job_path.is_absolute():
            job_path = self.base_dir / job_path
        job_path = job_path.resolve()

        step_log.info(f"[{step.name}] job_path={job_path}")

        if not job_path.exists():
            raise FileNotFoundError(f"Job directory not found: {job_path}")

        self._precheck_job_configured(job_path, step.name)

        # Propage les paramètres runtime (set_param / assign_param) au job,
        # comme couche de précédence maximale (équivalent --param). Le job peut
        # ainsi résoudre {{ param:X }} avec les valeurs définies dans le workflow.
        with self._params_lock:
            runtime_snapshot = dict(self.runtime_params)
        executor = JobExecutor(
            job_dir=job_path, root_dir=self.base_dir, env=self.env,
            params=runtime_snapshot,
        )
        # Détails internes du job (env, connecteurs, scripts...) -> log du step
        capture = _JobLogCapture(step_log, threading.get_ident())
        root_logger = logging.getLogger()
        root_logger.addHandler(capture)
        prev_level = root_logger.level
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)
        try:
            job_result = executor.run()
        finally:
            root_logger.removeHandler(capture)
            root_logger.setLevel(prev_level)
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

        # Résout {{ param:NAME }} (store runtime) et {{ env:NAME }} dans les
        # params AVANT exécution — permet à log/webhook/bash/... d'utiliser les
        # paramètres créés par set_param / assign_param.
        try:
            params = self._resolve_action_params(step.params or {})
        except Exception as exc:
            return StepResult(
                step_name=step.name, success=False,
                duration=time.monotonic() - start,
                error=f"{exc.__class__.__name__}: {exc}",
            )

        action_handlers = {
            "webhook":    self._action_webhook,
            "log":        self._action_log,
            "delay":      self._action_delay,
            "condition":  self._action_condition,
            "bash":       self._action_shell,
            "powershell": self._action_shell,
            "ssh":        self._action_ssh,
            "email":      self._action_email,
            "python":       self._action_python,
            "set_param":    self._action_set_param,
            "assign_param": self._action_assign_param,
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

    def _resolve_action_params(self, params: dict) -> dict:
        """Résout les placeholders {{ param:NAME }} / {{ env:NAME }} dans les
        valeurs des params d'action, à partir des paramètres runtime courants.
        Un placeholder seul préserve le type ; un paramètre inconnu lève une
        erreur claire (fail-fast / débogage)."""
        from hydra_etl.internal.config.parameters import ParameterResolver
        merged = {**self._project_params(), **self._runtime_snapshot()}
        resolver = ParameterResolver(
            params=merged, env=dict(os.environ),
            strict=False, strict_params=True,
        )
        return resolver.resolve(params)

    def _runtime_snapshot(self) -> Dict[str, Any]:
        with self._params_lock:
            return dict(self.runtime_params)

    def _project_params(self) -> Dict[str, Any]:
        """Paramètres PROJET (parameters.yaml + environments/<env>.yaml de
        base_dir) — mêmes fichiers que ceux lus par JobExecutor. Ils forment la
        couche de précédence FAIBLE sous les paramètres runtime, afin que les
        actions du workflow (log, shell, webhook...) résolvent {{ param:X }}
        déclaré au niveau projet, exactement comme les jobs."""
        if self._project_params_cache is not None:
            return self._project_params_cache
        import yaml as _yaml
        from hydra_etl.internal.config.parameters import build_effective

        def _block(path: Path) -> Dict[str, Any]:
            if not path.exists():
                return {}
            try:
                raw = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                return {}
            try:
                data = _yaml.safe_load(raw) or {}
            except Exception:
                return {}
            if isinstance(data, dict):
                block = data.get("parameters", data)
                return block if isinstance(block, dict) else {}
            return {}

        declarations = _block(self.base_dir / "parameters.yaml")
        env_values = (
            _block(self.base_dir / "environments" / f"{self.env}.yaml")
            if self.env else {}
        )
        try:
            effective = build_effective(declarations, [env_values])
        except Exception:
            # Paramètre requis sans valeur -> fallback sur les défauts seuls
            effective = {
                k: (v or {}).get("default")
                for k, v in declarations.items()
                if isinstance(v, dict) and (v or {}).get("default") is not None
            }
        self._project_params_cache = effective
        return effective

    def _runtime_env_vars(self) -> Dict[str, str]:
        """Convertit les paramètres runtime en variables d'environnement OS,
        injectées dans les actions shell. Accès :
            bash        : $NAME  /  ${NAME}
            PowerShell  : $env:NAME
        Seuls les noms d'identifiant valides sont exportés ; bool -> true/false.
        Agnostique de l'OS : le même dict est passé au sous-processus, seule la
        syntaxe d'accès (côté script utilisateur) diffère entre bash et PowerShell.
        """
        import re as _re
        snapshot = {**self._project_params(), **self._runtime_snapshot()}
        env: Dict[str, str] = {}
        for k, v in snapshot.items():
            if v is None:
                continue
            if not _re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                continue
            env[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
        return env

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

    def _action_delay(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Pause le flux pendant params.seconds avant de laisser passer la suite."""
        raw = params.get("seconds", params.get("duration", 1))
        try:
            seconds = max(0.0, float(raw))
        except (TypeError, ValueError):
            raise ValueError(f"Action delay '{step.name}' : 'seconds' doit être un nombre (reçu: {raw!r})")
        step_log.info(f"[{step.name}] delay {seconds}s")
        time.sleep(seconds)
        return StepResult(
            step_name=step.name, success=True,
            duration=time.monotonic() - start,
        )

    def _action_condition(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Évalue une condition (mode structured ou expression) et stocke le
        booléen résultant dans un paramètre runtime, consommé par le `when`
        des steps en aval (routage conditionnel, B2)."""
        import os
        from hydra_etl.workflow.expr import evaluate_bool, evaluate_structured
        with self._params_lock:
            snap = dict(self.runtime_params)
        merged = {**self._project_params(), **snap}
        env = dict(os.environ)
        mode = str(params.get("mode", "expr"))
        if mode == "structured":
            result = evaluate_structured(params.get("left", ""), str(params.get("op", "==")),
                                         params.get("right", ""), merged, env)
        else:
            result = evaluate_bool(str(params.get("expr", "")), merged, env)
        name = str(params.get("name") or step.name)
        with self._params_lock:
            self.runtime_params[name] = bool(result)
        step_log.info(f"[{step.name}] condition {name} = {bool(result)}")
        return StepResult(
            step_name=step.name, success=True,
            duration=time.monotonic() - start,
        )

    def _eval_when(self, when_expr: str) -> bool:
        """Évalue la garde `when` d'un step avec les paramètres runtime courants."""
        import os
        from hydra_etl.workflow.expr import evaluate_bool
        with self._params_lock:
            snap = dict(self.runtime_params)
        merged = {**self._project_params(), **snap}
        return evaluate_bool(when_expr, merged, dict(os.environ))

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

    def _action_set_param(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Crée un paramètre runtime au moment de l'exécution.

        Échoue si le paramètre existe déjà -> utiliser assign_param pour le
        modifier. Utile pour préparer des flux conditionnels et le débogage.

        Params : name (str, requis), value (requis),
                 type (optionnel : int|float|str|bool|json, défaut any).
        """
        from hydra_etl.internal.config.parameters import coerce_value, ParameterError

        name = params.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"Action set_param '{step.name}' : paramètre 'name' (str) requis")
        if "value" not in params:
            raise ValueError(f"Action set_param '{step.name}' : paramètre 'value' requis")

        typ = str(params.get("type", "any"))
        try:
            value = coerce_value(params["value"], typ, name)
        except ParameterError as ex:
            raise ValueError(f"Action set_param '{step.name}' : {ex}") from None

        with self._params_lock:
            if name in self.runtime_params:
                raise ValueError(
                    f"Action set_param '{step.name}' : le paramètre '{name}' existe déjà "
                    f"(valeur={self.runtime_params[name]!r}). Utilisez assign_param pour le modifier."
                )
            self.runtime_params[name] = value

        step_log.info(f"[{step.name}] set_param {name}={value!r} (type={typ})")
        return StepResult(
            step_name=step.name,
            success=True,
            duration=time.monotonic() - start,
        )

    def _action_assign_param(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Affecte une valeur à un paramètre runtime DÉJÀ existant.

        Échoue si le paramètre n'existe pas -> utiliser set_param d'abord.

        Params : name (str, requis), value (requis), type (optionnel).
        """
        from hydra_etl.internal.config.parameters import coerce_value, ParameterError

        name = params.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"Action assign_param '{step.name}' : paramètre 'name' (str) requis")
        if "value" not in params:
            raise ValueError(f"Action assign_param '{step.name}' : paramètre 'value' requis")

        typ = str(params.get("type", "any"))
        try:
            value = coerce_value(params["value"], typ, name)
        except ParameterError as ex:
            raise ValueError(f"Action assign_param '{step.name}' : {ex}") from None

        with self._params_lock:
            if name not in self.runtime_params:
                raise ValueError(
                    f"Action assign_param '{step.name}' : le paramètre '{name}' n'existe pas. "
                    f"Utilisez set_param pour le créer d'abord."
                )
            old = self.runtime_params[name]
            self.runtime_params[name] = value

        step_log.info(f"[{step.name}] assign_param {name}: {old!r} -> {value!r}")
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

        # Paramètres runtime exposés comme variables d'environnement OS
        # ($NAME en bash, $env:NAME en PowerShell), en plus du templating
        # {{ param:NAME }} déjà résolu dans la commande.
        run_env = {**os.environ, **self._runtime_env_vars()}
        result = subprocess.run(
            shell_args,
            capture_output=True, text=True,
            cwd=work_dir, timeout=timeout,
            env=run_env,
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

    def _action_python(
        self, step: WorkflowStep, params: dict, start: float,
        step_log: logging.Logger,
    ) -> StepResult:
        """Exécute un script Python (inline ou fichier .py) via l'interpréteur
        courant — cross-platform (Windows / Linux / macOS).

        Params : script (str, code inline) OU file_path (chemin .py),
                 working_dir (optionnel), timeout (optionnel, défaut 60s).

        Les {{ param:X }} sont résolus dans le script AVANT exécution, et les
        paramètres (projet + runtime) sont aussi exposés en variables
        d'environnement (os.environ["X"]).
        """
        import subprocess, sys as _sys

        script    = params.get("script") or ""
        file_path = params.get("file_path") or ""
        work_dir  = params.get("working_dir") or None
        timeout   = int(params.get("timeout", 60))

        if not script.strip() and not file_path.strip():
            raise ValueError(
                f"Action python '{step.name}' : 'script' (inline) ou 'file_path' requis"
            )

        if file_path.strip():
            fp = Path(file_path)
            if not fp.is_absolute():
                fp = self.base_dir / fp
            if not fp.exists():
                raise FileNotFoundError(f"Script Python introuvable : {fp}")
            args = [_sys.executable, str(fp)]
            shown = str(fp)
        else:
            args = [_sys.executable, "-c", script]
            shown = script.replace(chr(10), " ")[:80]

        step_log.info(f"[{step.name}] python: {shown}{'…' if len(shown) >= 80 else ''}")

        run_env = {**os.environ, **self._runtime_env_vars()}
        result = subprocess.run(
            args, capture_output=True, text=True,
            cwd=work_dir, timeout=timeout, env=run_env,
        )
        for line in (result.stdout + result.stderr).splitlines():
            step_log.info(f"  {line}")

        if result.returncode != 0:
            raise RuntimeError(
                f"Script Python terminé avec code {result.returncode}"
                f"{chr(10)}{result.stderr[:500]}"
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
            _, stdout, stderr = client.exec_command(
                command, timeout=timeout,
                environment=self._runtime_env_vars() or None,
            )
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
