"""Génère customers.csv et orders.csv avec N commandes (même forme que le banc)."""
import csv, random, sys
from pathlib import Path
n, out = int(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
rnd = random.Random(42)
countries = ["FR", "TN", "ES", "DE", "IT", "MA", "BE", "CA"]
with open(out / "customers.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["customer_id", "name", "country"])
    for c in range(1, 2001):
        w.writerow([c, f"customer {c}", rnd.choice(countries)])
st = ["paid", "paid", "paid", "refunded"]
with open(out / "orders.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["order_id", "customer_id", "order_date", "amount", "status"])
    rows = []
    for o in range(1, n + 1):
        rows.append((o, rnd.randint(1, 2000), f"2026-{rnd.randint(1, 9):02d}-{rnd.randint(1, 28):02d}",
                     f"{rnd.uniform(5, 500):.2f}", st[rnd.randrange(4)]))
        if len(rows) == 100_000:
            w.writerows(rows); rows = []
    w.writerows(rows)
