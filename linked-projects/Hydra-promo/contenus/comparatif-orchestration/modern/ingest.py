"""Chargement des CSV dans DuckDB avec dlt (couche « EL »)."""
import sys
from pathlib import Path

import dlt
import pandas as pd

ORDERS = sys.argv[1] if len(sys.argv) > 1 else "data/orders.csv"


@dlt.resource(name="orders", write_disposition="replace")
def orders():
    for chunk in pd.read_csv(ORDERS, dtype=str, chunksize=50_000):
        yield chunk                      # DataFrame : chemin rapide (Arrow)


@dlt.resource(name="customers", write_disposition="replace")
def customers():
    yield pd.read_csv("data/customers.csv", dtype=str)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    pipeline = dlt.pipeline(pipeline_name="daily_revenue", dataset_name="raw",
                            destination=dlt.destinations.duckdb(str(here / "warehouse.duckdb")),
                            pipelines_dir=str(here / ".dlt_pipelines"))   # état local au projet
    print(pipeline.run([orders(), customers()]))
