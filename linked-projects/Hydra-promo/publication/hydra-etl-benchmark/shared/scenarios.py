"""Rejoue les mêmes pannes sur une pile (Hydra ETL ou dlt + dbt + Airflow) et
dit, pour chaque sortie, de quelle version des données elle vient.

  python scenarios.py <dossier de la pile> "<commande de lancement>"

Versions attendues, calculées ici avec pandas (indépendamment des piles) :
  previous : export de l'avant-veille (198 000 commandes) — état avant le run
  backup   : export de secours (199 000 commandes, data/backup/orders.csv)
  main     : export du jour (200 000 commandes, data/orders.csv)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SRC = HERE / "data"
OUTPUTS = ["revenue_by_country", "revenue_by_month"]


def reports(orders: pd.DataFrame) -> dict:
    cust = pd.read_csv(SRC / "customers.csv")
    paid = orders[orders.status == "paid"]
    by_c = (paid.merge(cust, on="customer_id").groupby("country")
            .agg(revenue=("amount", "sum"), orders=("order_id", "count")).reset_index())
    m = paid.assign(month=paid.order_date.str.slice(0, 7))
    by_m = m.groupby("month").agg(revenue=("amount", "sum")).reset_index()
    return {"revenue_by_country": by_c, "revenue_by_month": by_m}


def fingerprint(df: pd.DataFrame) -> tuple:
    d = df.copy()
    d["revenue"] = d["revenue"].astype(float).round(2)
    return tuple(map(tuple, d.sort_values(list(d.columns[:1])).astype(str).values))


def versions() -> dict:
    full = pd.read_csv(SRC / "orders.csv")
    return {"main": reports(full), "backup": reports(full.head(199_000)),
            "previous": reports(full.head(198_000))}


def label(path: Path, vers: dict, name: str) -> str:
    if not path.exists():
        return "missing"
    try:
        fp = fingerprint(pd.read_csv(path))
    except Exception as e:  # noqa: BLE001
        return f"unreadable ({type(e).__name__})"
    for v, rep in vers.items():
        if fp == fingerprint(rep[name]):
            return v
    return "other"


def prepare(stack: Path, vers: dict, scenario: str) -> None:
    data, out = stack / "data", stack / "output"
    (data / "backup").mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    shutil.copy(SRC / "customers.csv", data / "customers.csv")
    shutil.copy(SRC / "orders.csv", data / "orders.csv")
    shutil.copy(SRC / "orders_backup.csv", data / "backup" / "orders.csv")
    for n in OUTPUTS:                      # état de départ : le run de l'avant-veille
        vers["previous"][n].to_csv(out / f"{n}.csv", index=False)
    lines = (data / "orders.csv").read_text().splitlines(keepends=True)
    if scenario == "missing_source":
        (data / "orders.csv").unlink()
    elif scenario == "bad_amount":       # un montant illisible : la 1re sortie échoue
        lines[150_000] = lines[150_000].rsplit(",", 2)[0] + ",abc,paid\n"
        (data / "orders.csv").write_text("".join(lines))
    elif scenario == "bad_date":         # une date impossible : seule la 2e sortie échoue
        p = lines[150_000].split(",")
        p[2], p[4] = "2026-13-45", "paid\n"
        lines[150_000] = ",".join(p)
        (data / "orders.csv").write_text("".join(lines))


def main() -> int:
    """scenarios.py <pile> "<commande>" [--repeat N] [--out fichier.json]
    Affiche « PROGRESS i/n » après chaque run (lu par run.py pour la barre)."""
    args = sys.argv[1:]
    repeat, out = 1, None
    if "--repeat" in args:
        i = args.index("--repeat"); repeat = int(args[i + 1]); del args[i:i + 2]
    if "--out" in args:
        i = args.index("--out"); out = Path(args[i + 1]); del args[i:i + 2]
    stack, cmd = Path(args[0]).resolve(), args[1]
    vers = versions()
    scenarios = ["normal", "missing_source", "bad_amount", "bad_date"]
    total, done, rows = len(scenarios) * repeat, 0, []
    for sc in scenarios:
        for k in range(1, repeat + 1):
            prepare(stack, vers, sc)
            t0 = time.monotonic()
            p = subprocess.run(["bash", "-c", cmd], cwd=stack, capture_output=True, text=True)
            dt = time.monotonic() - t0
            got = {n: label(stack / "output" / f"{n}.csv", vers, n) for n in OUTPUTS}
            rows.append({"scenario": sc, "run": k, "exit_code": p.returncode, "seconds": round(dt, 2),
                         **got, "consistent": len(set(got.values())) == 1})
            (stack / f"log_{sc}_{k}.txt").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr)
            done += 1
            print(f"PROGRESS {done}/{total} {sc} #{k} {dt:.1f}s {got}", flush=True)
    text = json.dumps(rows, indent=1)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
