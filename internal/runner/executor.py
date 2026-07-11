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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from internal.config.yaml_utils import read_yaml_text

from etl.types import JobResult
from internal.config.loader import load_env_layers
from internal.config.secrets import SecretResolver
from internal.connector.interface import Connector
from internal.connector.registry import build_connector
from internal.engines.pandas_engine import PandasEngine
from internal.parser.destination import DestinationParser
from internal.parser.source import SourceParser
from internal.parser.transform import TransformParser

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
        self._source_parser = SourceParser()
        self._dest_parser = DestinationParser()
        self._transform_parser = TransformParser()
        self._engine = PandasEngine()

    def run(self) -> JobResult:
        """Exécute le job ETL."""
        start = time.monotonic()
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

            # 2) Résoudre pipeline (from/to)
            src_id, dest_id = self._resolve_pipeline_ids(pipeline_raw)
            src_def = self._get_source_def(sources_cfg, src_id)
            dest_def = self._get_dest_def(dests_cfg, dest_id)

            # 3) Instancier les connecteurs via le registry
            source_connector = self._build_connector(src_id, src_def, is_source=True)
            dest_connector = self._build_connector(dest_id, dest_def, is_source=False)

            # 4) Extraire les paramètres d'extraction et de chargement
            extract_table, extract_batch_size, extract_query = self._source_extract_params(src_def)
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

            # 6) Streaming batch par batch
            for batch in source_connector.extract_batches(
                table=extract_table,
                batch_size=extract_batch_size,
                query=extract_query,
            ):
                rows_in += len(batch)
                out_batch = batch

                # Transformations (si définies)
                if steps:
                    df_in = pd.DataFrame(batch)
                    pipeline_result = self._engine.apply_pipeline(df_in, steps)
                    df_out = pipeline_result.output
                    out_batch = df_out.to_dict(orient="records")

                rows_out += len(out_batch)

                # Capturer un échantillon de sortie (max 100 lignes au total)
                if len(sample_rows) < 100:
                    sample_rows.extend(out_batch[:100 - len(sample_rows)])

                # Skip empty batches
                if not out_batch:
                    continue

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

            duration = time.monotonic() - start
            
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
            )

        except Exception as exc:
            duration = time.monotonic() - start
            error_msg = f"{exc.__class__.__name__}: {str(exc)}"
            logger.error(f"Job '{self.job_id}' failed: {error_msg}")
            
            return JobResult(
                success=False, 
                rows_in=rows_in, 
                rows_out=rows_out, 
                duration=duration, 
                error=error_msg
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

        try:
            data = self._secret_resolver.resolve(data)
        except Exception as e:
            raise ValueError(f"JobExecutor: échec résolution variables dans {path}: {e}") from e

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

    def _source_extract_params(self, src_def: Any) -> Tuple[Optional[str], int, Optional[str]]:
        """Extrait les paramètres d'extraction depuis la définition source."""
        extract = getattr(src_def, "extract", None)
        if extract is None:
            raise ValueError("JobExecutor: source.extract manquant")

        table = getattr(extract, "table", None)
        query = getattr(extract, "query", None)
        batch_size = getattr(extract, "batch_size", 10_000)

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
