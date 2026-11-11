"""DAG « sûr » : mêmes garanties que le thread Hydra ETL — secours si la source
manque ou si le calcul échoue, sorties publiées en tout ou rien."""
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

HOME = Path(__file__).resolve().parents[1]
OUTPUTS = ["revenue_by_country.csv", "revenue_by_month.csv"]


def build(task_id: str, orders: str, stage: str) -> BashOperator:
    """Charge `orders` puis calcule les rapports dans un dossier de travail."""
    return BashOperator(
        task_id=task_id,
        execution_timeout=timedelta(minutes=10),
        bash_command=(f"cd {HOME} && rm -rf {stage} && mkdir -p {stage} && python ingest.py {orders} "
                      f"&& cd dbt && dbt run --profiles-dir . --threads 1 "
                      f"--vars '{{out_dir: {stage}}}'"),
    )


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def daily_revenue_safe():
    @task
    def clean():
        shutil.rmtree(HOME / "staging", ignore_errors=True)

    main = build("build_main", "data/orders.csv", f"{HOME}/staging/main")
    # secours : seulement si build_main échoue (source absente, données illisibles…)
    backup = build("build_backup", "data/backup/orders.csv", f"{HOME}/staging/backup")
    backup.trigger_rule = "one_failed"

    @task(trigger_rule="one_success")
    def publish():
        """Publie les deux sorties d'un même run, ou rien."""
        for stage in ("main", "backup"):
            d = HOME / "staging" / stage
            if all((d / f).exists() for f in OUTPUTS):
                for f in OUTPUTS:            # copie à côté puis renommage atomique
                    shutil.copy(d / f, HOME / "output" / (f + ".tmp"))
                for f in OUTPUTS:
                    os.replace(HOME / "output" / (f + ".tmp"), HOME / "output" / f)
                return stage
        raise RuntimeError("no complete set of reports to publish")

    clean() >> main >> backup
    [main, backup] >> publish()


daily_revenue_safe()
