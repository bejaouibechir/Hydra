"""Write outputs/summary.md from the top customers ranking."""
import csv
import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
rows = list(csv.DictReader(open(root / "outputs" / "top_customers.csv", encoding="utf-8")))
lines = [f"# Top customers — {os.environ.get('run_date', '')}", "",
         "| Rank | Customer | Country | Orders | Revenue |", "|---|---|---|---|---|"]
for r in rows:
    lines.append(f"| {r['rank']} | {r['name']} | {r['country']} | {r['orders']} | {float(r['revenue']):,.2f} |")
(root / "outputs" / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"summary.md written: {len(rows)} customers")
