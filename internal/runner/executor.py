"""
JobExecutor — VERSION FINALE CORRIGÉE (Étape 7 - FIX COMPLET)

FIX CRITIQUE Étape 7 : Mode replace doit utiliser le connecteur pour résoudre les chemins,
pas accéder directement au filesystem avec Path().
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from etl.types import JobResult
from internal.config.loader import load_env_layers
from internal.config.secrets import SecretResolver
from internal.connector.csv_connector import CSVConnector
from internal.engines.pandas_engine import PandasEngine
from internal.parser.destination import DestinationParser
from internal.parser.source import SourceParser
from internal.parser.transform import TransformParser

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executor minimaliste pour orchestrer un job ETL."""

    def __init__(
        self, 
        job_dir: Path, 
        root_dir: Optional[Path] = None,
        override_os: bool = True
    ) -> None:
        self.job_dir = Path(job_dir)
        self.root_dir = root_dir or self.job_dir.parent
        self.job_id = self.job_dir.name
        
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
        
        self._secret_resolver = SecretResolver(secrets={})
        self._source_parser = SourceParser()
        self._dest_parser = DestinationParser()
        self._transform_parser = TransformParser()
        self._engine = PandasEngine()

    def run(self) -> JobResult:
        """Exécute le job en mode fail-fast."""
        start = time.monotonic()
        rows_in = 0
        rows_out = 0

        try:
            # 0) Charger YAML
            sources_raw = self._load_yaml_with_resolution(self.job_dir / "sources.yaml", required=True)
            dests_raw = self._load_yaml_with_resolution(self.job_dir / "destinations.yaml", required=True)
            pipeline_raw = self._load_yaml_with_resolution(self.job_dir / "pipeline.yaml", required=True)
            transforms_raw = self._load_yaml_with_resolution(self.job_dir / "transformations.yaml", required=False)

            # 1) Valider DSL
            sources_cfg = self._source_parser.parse(sources_raw)
            dests_cfg = self._dest_parser.parse(dests_raw)

            steps: List[Dict[str, Any]] = []
            if transforms_raw:
                transforms_cfg = self._transform_parser.parse(transforms_raw)
                steps = self._extract_steps_for_engine(transforms_cfg)

            # 2) Résoudre pipeline
            src_id, dest_id = self._resolve_pipeline_ids(pipeline_raw)
            src_def = self._get_source_def(sources_cfg, src_id)
            dest_def = self._get_dest_def(dests_cfg, dest_id)

            # 3) Connecteurs
            source_connector = self._build_connector(src_id, src_def, is_source=True)
            dest_connector = self._build_connector(dest_id, dest_def, is_source=False)

            # 4) Params
            extract_table, extract_batch_size, extract_query = self._source_extract_params(src_def)
            load_table, load_mode = self._dest_load_params(dest_def)

            if extract_query is not None and str(extract_query).strip():
                raise ValueError(
                    f"JobExecutor: source '{src_id}' utilise 'query' mais le connecteur CSV "
                    f"ne supporte que 'table'. Utilisez extract.table à la place."
                )

            # ==================================================================
            # 🔥 FIX ÉTAPE 7 : Mode replace via le connecteur (pas Path direct)
            # ==================================================================
            first_batch_written = False
            effective_mode = load_mode  # "replace" pour le premier batch, "append" ensuite
            
            # 5) Streaming batch par batch
            for batch in source_connector.extract_batches(
                table=extract_table,
                batch_size=extract_batch_size,
                query=None,
            ):
                rows_in += len(batch)
                out_batch = batch

                # Transformations
                if steps:
                    df_in = pd.DataFrame(batch)
                    df_out = self._engine.apply_pipeline(df_in, steps)
                    out_batch = df_out.to_dict(orient="records")

                rows_out += len(out_batch)

                # Skip empty batches
                if not out_batch:
                    continue

                # Load avec le bon mode
                dest_connector.load_batches(
                    [out_batch], 
                    table=load_table, 
                    mode=effective_mode,  # "replace" puis "append"
                    key=None
                )
                
                # Après le premier batch, passer en append
                if not first_batch_written:
                    first_batch_written = True
                    effective_mode = "append"

            duration = time.monotonic() - start
            
            logger.info(
                f"Job '{self.job_id}' completed successfully: "
                f"{rows_in} rows in, {rows_out} rows out, {duration:.2f}s"
            )
            
            return JobResult(
                success=True, 
                rows_in=rows_in, 
                rows_out=rows_out, 
                duration=duration, 
                error=None
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

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _load_yaml_with_resolution(self, path: Path, *, required: bool) -> Dict[str, Any]:
        if not path.exists():
            if required:
                raise ValueError(f"JobExecutor: fichier requis manquant: {path}")
            return {}

        raw_text = path.read_text(encoding="utf-8")
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

    def _resolve_pipeline_ids(self, pipeline_raw: Dict[str, Any]) -> Tuple[str, str]:
        pipe = pipeline_raw.get("pipeline")
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
        sources = getattr(sources_cfg, "sources", None)
        if not isinstance(sources, dict) or src_id not in sources:
            raise ValueError(f"JobExecutor: source inconnue: '{src_id}'")
        return sources[src_id]

    def _get_dest_def(self, dests_cfg: Any, dest_id: str) -> Any:
        dests = getattr(dests_cfg, "destinations", None)
        if not isinstance(dests, dict) or dest_id not in dests:
            raise ValueError(f"JobExecutor: destination inconnue: '{dest_id}'")
        return dests[dest_id]

    def _extract_steps_for_engine(self, transforms_cfg: Any) -> List[Dict[str, Any]]:
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

    def _build_connector(self, name: str, definition: Any, is_source: bool) -> CSVConnector:
        ctype = getattr(definition, "type", None)
        ctype = ctype.strip().lower() if isinstance(ctype, str) else None
        
        if ctype != "csv":
            connector_role = "source" if is_source else "destination"
            raise ValueError(
                f"JobExecutor: {connector_role} '{name}' type='{ctype}' non supporté. "
                f"MVP supporte uniquement 'csv'."
            )

        config = getattr(definition, "connection", None)
        if config is None:
            config = {}

        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()

        if not isinstance(config, dict):
            raise ValueError(f"JobExecutor: connection invalide pour '{name}' (dict attendu)")
        
        return CSVConnector(name=name, config=config, job_dir=str(self.job_dir))

    def _source_extract_params(self, src_def: Any) -> Tuple[str, int, Optional[str]]:
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

        if query is not None and not isinstance(query, str):
            raise ValueError("JobExecutor: source.extract.query invalide (str attendu)")

        return table or "", batch_size, query

    def _dest_load_params(self, dest_def: Any) -> Tuple[str, str]:
        load = getattr(dest_def, "load", None)
        if load is None:
            raise ValueError("JobExecutor: destination.load manquant")

        table = getattr(load, "table", None)
        mode = getattr(load, "mode", "append")

        if not isinstance(table, str) or not table.strip():
            raise ValueError("JobExecutor: destination.load.table manquant ou invalide")

        if not isinstance(mode, str) or not mode.strip():
            raise ValueError("JobExecutor: destination.load.mode invalide")

        mode_norm = mode.strip().lower()

        if mode_norm not in ("append", "replace"):
            raise ValueError(
                f"JobExecutor: destination.load.mode='{mode}' non supporté. "
                f"MVP supporte 'append' ou 'replace' uniquement."
            )

        return table.strip(), mode_norm