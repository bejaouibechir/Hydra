"""Exporte les deux rapports calculés par dbt (PostgreSQL) en CSV : python export.py <dossier>"""
import sys
from pathlib import Path

import psycopg2

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
cn = psycopg2.connect(host="localhost", port=5433, user="postgres", password="bench", dbname="bench")
for name in ("revenue_by_country", "revenue_by_month"):
    with open(out / f"{name}.csv", "w") as f, cn.cursor() as cur:
        cur.copy_expert(f"COPY (SELECT * FROM analytics.{name} ORDER BY 1) TO STDOUT WITH CSV HEADER", f)
cn.close()
