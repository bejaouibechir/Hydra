"""DAG « simple » : ce qu'on écrit d'habitude — charger puis transformer."""
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

HOME = Path(__file__).resolve().parents[1]


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def daily_revenue_simple():
    ingest = BashOperator(task_id="ingest", bash_command=f"cd {HOME} && python ingest.py data/orders.csv")
    transform = BashOperator(task_id="transform",
                             bash_command=f"cd {HOME}/dbt && dbt run --profiles-dir . --threads 1")
    ingest >> transform


daily_revenue_simple()
