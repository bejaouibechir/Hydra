"""DAG « simple » : synchroniser (Airbyte), transformer (dbt), exporter."""
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

HOME = Path(__file__).resolve().parents[1]


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False)
def daily_revenue_simple():
    orders = BashOperator(task_id="sync_orders", bash_command=f"cd {HOME} && python airbyte_sync.py orders_main")
    customers = BashOperator(task_id="sync_customers", bash_command=f"cd {HOME} && python airbyte_sync.py customers")
    transform = BashOperator(task_id="transform", bash_command=f"cd {HOME}/dbt && dbt run --profiles-dir . --threads 1")
    export = BashOperator(task_id="export", bash_command=f"cd {HOME} && python export.py output")
    [orders, customers] >> transform >> export


daily_revenue_simple()
