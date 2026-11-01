"""Données du comparatif : clients et commandes (déterministes, graine fixe)."""
import csv, random, sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
out.mkdir(parents=True, exist_ok=True)
rnd = random.Random(42)
countries = ["FR", "TN", "ES", "DE", "IT", "MA", "BE", "CA"]
with open(out / "customers.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["customer_id", "name", "country"])
    for c in range(1, 2001):
        w.writerow([c, f"customer {c}", rnd.choice(countries)])
with open(out / "orders.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "customer_id", "order_date", "amount", "status"])
    for o in range(1, 200_001):
        w.writerow([o, rnd.randint(1, 2000), f"2026-{rnd.randint(1, 9):02d}-{rnd.randint(1, 28):02d}",
                    f"{rnd.uniform(5, 500):.2f}", rnd.choice(["paid", "paid", "paid", "refunded"])])
with open(out / "orders.csv", newline="") as f:
    lines = f.readlines()
with open(out / "orders_backup.csv", "w", newline="") as f:
    f.writelines(lines[:199_001])
print("ok", out)
