#!/usr/bin/env python
"""
perf_bench.py — banc de mesure des jobs de reference (S1 CSV filter,
S2 JSON->CSV, S3 aggregate) sur volume realiste.

    python bench/perf_bench.py --rows 1000000 --scenarios s1,s2,s3
    python bench/perf_bench.py --rows 200000 --profile

Genere les donnees une seule fois dans bench/_data/, construit des jobs
temporaires dans bench/_jobs/, et chronometre chaque job (hors import).
Les chiffres servent a comparer un avant/apres : lancer sur la meme
machine, sans autre charge.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Donnees et jobs temporaires hors du depot (HYDRA_BENCH_DIR pour choisir).
import tempfile

BENCH_DIR = Path(os.environ.get("HYDRA_BENCH_DIR") or (Path(tempfile.gettempdir()) / "hydra_bench"))
DATA = BENCH_DIR / "data"
JOBS = BENCH_DIR / "jobs"

CATEGORIES = ["electronics", "books", "toys", "garden", "sport"]
STATUSES = ["completed", "pending", "cancelled"]
COUNTRIES = ["FR", "DE", "ES", "IT", "BE"]


def gen_csv(path: Path, rows: int) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    rnd = random.Random(42)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("order_id,customer_id,product,category,unit_price,qty,status,order_date,country,note\n")
        for i in range(1, rows + 1):
            f.write(
                f"{i},{rnd.randint(1, 50000)},product_{i % 997},{rnd.choice(CATEGORIES)},"
                f"{rnd.randint(100, 99999) / 100:.2f},{rnd.randint(1, 20)},{rnd.choice(STATUSES)},"
                f"2026-0{rnd.randint(1, 9)}-{rnd.randint(10, 28)},{rnd.choice(COUNTRIES)},"
                f"note libre {i}\n"
            )


def gen_json(path: Path, rows: int) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    rnd = random.Random(43)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("[\n")
        for i in range(1, rows + 1):
            rec = {
                "order_id": i,
                "customer_id": rnd.randint(1, 50000),
                "product": f"product_{i % 997}",
                "category": rnd.choice(CATEGORIES),
                "unit_price": round(rnd.randint(100, 99999) / 100, 2),
                "qty": rnd.randint(1, 20),
                "status": rnd.choice(STATUSES),
                "order_date": f"2026-0{rnd.randint(1, 9)}-{rnd.randint(10, 28)}",
                "country": rnd.choice(COUNTRIES),
            }
            f.write(json.dumps(rec) + (",\n" if i < rows else "\n"))
        f.write("]\n")


def write_job(name: str, sources: str, dests: str, transforms: str) -> Path:
    d = JOBS / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "sources.yaml").write_text(sources, encoding="utf-8")
    (d / "destinations.yaml").write_text(dests, encoding="utf-8")
    (d / "transformations.yaml").write_text(transforms, encoding="utf-8")
    (d / "pipeline.yaml").write_text(
        'version: "1.0"\npipeline:\n  name: bench\n  from: src\n  to: dst\n', encoding="utf-8"
    )
    (d / "output").mkdir(exist_ok=True)
    return d


def build_jobs(batch_size) -> dict:
    """batch_size=None : ne pas declarer batch_size (reglage automatique)."""
    csv_in = (DATA / "sales.csv").as_posix()
    json_in = (DATA / "sales.json").as_posix()

    bs_line = f'      batch_size: {batch_size}\n' if batch_size else ''
    src_csv = (
        'version: "1.0"\nsources:\n  src:\n    type: csv\n    connection: {}\n'
        f'    extract:\n      table: {csv_in}\n' + bs_line
    )
    src_json = (
        'version: "1.0"\nsources:\n  src:\n    type: json\n    connection: {}\n'
        f'    extract:\n      table: {json_in}\n' + bs_line
    )

    def dst(fname: str) -> str:
        return (
            'version: "1.0"\ndestinations:\n  dst:\n    type: csv\n    connection: {}\n'
            f'    load:\n      table: ./output/{fname}\n      mode: replace\n'
        )

    s1_t = """version: "1.0"
transformations:
  steps:
    - cast:
        mapping: {order_id: int, unit_price: float, qty: int}
    - filter:
        expr: "status == 'completed'"
    - calculate:
        column: revenue
        expr: "unit_price * qty"
    - rename:
        mapping: {customer_id: client_id, unit_price: price}
    - select:
        columns: [order_id, client_id, product, category, price, qty, revenue, order_date, country]
"""
    s2_t = """version: "1.0"
transformations:
  steps:
    - cast:
        mapping: {unit_price: float, qty: int}
    - calculate:
        column: revenue
        expr: "unit_price * qty"
    - select:
        columns: [order_id, customer_id, product, category, revenue, country]
"""
    s3_t = """version: "1.0"
transformations:
  steps:
    - cast:
        mapping: {unit_price: float, qty: int}
    - calculate:
        column: revenue
        expr: "unit_price * qty"
    - aggregate:
        by: [category]
        agg:
          total_revenue: {func: sum, col: revenue}
          order_count: {func: count, col: order_id}
"""
    return {
        "s1": write_job("s1", src_csv, dst("s1_out.csv"), s1_t),
        "s2": write_job("s2", src_json, dst("s2_out.csv"), s2_t),
        "s3": write_job("s3", src_csv, dst("s3_out.csv"), s3_t),
    }


def run_job(job_dir: Path, profile: bool):
    from hydra_etl.internal.runner.executor import JobExecutor

    t0 = time.perf_counter()
    res = JobExecutor(job_dir=job_dir, profile=profile or None).run()
    return time.perf_counter() - t0, res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--batch-size", type=int, default=10_000,
                    help="0 = ne pas declarer batch_size (reglage automatique)")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--scenarios", default="s1,s2,s3")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--clean", action="store_true", help="regenere les donnees")
    args = ap.parse_args()

    if args.clean and DATA.exists():
        shutil.rmtree(DATA)

    print(f"Generation des donnees ({args.rows:,} lignes)...".replace(",", " "))
    gen_csv(DATA / "sales.csv", args.rows)
    gen_json(DATA / "sales.json", args.rows)

    jobs = build_jobs(args.batch_size or None)
    wanted = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    import logging
    logging.disable(logging.INFO if not args.profile else logging.NOTSET)
    if args.profile:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    print(f"\n{'scenario':<10} {'median':>9} {'min':>9}   rows_in -> rows_out"
          + (f"   [{args.label}]" if args.label else ""))
    results = {}
    for name in wanted:
        times = []
        res = None
        for _ in range(args.repeat):
            dt, res = run_job(jobs[name], args.profile)
            if not res.success:
                print(f"{name:<10} ECHEC: {res.error}")
                break
            times.append(dt)
        if not times:
            continue
        med = statistics.median(times)
        results[name] = med
        print(f"{name:<10} {med:>8.3f}s {min(times):>8.3f}s   {res.rows_in} -> {res.rows_out}")
        if args.profile and res.profile:
            from hydra_etl.internal.runner.profiler import format_profile
            print(format_profile(res.profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
