"""Reads the report Hydra just produced and prints a one-line summary."""
import csv, glob, os

reports = sorted(glob.glob("output/report_*.csv"))
if not reports:
    raise SystemExit("no report found - did export-report run?")

for path in reports:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total = sum(float(r["amount"]) for r in rows)
    by_region = {}
    for r in rows:
        by_region[r["region"]] = by_region.get(r["region"], 0) + 1
    regions = ", ".join(f"{k}={v}" for k, v in sorted(by_region.items()))
    print(f"{os.path.basename(path)}: {len(rows)} orders, total {total:,.2f} ({regions})")
