"""
etl/engine.py — API publique Hydra (façade stable).

Rôle : wrapper fin autour de internal/runner/executor.py.
       Isole les consommateurs externes (scripts, notebooks, tests d'intégration)
       des détails d'implémentation de internal/*.

Usage recommandé pour les intégrations externes :
    from hydra_etl.etl.engine import Engine
    result = Engine().run(job_dir="./jobs/my_job")

La CLI (hdrctl) et le workflow runner utilisent JobExecutor directement
pour des raisons de performance et de contrôle fin.
etl.Engine reste la surface publique stable pour les autres consommateurs.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Optional, Union

from hydra_etl.etl.types import JobResult


class Engine:
    """
    Engine public Hydra.

    Usage :
        from hydra_etl.etl.engine import Engine
        result = Engine().run(job_dir="tests/fixtures/job_minimal_ok")
    """

    def run(
        self,
        *,
        job_dir: Union[str, Path],
        root_dir: Optional[Union[str, Path]] = None,
        override_os: bool = True,
    ) -> JobResult:
        """
        Exécute un job Hydra depuis un répertoire (job_dir).

        Paramètres :
            job_dir :
                Dossier job contenant les fichiers YAML attendus par Hydra.

            root_dir :
                Dossier racine projet (optionnel).
                Si fourni, permet le chargement d'un .env global (root) + .env job.

            override_os :
                True  : les variables .env peuvent écraser os.environ
                False : os.environ garde priorité (les .env ne surchargent pas)

        Retour :
            JobResult (success, rows_in, rows_out, duration, error)
        """
        # Import local pour garder etl/* "clean" et stable
        from hydra_etl.internal.runner.executor import JobExecutor

        job_path = Path(job_dir).expanduser().resolve()
        if not job_path.exists() or not job_path.is_dir():
            raise ValueError(f"Engine.run: job_dir invalide: {str(job_path)!r}")

        root_path: Optional[Path] = None
        if root_dir is not None:
            root_path = Path(root_dir).expanduser().resolve()
            if not root_path.exists() or not root_path.is_dir():
                raise ValueError(f"Engine.run: root_dir invalide: {str(root_path)!r}")

        # IMPORTANT : le JobExecutor attend 'override_os' (pas override_os_env)
        executor = JobExecutor(job_dir=job_path, root_dir=root_path, override_os=override_os)
        return executor.run()

    @staticmethod
    def to_dict(result: JobResult) -> dict:
        """
        Convertit un JobResult en dict sérialisable.

        Utile pour la sortie JSON côté CLI.
        """
        return asdict(result)
