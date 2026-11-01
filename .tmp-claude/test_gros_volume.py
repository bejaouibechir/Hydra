"""Prépare un test du moteur gros volumes de Hydra ETL.

    python test_gros_volume.py 5000000

Crée le dossier gros-volume/ :
  data/orders.csv      N commandes (≈ 45 Mo par million de lignes)
  data/customers.csv   2 000 clients
  jobs/revenue_by_country/   filter → cast → join → aggregate → sort
  output/              résultat (revenue_by_country.csv)
"""
import random
import sys
from pathlib import Path

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5_000_000
root = Path("gros-volume")
(root / "data").mkdir(parents=True, exist_ok=True)
(root / "output").mkdir(exist_ok=True)
job = root / "jobs" / "revenue_by_country"
job.mkdir(parents=True, exist_ok=True)

rnd = random.Random(42)
countries = ["FR", "TN", "ES", "DE", "IT", "MA", "BE", "CA"]
with open(root / "data" / "customers.csv", "w", newline="", encoding="utf-8") as f:
    f.write("customer_id,name,country\n")
    for c in range(1, 2001):
        f.write(f"{c},customer {c},{rnd.choice(countries)}\n")

status = ["paid", "paid", "paid", "refunded"]
with open(root / "data" / "orders.csv", "w", newline="", encoding="utf-8") as f:
    f.write("order_id,customer_id,order_date,amount,status\n")
    buf = []
    for o in range(1, n + 1):
        buf.append(f"{o},{rnd.randint(1, 2000)},2026-{rnd.randint(1, 9):02d}-{rnd.randint(1, 28):02d},"
                   f"{rnd.uniform(5, 500):.2f},{status[rnd.randrange(4)]}\n")
        if len(buf) == 100_000:
            f.writelines(buf)
            buf = []
            print(f"\r{o:,} / {n:,} lignes".replace(",", " "), end="", flush=True)
    f.writelines(buf)
print()

files = {
    "sources.yaml": """sources:
  orders:
    type: csv
    extract:
      table: ../../data/orders.csv
  customers:
    type: csv
    extract:
      table: ../../data/customers.csv
""",
    "destinations.yaml": """destinations:
  report:
    type: csv
    load:
      table: ../../output/revenue_by_country.csv
      mode: replace
""",
    "pipeline.yaml": """pipeline:
  from: orders
  to: report
""",
    "transformations.yaml": """steps:
  - filter: {expr: "status == 'paid'"}
  - cast: {mapping: {amount: float}}
  - join: {right: customers, key: customer_id, how: inner}
  - aggregate:
      by: [country]
      agg:
        revenue: {func: sum, col: amount}
        orders: {func: count, col: order_id}
  - sort: {by: [country]}
""",
}
for name, text in files.items():
    (job / name).write_text(text, encoding="utf-8")
print(f"Prêt : {root.resolve()}")
