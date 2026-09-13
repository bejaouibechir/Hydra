"""
JobExecutor — VERSION SPRINT 1 (Support Mode Upsert avec Validation)

CHANGEMENTS SPRINT 1 (Backlog 2.3):
- Support mode upsert dans load_batches
- Validation capabilities destination (CSV ne supporte pas upsert)
- Validation key columns requises pour upsert
- Validation key columns présentes dans les données
- Messages d'erreur clairs et actionnables

FIX FINAL: Validation basée sur type connector, pas sur capabilities object
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from hydra_etl.internal.config.yaml_utils import read_yaml_text

from hydra_etl.etl.types import JobResult
from hydra_etl.internal.config.loader import load_env_layers
from hydra_etl.internal.config.secrets import SecretResolver
from hydra_etl.internal.config.parameters import ParameterResolver, build_effective
from hydra_etl.internal.connector.interface import Connector
from hydra_etl.internal.connector.frame_batch import FrameBatch, frame_io_enabled
from hydra_etl.internal.connector.registry import build_connector
from hydra_etl.internal.engines.frame_copy import copy_on_write
from hydra_etl.internal.engines.pandas_engine import PandasEngine
from hydra_etl.internal.runner import batch_size as batch_size_policy
from hydra_etl.internal.runner.projection import required_columns
from hydra_etl.internal.runner.profiler import (
    JobProfiler,
    format_profile,
    profile_enabled,
)
from hydra_etl.internal.parser.destination import DestinationParser
from hydra_etl.internal.parser.source import SourceParser
from hydra_etl.internal.parser.transform import TransformParser

logger = logging.getLogger(__name__)


class JobExecutor:
    """
    Executor ETL avec support mode upsert.
    
    Version Sprint 1:
    - Validation capabilities destination
    - Support mode upsert avec key columns
    - Fail-fast sur configurations invalides
    """

    def __init__(
        self,
        job_dir: Path,
        root_dir: Optional[Path] = None,
        override_os: bool = True,
        *,
        sources_file: Optional[Path] = None,
        destinations_file: Optional[Path] = None,
        pipeline_file: Optional[Path] = None,
        transformations_file: Optional[Path] = None,
        path_base: Optional[Path] = None,
        params: Optional[Dict[str, Any]] = None,
        env: Optional[str] = None,
        profile: Optional[bool] = None,
    ) -> None:
        """Initialise l'executor."""
        self.job_dir = Path(job_dir).resolve()
        self.root_dir = root_dir or self.job_dir.parent
        # path_base : dossier de référence pour la résolution des chemins relatifs
        # dans les connecteurs fichier (csv, json). Par défaut = job_dir.
        # Surchargé lors d'exécution inline depuis Studio pour pointer
        # vers le dossier job d'origine plutôt que le dossier temporaire.
        self.path_base = Path(path_base).resolve() if path_base else self.job_dir
        self.job_id = self.job_dir.name
        # Fichiers explicites (surcharge docker-compose style)
        self._sources_file      = Path(sources_file).resolve()      if sources_file      else self.job_dir / "sources.yaml"
        self._destinations_file = Path(destinations_file).resolve() if destinations_file else self.job_dir / "destinations.yaml"
        self._pipeline_file     = Path(pipeline_file).resolve()     if pipeline_file     else self.job_dir / "pipeline.yaml"
        self._transforms_file   = Path(transformations_file).resolve() if transformations_file else self.job_dir / "transformations.yaml"

        
        # Chargement .env layers
        try:
            root_env_path = self.root_dir / ".env" if (self.root_dir / ".env").exists() else None
            job_env_path = self.job_dir / ".env" if (self.job_dir / ".env").exists() else None
            
            env_report = load_env_layers(
                root_env_path=root_env_path,
                job_env_path=job_env_path,
                override_os=override_os
            )
            logger.info(f"Loaded {env_report.loaded_root} root vars, {env_report.loaded_job} job vars")
        except Exception as e:
            logger.warning(f"Could not load .env layers: {e}")
        
        # Parsers et engine
        self._secret_resolver = SecretResolver(secrets={})
        # Parametres (couche statique, lecture seule) resolus avant le parsing
        self._runtime_params = dict(params or {})
        self._active_env = env or os.environ.get("HYDRA_ENV")
        self._effective_params = self._load_parameters()
        self._param_resolver = ParameterResolver(params=self._effective_params, env=dict(os.environ), strict=False, strict_params=True)
        self._source_parser = SourceParser()
        self._dest_parser = DestinationParser()
        self._transform_parser = TransformParser()
        self._engine = PandasEngine()
        # Profil d'exécution (--profile / HYDRA_PROFILE=1) : désactivé, il ne
        # coûte rien ; activé, il chronomètre extract / chaque step / load.
        self._profiler = JobProfiler(profile_enabled(profile))

    def run(self) -> JobResult:
        """Exécute le job ETL."""
        # Copy-on-Write : les copies défensives des opérations deviennent
        # paresseuses (comportement natif de pandas 3, aligné ici sur pandas 2).
        with copy_on_write():
            return self._run()

    def _run(self) -> JobResult:
        start = time.monotonic()
        prof = self._profiler
        rows_in = 0
        rows_out = 0

        try:
            # 0) Charger YAML avec résolution ${ENV:...}
            sources_raw = self._load_yaml_with_resolution(self._sources_file, required=True)
            dests_raw = self._load_yaml_with_resolution(self._destinations_file, required=True)
            pipeline_raw = self._load_yaml_with_resolution(self._pipeline_file, required=True)
            transforms_raw = self._load_yaml_with_resolution(self._transforms_file, required=False)

            # 1) Valider DSL
            sources_cfg = self._source_parser.parse(sources_raw)
            dests_cfg = self._dest_parser.parse(dests_raw)

            steps: List[Dict[str, Any]] = []
            # Un transformations.yaml présent mais SANS steps (steps: []) est
            # valide : job source → destination sans transformation.
            # (Cas généré par Studio et fréquent en création manuelle.)
            if transforms_raw and self._has_transform_steps(transforms_raw):
                transforms_cfg = self._transform_parser.parse(transforms_raw)
                steps = self._extract_steps_for_engine(transforms_cfg)

            # Precharger la source de reference des eventuels steps 'join'
            self._prepare_join_steps(steps, sources_cfg)
            self._inject_script_params(steps)

            # 2) Résoudre pipeline (from/to)
            src_id, dest_id = self._resolve_pipeline_ids(pipeline_raw)
            src_def = self._get_source_def(sources_cfg, src_id)
            dest_def = self._get_dest_def(dests_cfg, dest_id)

            # 3) Instancier les connecteurs via le registry
            source_connector = self._build_connector(src_id, src_def, is_source=True)
            dest_connector = self._build_connector(dest_id, dest_def, is_source=False)

            # 3-bis) Projection : ne lire que les colonnes dont le job se sert.
            #        L'analyse rend None au moindre doute -> lecture complète.
            self._apply_projection(source_connector, steps)

            # 4) Extraire les paramètres d'extraction et de chargement
            extract_table, extract_batch_size, extract_query = self._source_extract_params(
                src_def, connector=source_connector
            )
            load_table, load_mode, load_key = self._dest_load_params(dest_def)
            
            # 4b) Sprint 1: Validation anticipée (fail-fast)
            self._validate_load_params_before_execution(
                dest_connector=dest_connector,
                dest_name=dest_id,
                load_mode=load_mode,
                key_columns=load_key,
            )

            # 5) Gestion du mode replace : premier batch en "replace", suivants en "append"
            first_batch_written = False
            effective_mode = load_mode
            sample_rows: list = []   # capture jusqu'à 100 lignes de sortie

            # 6) Étape 0-bis : les opérations globales (aggregate, sort, ...)
            #    doivent voir toutes les lignes, pas un batch à la fois.
            #    stream_steps s'appliquent batch par batch ; à partir de la
            #    première opération globale, le reste s'applique une seule
            #    fois sur l'ensemble concaténé. Sans opération globale, le
            #    comportement est strictement celui d'avant (streaming).
            stream_steps, global_steps = self._split_global_steps(steps)
            global_frames: List[pd.DataFrame] = []

            # Échanges par DataFrame (étape 0-bis) : seulement avec des transformations
            # (sans transformation, les dicts de la source partent tels quels, comme avant),
            # et seulement si le connecteur le propose. HYDRA_FRAME_IO=0 pour désactiver.
            frames_in = bool(steps) and frame_io_enabled() and callable(
                getattr(source_connector, "extract_frames", None))
            frames_out = frame_io_enabled() and bool(
                getattr(dest_connector, "accepts_frame_batches", False))

            def _out_batch(df_out: pd.DataFrame) -> Any:
                if frames_out:
                    fb = FrameBatch.wrap(df_out)
                    if fb is not None:
                        return fb
                return df_out.to_dict(orient="records")

            def _emit(out_batch: list) -> None:
                """Comptage, échantillon, validation et chargement d'un batch de sortie
                (logique inchangée, extraite de la boucle pour servir aux deux chemins)."""
                nonlocal rows_out, first_batch_written, effective_mode

                rows_out += len(out_batch)

                # Capturer un échantillon de sortie (max 100 lignes au total)
                if len(sample_rows) < 100:
                    sample_rows.extend(out_batch[:100 - len(sample_rows)])

                # Skip empty batches
                if not out_batch:
                    return

                # Sprint 1: Validation capabilities au premier batch
                if not first_batch_written:
                    self._validate_destination_capabilities(
                        dest_connector=dest_connector,
                        dest_name=dest_id,
                        load_mode=load_mode,
                        key_columns=load_key,
                        first_batch=out_batch,
                    )

                # Load avec le bon mode et key si upsert
                with prof.span("load"):
                    dest_connector.load_batches(
                        [out_batch],
                        table=load_table,
                        mode=effective_mode,
                        key=load_key if load_mode == "upsert" else None
                    )

                # Après le premier batch, passer en append (sauf si déjà upsert)
                if not first_batch_written:
                    first_batch_written = True
                    if load_mode == "replace":
                        effective_mode = "append"

            # 7) Streaming batch par batch
            extract = source_connector.extract_frames if frames_in else source_connector.extract_batches
            for batch in prof.iterate("extract", extract(
                table=extract_table,
                batch_size=extract_batch_size,
                query=extract_query,
            )):
                rows_in += len(batch)
                out_batch = batch

                if global_steps:
                    with prof.span("batch -> DataFrame"):
                        df_in = batch if isinstance(batch, pd.DataFrame) else pd.DataFrame(batch)
                    if stream_steps:
                        df_in = self._run_steps(df_in, stream_steps, 1, len(steps))
                    global_frames.append(df_in)
                    continue

                # Transformations (si définies)
                if steps:
                    with prof.span("batch -> DataFrame"):
                        df_in = batch if isinstance(batch, pd.DataFrame) else pd.DataFrame(batch)
                    # _run_steps == apply_pipeline (mêmes messages d'erreur), mais
                    # chronométrable étape par étape.
                    df_out = self._run_steps(df_in, steps, 1, len(steps))
                    with prof.span("DataFrame -> sortie"):
                        out_batch = _out_batch(df_out)

                _emit(out_batch)

            # 8) Opérations globales : une seule passe sur l'ensemble des lignes
            if global_steps and global_frames:
                non_empty = [f for f in global_frames if len(f)] or global_frames[:1]
                with prof.span("concaténation (opérations globales)"):
                    df_all = non_empty[0] if len(non_empty) == 1 else pd.concat(non_empty, ignore_index=True)
                global_frames.clear()
                logger.info(
                    f"Job '{self.job_id}': global operations on {len(df_all)} rows "
                    f"(steps {len(stream_steps) + 1}-{len(steps)})"
                )
                df_all = self._run_steps(df_all, global_steps, len(stream_steps) + 1, len(steps))
                # Conversion en records par tranche : même coût qu'avant par batch,
                # et pas de liste géante de dicts en mémoire (pression GC).
                chunk = max(1, int(extract_batch_size or 1))
                if len(df_all) == 0:
                    _emit(df_all.to_dict(orient="records"))
                for i in range(0, len(df_all), chunk):
                    with prof.span("DataFrame -> sortie"):
                        out_chunk = _out_batch(df_all.iloc[i:i + chunk])
                    _emit(out_chunk)

            duration = time.monotonic() - start

            profile_data = None
            if prof.enabled:
                profile_data = prof.to_dict(
                    total=duration, rows_in=rows_in, rows_out=rows_out, job_id=self.job_id
                )
                logger.info("\n" + format_profile(profile_data))

            logger.info(
                f"Job '{self.job_id}' completed successfully: "
                f"{rows_in} rows in, {rows_out} rows out, {duration:.2f}s"
            )
            
            output_cols = list(sample_rows[0].keys()) if sample_rows else []
            # Convertir types numpy → types Python natifs (JSON-safe)
            import json as _json
            import pandas as _pd
            if sample_rows:
                safe_sample = _json.loads(
                    _pd.DataFrame(sample_rows[:100]).to_json(orient="records", date_format="iso")
                )
            else:
                safe_sample = []
            return JobResult(
                success=True,
                rows_in=rows_in,
                rows_out=rows_out,
                duration=duration,
                error=None,
                output_sample=safe_sample,
                output_columns=output_cols,
                profile=profile_data,
            )

        except Exception as exc:
            duration = time.monotonic() - start
            error_msg = f"{exc.__class__.__name__}: {str(exc)}"
            logger.error(f"Job '{self.job_id}' failed: {error_msg}")

            profile_data = None
            if self._profiler.enabled:
                profile_data = self._profiler.to_dict(
                    total=duration, rows_in=rows_in, rows_out=rows_out, job_id=self.job_id
                )
                logger.info("\n" + format_profile(profile_data))

            return JobResult(
                success=False,
                rows_in=rows_in,
                rows_out=rows_out,
                duration=duration,
                error=error_msg,
                profile=profile_data,
            )

    def _apply_projection(self, source_connector: Connector, steps: List[Dict[str, Any]]) -> None:
        """Restreint la lecture de la source aux colonnes utiles au job."""
        if not steps or not getattr(source_connector, "supports_projection", False):
            return
        needed = required_columns(steps)
        if not needed:
            return
        try:
            source_connector.set_projection(sorted(needed))
        except Exception as exc:  # noqa: BLE001 - jamais bloquant
            logger.debug("Projection ignorée : %s", exc)
            return
        logger.info(
            "Job '%s': lecture restreinte à %d colonne(s) : %s",
            self.job_id, len(needed), ", ".join(sorted(needed)),
        )

    # =========================================================================
    # Helpers - Chargement YAML
    # =========================================================================

    def _load_yaml_with_resolution(self, path: Path, *, required: bool) -> Dict[str, Any]:
        """Charge un fichier YAML et résout les variables ${ENV:...}."""
        if not path.exists():
            if required:
                raise ValueError(f"JobExecutor: fichier requis manquant: {path}")
            return {}

        raw_text = read_yaml_text(path)
        data = yaml.safe_load(raw_text)

        if data is None:
            return {}

        if not isinstance(data, dict):
            raise ValueError(f"JobExecutor: YAML invalide (dict attendu): {path}")

        # Regle 3.2 : on lit la version du format, on avertit, on n'echoue jamais.
        from hydra_etl.internal.dsl_version import check_dsl_version
        check_dsl_version(data, path.name)

        try:
            data = self._secret_resolver.resolve(data)
        except Exception as e:
            raise ValueError(f"JobExecutor: échec résolution variables dans {path}: {e}") from e

        try:
            data = self._param_resolver.resolve(data)
        except Exception as e:
            raise ValueError(f"JobExecutor: échec résolution paramètres dans {path}: {e}") from e

        return data

    # =========================================================================
    # Helpers - Résolution Pipeline
    # =========================================================================

    def _resolve_pipeline_ids(self, pipeline_raw: Dict[str, Any]) -> Tuple[str, str]:
        """Extrait from/to depuis pipeline.yaml."""
        pipe = pipeline_raw.get("pipeline")
        # Tolérance : format imbriqué job: → pipeline: (générés par d'anciennes
        # versions de Studio) — la clé canonique reste 'pipeline' à la racine.
        if not isinstance(pipe, dict):
            job_section = pipeline_raw.get("job")
            if isinstance(job_section, dict) and isinstance(job_section.get("pipeline"), dict):
                pipe = job_section["pipeline"]
        if not isinstance(pipe, dict):
            raise ValueError("JobExecutor: pipeline.yaml invalide (clé 'pipeline' dict attendue)")

        src_id = pipe.get("from")
        dest_id = pipe.get("to")

        if not isinstance(src_id, str) or not src_id.strip():
            raise ValueError("JobExecutor: pipeline.from manquant ou invalide")
        if not isinstance(dest_id, str) or not dest_id.strip():
            raise ValueError("JobExecutor: pipeline.to manquant ou invalide")

        return src_id.strip(), dest_id.strip()

    def _get_source_def(self, sources_cfg: Any, src_id: str) -> Any:
        """Récupère la définition d'une source."""
        sources = getattr(sources_cfg, "sources", None)
        if not isinstance(sources, dict) or src_id not in sources:
            raise ValueError(f"JobExecutor: source inconnue: '{src_id}'")
        return sources[src_id]

    def _get_dest_def(self, dests_cfg: Any, dest_id: str) -> Any:
        """Récupère la définition d'une destination."""
        dests = getattr(dests_cfg, "destinations", None)
        if not isinstance(dests, dict) or dest_id not in dests:
            raise ValueError(f"JobExecutor: destination inconnue: '{dest_id}'")
        return dests[dest_id]

    # =========================================================================
    # Helpers - Transformations
    # =========================================================================

    def _config_dirs(self) -> List[Path]:
        """Dossiers de config du plus LOIN (racine projet, precedence faible) au plus
        PROCHE du job (precedence forte). Remonte l'arborescence depuis le job (borne
        a 6 niveaux) et s'arrete apres une racine de projet (.hydra/ ou workflows/).
        Permet a un run Studio (job dans project/jobs/<name>) de trouver
        parameters.yaml / environments/ places a la racine projet."""
        dirs: List[Path] = []
        # On remonte l'arborescence depuis plusieurs ancres. En exécution Studio,
        # job_dir est un dossier temporaire hors de l'arbre projet : les fichiers
        # parameters.yaml / environments/ ne s'y trouvent pas. root_dir et
        # path_base pointent vers le projet réel -> on les remonte aussi pour
        # retrouver les déclarations de paramètres (sinon host=None silencieux).
        anchors: List[Path] = [self.job_dir, self.root_dir, self.path_base]
        for anchor in anchors:
            d = anchor
            for _ in range(6):
                if d not in dirs:
                    dirs.append(d)
                if (d / ".hydra").exists() or (d / "workflows").is_dir():
                    break
                if d.parent == d:
                    break
                d = d.parent
        uniq: List[Path] = []
        for x in dirs:
            if x not in uniq:
                uniq.append(x)
        return list(reversed(uniq))

    def _load_parameters(self) -> Dict[str, Any]:
        """Declarations (parameters.yaml) + valeurs de l'env actif
        (environments/<env>.yaml) collectees le long de l'arborescence (le plus proche
        du job l'emporte) + surcharges runtime -> valeurs effectives."""
        def _block(path: Path) -> Dict[str, Any]:
            if not path.exists():
                return {}
            try:
                data = yaml.safe_load(read_yaml_text(path)) or {}
            except Exception:
                return {}
            if isinstance(data, dict):
                block = data.get("parameters", data)
                return block if isinstance(block, dict) else {}
            return {}

        declarations: Dict[str, Any] = {}
        env_values: Dict[str, Any] = {}
        for cd in self._config_dirs():
            declarations.update(_block(cd / "parameters.yaml"))
            if self._active_env:
                env_values.update(_block(cd / "environments" / f"{self._active_env}.yaml"))
        return build_effective(declarations, [env_values, self._runtime_params])

    def _inject_script_params(self, steps: List[Dict[str, Any]]) -> None:
        """Injecte les parametres effectifs (lecture seule) dans les steps 'script'."""
        if not self._effective_params:
            return
        for step in steps:
            if isinstance(step, dict) and isinstance(step.get("script"), dict):
                step["script"]["_params"] = dict(self._effective_params)

    @staticmethod
    def _has_transform_steps(raw: Any) -> bool:
        """True si le YAML de transformations contient au moins un step."""
        if not isinstance(raw, dict):
            return False
        steps = raw.get("steps")
        if steps is None:
            inner = raw.get("transformations")
            if isinstance(inner, dict):
                steps = inner.get("steps")
            elif isinstance(inner, list):
                steps = inner
        return bool(steps)

    def _extract_steps_for_engine(self, transforms_cfg: Any) -> List[Dict[str, Any]]:
        """Convertit la config Pydantic des transformations en format attendu par le engine."""
        if hasattr(transforms_cfg, "model_dump"):
            config_dict = transforms_cfg.model_dump()
        elif hasattr(transforms_cfg, "dict"):
            config_dict = transforms_cfg.dict()
        else:
            raise ValueError("JobExecutor: transforms_cfg n'est pas un modèle Pydantic valide")
        
        steps_raw = config_dict.get("steps", [])
        if not steps_raw:
            return []
        
        steps_for_engine: List[Dict[str, Any]] = []
        
        for step_dict in steps_raw:
            if not isinstance(step_dict, dict):
                raise ValueError("JobExecutor: step transformation invalide (dict attendu)")
            
            op = step_dict.get("op")
            params = step_dict.get("params")
            
            if not isinstance(op, str) or not op.strip():
                raise ValueError("JobExecutor: step.op invalide")
            
            if params is None:
                params = {}
            
            if hasattr(params, "model_dump"):
                params = params.model_dump()
            elif hasattr(params, "dict"):
                params = params.dict()
            elif not isinstance(params, dict):
                raise ValueError("JobExecutor: step.params invalide (dict attendu)")
            
            steps_for_engine.append({op.strip(): params})
        
        return steps_for_engine

    # Opérations dont le résultat dépend de l'ensemble des lignes : appliquées
    # batch par batch, elles produisent un résultat faux (agrégats partiels,
    # tri local, doublons inter-batch, union/merge répétés à chaque batch).
    _GLOBAL_OPS = frozenset({
        "aggregate", "sort", "deduplicate", "pivot", "unpivot",
        "transpose", "union", "merge",
    })

    @classmethod
    def _is_global_step(cls, step: Dict[str, Any]) -> bool:
        """Vrai si le step doit voir toutes les lignes d'un coup."""
        if "op" in step:
            op, params = step.get("op"), step.get("params") or {}
        else:
            op, params = next(iter(step)), next(iter(step.values()))
        op = str(op).strip().lower()
        params = params if isinstance(params, dict) else {}
        if op in cls._GLOBAL_OPS:
            return True
        if op == "join":
            # right/outer : les lignes de droite non appariées seraient répétées à chaque batch
            return str(params.get("how", "inner")).lower() in ("right", "outer")
        if op == "script":
            # vectorized : le code reçoit des Series entières (rank, mean, cumsum...)
            return str(params.get("mode", "vectorized")).lower() == "vectorized"
        return False

    @classmethod
    def _split_global_steps(
        cls, steps: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Coupe la liste au premier step global : (steps par batch, steps sur l'ensemble)."""
        for i, step in enumerate(steps):
            if cls._is_global_step(step):
                return steps[:i], steps[i:]
        return list(steps), []

    def _run_steps(
        self, df: pd.DataFrame, steps: List[Dict[str, Any]], start: int, total: int
    ) -> pd.DataFrame:
        """Applique une tranche de steps en gardant la numérotation du pipeline complet
        (même format de message que PandasEngine.apply_pipeline)."""
        prof = self._profiler
        for idx, step in enumerate(steps, start=start):
            try:
                with prof.span(f"{idx} {self._step_op_name(step)}"):
                    df = self._engine.apply_step(df, step).output
            except ValueError as e:
                raise ValueError(f"Erreur à l'étape {idx}/{total}: {e}") from None
        return df

    @staticmethod
    def _step_op_name(step: Dict[str, Any]) -> str:
        """Nom de l'opération d'un step, quel que soit le format ({op:...} ou {op: params})."""
        if not isinstance(step, dict):
            return "?"
        if "op" in step:
            return str(step.get("op") or "?").strip().lower()
        try:
            return str(next(iter(step))).strip().lower()
        except StopIteration:
            return "?"

    def _prepare_join_steps(self, steps: List[Dict[str, Any]], sources_cfg: Any) -> None:
        """Precharge la source de reference (2e flux) de chaque step 'join'.

        join.right peut etre :
          - un id de source declaree dans sources.yaml (recommande), ou
          - une source inline (dict avec 'type') pour un usage ponctuel.
        """
        for step in steps:
            if not isinstance(step, dict):
                continue
            op = "join" if "join" in step else ("merge" if "merge" in step else ("union" if "union" in step else None))
            if op is None:
                continue
            params = step[op]
            if not isinstance(params, dict):
                continue
            right = params.get("right")

            if isinstance(right, str) and right.strip():
                # Reference vers une source declaree
                src_def = self._get_source_def(sources_cfg, right.strip())
                conn = self._build_connector(right.strip(), src_def, is_source=True)
                r_table, r_bs, r_query = self._source_extract_params(src_def)
            elif isinstance(right, dict) and right.get("type"):
                # Source inline (compat)
                rtype = str(right["type"]).strip().lower()
                config: Dict[str, Any] = {"type": rtype}
                if isinstance(right.get("connection"), dict):
                    config["connection"] = right["connection"]
                ext = right.get("extract") if isinstance(right.get("extract"), dict) else {}
                if ext:
                    config["extract"] = ext
                if rtype in ("csv", "json"):
                    config["job_dir"] = str(self.path_base)
                conn = build_connector(name=f"{op}_right", config=config)
                r_table = ext.get("table")
                r_bs = int(ext.get("batch_size", 10000))
                r_query = ext.get("query")
            else:
                raise ValueError(
                    f"JobExecutor: {op}.right doit etre un id de source declaree ou une source inline (dict avec 'type')"
                )

            rows: List[Dict[str, Any]] = []
            for b in conn.extract_batches(table=r_table, batch_size=r_bs, query=r_query):
                rows.extend(b)
            params["_right_rows"] = rows

    # =========================================================================
    # Helpers - Connecteurs
    # =========================================================================

    def _build_connector(self, name: str, definition: Any, is_source: bool) -> Connector:
        """Instancie un connecteur via le registry."""
        # 1. Extraire le type
        ctype = getattr(definition, "type", None)
        ctype = ctype.strip().lower() if isinstance(ctype, str) else None
        
        if not ctype:
            connector_role = "source" if is_source else "destination"
            raise ValueError(f"JobExecutor: {connector_role} '{name}' sans type défini")

        # 2. Construire la config complète
        config: Dict[str, Any] = {"type": ctype}
        
        # 2a. Ajouter connection si présente (pour DB)
        connection = getattr(definition, "connection", None)
        if connection is not None:
            if hasattr(connection, "model_dump"):
                config["connection"] = connection.model_dump()
            elif hasattr(connection, "dict"):
                config["connection"] = connection.dict()
            elif isinstance(connection, dict):
                config["connection"] = connection
            else:
                raise ValueError(f"JobExecutor: connection invalide pour '{name}' (dict attendu)")
        
        # 2b. Ajouter extract/load selon le rôle
        if is_source:
            extract = getattr(definition, "extract", None)
            if extract is not None:
                if hasattr(extract, "model_dump"):
                    config["extract"] = extract.model_dump()
                elif hasattr(extract, "dict"):
                    config["extract"] = extract.dict()
                elif isinstance(extract, dict):
                    config["extract"] = extract
        else:
            load = getattr(definition, "load", None)
            if load is not None:
                if hasattr(load, "model_dump"):
                    config["load"] = load.model_dump()
                elif hasattr(load, "dict"):
                    config["load"] = load.dict()
                elif isinstance(load, dict):
                    config["load"] = load
        
        # 2c. Pour les connecteurs fichier, injecter path_base résolu (absolu)
        # path_base == job_dir en mode CLI ; == dossier job d\'origine en mode Studio inline.
        if ctype in ("csv", "json"):
            config["job_dir"] = str(self.path_base)
        
        # 3. Instancier via le registry
        try:
            connector = build_connector(name=name, config=config)
        except ValueError as e:
            connector_role = "source" if is_source else "destination"
            raise ValueError(
                f"JobExecutor: échec instanciation {connector_role} '{name}' (type='{ctype}'). "
                f"Erreur: {e}"
            ) from e
        
        return connector

    # =========================================================================
    # Helpers - Paramètres Extract/Load
    # =========================================================================

    def _source_extract_params(
        self, src_def: Any, connector: Optional[Connector] = None
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Extrait les paramètres d'extraction depuis la définition source.

        batch_size non déclaré dans le YAML : la taille est calculée pour
        viser ~64 Mo par lot à partir d'un échantillon de la source
        (voir runner/batch_size.py). Déclaré : la valeur est respectée, avec
        un avertissement si elle est trop petite pour être efficace.
        """
        extract = getattr(src_def, "extract", None)
        if extract is None:
            raise ValueError("JobExecutor: source.extract manquant")

        table = getattr(extract, "table", None)
        query = getattr(extract, "query", None)
        declared = "batch_size" in (getattr(extract, "model_fields_set", None) or set())
        if declared:
            batch_size = getattr(extract, "batch_size", 10_000)
            batch_size_policy.warn_if_too_small(batch_size, self.job_id)
        else:
            batch_size = batch_size_policy.resolve(
                connector, table if isinstance(table, str) else None, self.job_id
            )

        if not isinstance(batch_size, int) or not (100 <= batch_size <= 100_000):
            raise ValueError(
                f"JobExecutor: source.extract.batch_size invalide ({batch_size}). "
                f"Doit être entre 100 et 100,000."
            )

        if not table and not query:
            raise ValueError("JobExecutor: source.extract doit définir 'table' ou 'query'")

        if table is not None:
            if not isinstance(table, str) or not table.strip():
                raise ValueError("JobExecutor: source.extract.table invalide")
            table = table.strip()

        if query is not None:
            if not isinstance(query, str):
                raise ValueError("JobExecutor: source.extract.query invalide (str attendu)")
            query = query.strip() if query.strip() else None

        return table, batch_size, query

    def _dest_load_params(self, dest_def: Any) -> Tuple[str, str, Optional[List[str]]]:
        """Extrait les paramètres de chargement depuis la définition destination."""
        load = getattr(dest_def, "load", None)
        if load is None:
            raise ValueError("JobExecutor: destination.load manquant")

        table = getattr(load, "table", None)
        mode = getattr(load, "mode", "append")
        key = getattr(load, "key", None)

        if not isinstance(table, str) or not table.strip():
            raise ValueError("JobExecutor: destination.load.table manquant ou invalide")

        if not isinstance(mode, str) or not mode.strip():
            raise ValueError("JobExecutor: destination.load.mode invalide")

        # Normalisation mode (support Enum LoadMode)
        if hasattr(mode, 'value'):
            mode_norm = mode.value
        else:
            mode_norm = mode.strip().lower()

        # Validation: mode supporté
        if mode_norm not in ("append", "replace", "upsert"):
            raise ValueError(
                f"JobExecutor: destination.load.mode='{mode}' non supporté. "
                f"Modes supportés : 'append', 'replace', 'upsert'."
            )

        return table.strip(), mode_norm, key

    # =========================================================================
    # Sprint 1 - Validation Capabilities
    # =========================================================================

    def _validate_load_params_before_execution(
        self,
        dest_connector: Connector,
        dest_name: str,
        load_mode: str,
        key_columns: Optional[List[str]],
    ) -> None:
        """Validation anticipée avant de commencer le streaming."""
        # Validation 1: Mode upsert → key requis
        if load_mode == "upsert" and not key_columns:
            raise ValueError(
                f"Mode 'upsert' requires 'key' parameter for destination '{dest_name}'. "
                f"Add key to destinations.yaml"
            )
        
        # Validation 2: Types connus ne supportant pas upsert
        connector_type = getattr(dest_connector, 'config', {}).get('type', 'unknown')
        
        if load_mode == "upsert" and connector_type in ["csv", "json", "excel"]:
            raise ValueError(
                f"Destination '{dest_name}' (type={connector_type}) does not support mode 'upsert'. "
                f"Use 'append' or 'replace' instead."
            )

    def _validate_destination_capabilities(
        self,
        dest_connector: Connector,
        dest_name: str,
        load_mode: str,
        key_columns: Optional[List[str]],
        first_batch: List[dict],
    ) -> None:
        """
        Valide que la destination supporte le mode demandé.
        
        ✅ FIX FINAL: Validation basée sur type, pas sur objet capabilities.
        """
        # 1. Récupérer type connecteur
        connector_type = getattr(dest_connector, 'config', {}).get('type', 'unknown')
        
        # 2. Validation mode upsert selon type
        if load_mode == "upsert":
            # Types fichiers ne supportent jamais upsert
            non_upsert_types = ["csv", "json", "excel"]
            
            if connector_type in non_upsert_types:
                raise ValueError(
                    f"Destination '{dest_name}' (type={connector_type}) does not support mode 'upsert'. "
                    f"Upsert requires a database with PRIMARY KEY or UNIQUE constraint. "
                    f"Supported modes for {connector_type.upper()}: append, replace"
                )
            
            # Types DB supportent upsert (mysql, mariadb, postgresql, etc.)
            # → Pas d'erreur, continuer
        
        # 3. Validation upsert → key requis
        if load_mode == "upsert":
            if not key_columns:
                raise ValueError(
                    f"Mode 'upsert' requires 'key' parameter for destination '{dest_name}'. "
                    f"Specify key columns in destinations.yaml:\n"
                    f"  load:\n"
                    f"    table: your_table\n"
                    f"    mode: upsert\n"
                    f"    key: [id]  # or [col1, col2] for composite key"
                )
        
        # 4. Validation colonnes key existent dans les données
        if load_mode == "upsert" and key_columns and first_batch:
            if not first_batch or not isinstance(first_batch[0], dict):
                return
            
            available_columns = set(first_batch[0].keys())
            missing_keys = set(key_columns) - available_columns
            
            if missing_keys:
                raise ValueError(
                    f"Key column(s) {sorted(missing_keys)} not found in data for destination '{dest_name}'. "
                    f"Available columns: {sorted(available_columns)}. "
                    f"Check your transformations or source data."
                )
