"""Compte rendu brut : rassemble les résultats des phases en tableaux Markdown.

  python report.py <dossier results>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PHASES = [("phase1_hydra", "Hydra ETL"), ("phase2_airflow_dlt_dbt", "Airflow + dlt + dbt"),
          ("phase3_airflow_airbyte_dbt", "Airflow + Airbyte + dbt")]
SCEN = ["normal", "missing_source", "bad_amount", "bad_date"]


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def total_lines(p: Path):
    try:
        last = p.read_text().strip().splitlines()[-1].split()
        return f"{last[0]} lignes, {last[2].strip('(')} fichiers"
    except Exception:  # noqa: BLE001
        return "—"


def runs(rows):
    out = {}
    for sc in SCEN:
        rs = [r for r in rows or [] if r["scenario"] == sc]
        if not rs:
            out[sc] = "—"
            continue
        secs = sorted(r["seconds"] for r in rs)
        outs = sorted({f"{r['revenue_by_country']}/{r['revenue_by_month']}" for r in rs})
        ok = "✓" if all(r["consistent"] for r in rs) else "⚠ incohérent"
        out[sc] = f"{', '.join(outs)} {ok} ({secs[len(secs) // 2]} s)"
    return out


def peak_by_phase(res: Path):
    """Mémoire maximale observée pendant les étapes de chaque phase (metrics.csv)."""
    peaks = {}
    try:
        with open(res / "metrics.csv") as f:
            for row in csv.DictReader(f):
                ph = row["step"].split(".")[0]
                if ph.isdigit():
                    peaks[ph] = max(peaks.get(ph, 0.0), float(row["mem_used_mb"]))
    except Exception:  # noqa: BLE001
        pass
    return peaks


def main() -> int:
    res = Path(sys.argv[1])
    m = load(res / "machine.json") or {}
    peaks = peak_by_phase(res)
    L = ["# Compte rendu brut du banc", "",
         f"Machine : {m.get('os', '?')}, {m.get('cpus', '?')} processeurs, {m.get('mem_gb', '?')} Go, "
         f"Python {m.get('python', '?')}.", "",
         "## Installation", "", "| Pile | Durée | Paquets Python | Taille env. | Mémoire max (phase) | Autres |",
         "|---|---|---|---|---|---|"]
    for i, (ph, name) in enumerate(PHASES, 1):
        ins = load(res / ph / "install.json") or {}
        extra = load(res / ph / "extra.json") or {}
        other = ", ".join(f"{k}: {v}" for k, v in extra.items()) or "—"
        peak = f"{peaks[str(i)]:.0f} Mo" if str(i) in peaks else "—"
        sec = f"{ins['install_seconds']} s" if "install_seconds" in ins else "—"
        size = f"{ins['env_size_mb']:.0f} Mo" if "env_size_mb" in ins else "—"
        L.append(f"| {name} | {sec} | {ins.get('packages', '—')} | {size} | {peak} | {other} |")
    L += ["", "## Code écrit (lignes utiles)", "", "| Pile | Simple | Sûre |", "|---|---|---|"]
    for ph, name in PHASES:
        L.append(f"| {name} | {total_lines(res / ph / 'lines_simple.txt')} | "
                 f"{total_lines(res / ph / 'lines_safe.txt')} |")
    for variant in ("simple", "safe"):
        L += ["", f"## Pannes — variante {'simple' if variant == 'simple' else 'sûre'}",
              "", "Sorties pays/mois, cohérence, médiane des durées.", "",
              "| Scénario | " + " | ".join(n for _, n in PHASES) + " |",
              "|---" * (len(PHASES) + 1) + "|"]
        cols = [runs(load(res / ph / f"scenarios_{variant}.json")) for ph, _ in PHASES]
        for sc in SCEN:
            L.append(f"| {sc} | " + " | ".join(c[sc] for c in cols) + " |")
    st = load(res / "state.json") or {}
    L += ["", "## Durée des étapes", "", "| Étape | Statut | Durée |", "|---|---|---|"]
    for k in sorted(st, key=lambda x: [int(p) for p in x.split(".")]):
        L.append(f"| {k} | {st[k].get('status')} | {st[k].get('seconds', '—')} s |")
    (res / "COMPTE-RENDU-BRUT.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
