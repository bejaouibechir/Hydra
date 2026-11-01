"""DAG « sûr » : secours si la synchronisation ou le calcul échoue, sorties
publiées en tout ou rien."""
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

HOME = Path(__file__).resolve().parents[1]
OUTPUTS = ["revenue_by_country.csv", "revenue_by_month.csv"]


def build(task_id: str, connection: str, stage: str) -> BashOperator:
    return BashOperator(
        task_id=task_id,
        execution_timeout=timedelta(minutes=30),
        bash_command=(f"cd {HOME} && python airbyte_sync.py {connection} && python airbyte_sync.py customers "
                      f"&& (cd dbt && dbt run --profiles-dir . --threads 1) && python export.py {stage}"),
    )


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def daily_revenue_safe():
    @task
    def clean():
        shutil.rmtree(HOME / "staging", ignore_errors=True)

    main = build("build_main", "orders_main", f"{HOME}/staging/main")
    backup = build("build_backup", "orders_backup", f"{HOME}/staging/backup")
    backup.trigger_rule = "one_failed"

    @task(trigger_rule="one_success")
    def publish():
        """Publie les deux sorties d'un même run, ou rien."""
        for stage in ("main", "backup"):
            d = HOME / "staging" / stage
            if all((d / f).exists() for f in OUTPUTS):
                for f in OUTPUTS:
                    shutil.copy(d / f, HOME / "output" / (f + ".tmp"))
                for f in OUTPUTS:
                    os.replace(HOME / "output" / (f + ".tmp"), HOME / "output" / f)
                return stage
        raise RuntimeError("no complete set of reports to publish")

    clean() >> main >> backup
    [main, backup] >> publish()


daily_revenue_safe()
