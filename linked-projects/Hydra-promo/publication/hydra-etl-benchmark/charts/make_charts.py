"""Charts for the Hydra ETL vs Airflow + dlt + dbt vs Airflow + Airbyte + dbt comparison.

Reads results/phase*/scenarios_*.json; other figures (install, lines of code) are
copied from results/phase*/install.json, extra.json and lines_*.txt.
Usage: python make_charts.py <results dir> <output dir>
"""
import json
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

RES = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "charts")
OUT.mkdir(parents=True, exist_ok=True)

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
STACKS = [
    ("phase1_hydra", "Hydra ETL", "#2a78d6"),
    ("phase2_airflow_dlt_dbt", "Airflow + dlt + dbt", "#eb6834"),
    ("phase3_airflow_airbyte_dbt", "Airflow + Airbyte + dbt", "#1baf7a"),
]
SCEN = [("normal", "Normal"), ("missing_source", "Missing source"),
        ("bad_amount", "Unreadable amount"), ("bad_date", "Impossible date")]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})
FOOT = "200,000 orders · one EC2 machine (4 vCPU, 15 GB) · Oct 28, 2026"


def load(phase, variant):
    rows = json.loads((RES / phase / f"scenarios_{variant}.json").read_text())
    out = {}
    for r in rows:
        out.setdefault(r["scenario"], []).append(r)
    return out


def finish(fig, name, note=FOOT):
    fig.text(0.01, 0.015, note, color=MUTED, fontsize=9)
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)
    print("wrote", OUT / name)


def clean(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)


# 1. Outcomes ------------------------------------------------------------------
STATE = {  # label, fill, text colour
    "today": ("✓ Today", "#0ca30c", "white"),
    "backup": ("✓ Backup", "#9fd89f", INK),
    "unchanged": ("Unchanged", "#e6e5e1", INK2),
    "inconsistent": ("✗ Inconsistent", "#d03b3b", "white"),
}


def state(r):
    a, b = r["revenue_by_country"], r["revenue_by_month"]
    if a != b:
        return "inconsistent"
    return {"main": "today", "backup": "backup"}.get(a, "unchanged")


fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
for ax, variant, title in zip(axes, ("simple", "safe"),
                              ("Without protection", "With protections")):
    ax.set_xlim(0, 3); ax.set_ylim(0, 4); ax.invert_yaxis(); ax.axis("off")
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=34)
    for j, (phase, name, _) in enumerate(STACKS):
        ax.text(j + 0.5, -0.12, name.replace(" + ", "\n+ ", 1) if j else name,
                ha="center", va="bottom", fontsize=9.5, color=INK2)
        data = load(phase, variant)
        for i, (key, _) in enumerate(SCEN):
            label, fill, txt = STATE[state(data[key][0])]
            ax.add_patch(FancyBboxPatch((j + 0.06, i + 0.08), 0.88, 0.84,
                                        boxstyle="round,pad=0,rounding_size=0.06",
                                        fc=fill, ec=SURFACE, lw=2))
            ax.text(j + 0.5, i + 0.5, label, ha="center", va="center",
                    color=txt, fontsize=10.5, fontweight="bold")
for i, (_, lab) in enumerate(SCEN):
    axes[0].text(-0.08, i + 0.5, lab, ha="right", va="center", fontsize=10.5)
fig.suptitle("What the two reports contain after each failure",
             x=0.01, ha="left", fontsize=15, fontweight="bold")
fig.subplots_adjust(left=0.15, right=0.99, top=0.78, bottom=0.12, wspace=0.08)
finish(fig, "outcomes.png", FOOT + "  ·  Inconsistent = one report from today, the other from two days ago")

# 2. Run time ------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5.2))
h = 0.26
for j, (phase, name, color) in enumerate(STACKS):
    data = load(phase, "safe")
    for i, (key, _) in enumerate(SCEN):
        v = statistics.median(r["seconds"] for r in data[key])
        y = i + (j - 1) * (h + 0.03)
        ax.hlines(y, 0.8, v, color=GRID, lw=2, zorder=1)
        ax.plot(v, y, "o", ms=11, color=color, mec=SURFACE, mew=2, zorder=3,
                label=name if i == 0 else None)
        txt = f"{v:.1f} s" if v < 60 else f"{v / 60:.1f} min"
        ax.text(v * 1.13, y, txt, va="center", fontsize=9.5, color=INK2)
ax.set_xscale("log")
ax.set_xlim(0.8, 600)
ax.set_xticks([1, 10, 60, 300]); ax.set_xticklabels(["1 s", "10 s", "1 min", "5 min"])
ax.set_yticks(range(4)); ax.set_yticklabels([s for _, s in SCEN])
ax.invert_yaxis()
ax.grid(axis="x", color=GRID, lw=0.8, ls=":"); ax.set_axisbelow(True)
clean(ax)
ax.legend(loc="upper center", bbox_to_anchor=(0.45, 1.13), ncol=3, frameon=False, numpoints=1)
fig.suptitle("End-to-end run time, with protections (log scale)",
             x=0.01, ha="left", fontsize=15, fontweight="bold")
fig.subplots_adjust(left=0.17, right=0.97, top=0.82, bottom=0.12)
finish(fig, "run-time.png",
       FOOT + "  ·  median of 3 runs (1 run for Airbyte)  ·  Airflow via `airflow dags test`")

# 3. Footprint -----------------------------------------------------------------
names = [n for _, n, _ in STACKS]
colors = [c for _, _, c in STACKS]
fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
panels = [
    ("Python packages", [15, 170, 162], lambda v: f"{v:g}"),
    ("Disk (GB)", [0.189, 0.922, 0.531], lambda v: f"{v:.2f}"),
    ("Memory at rest (GB)", [0, 0, 3.7], lambda v: f"{v:g}"),
]
for ax, (title, vals, fmt) in zip(axes, panels):
    xs = range(3)
    ax.bar(xs, vals, color=colors, width=0.62)
    top = max(vals)
    if title.startswith("Disk"):
        ax.bar(2, 8.879, bottom=0.531, color=colors[2], alpha=0.45, width=0.62,
               hatch="///", edgecolor=SURFACE, lw=0)
        ax.text(2, 0.531 + 8.879 + 0.25, "0.53 + 8.9\nof Docker images", ha="center",
                va="bottom", fontsize=9, color=INK2)
        top = 9.41
        for x in (0, 1):
            ax.text(x, vals[x] + 0.25, fmt(vals[x]), ha="center", va="bottom", fontsize=10)
    else:
        for x, v in zip(xs, vals):
            label = fmt(v) + ("\n(18 containers)" if title.startswith("Memory") and v else "")
            ax.text(x, v + top * 0.03, label, ha="center", va="bottom", fontsize=10)
    ax.set_ylim(0, top * 1.38)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.set_xticks(list(xs)); ax.set_xticklabels(["Hydra ETL", "Airflow\n+ dlt + dbt", "Airflow\n+ Airbyte + dbt"], fontsize=9.5)
    ax.set_yticks([])
    clean(ax)
fig.suptitle("What it costs to install and keep running",
             x=0.01, ha="left", fontsize=15, fontweight="bold")
fig.subplots_adjust(left=0.02, right=0.99, top=0.8, bottom=0.17, wspace=0.12)
finish(fig, "footprint.png", FOOT + "  ·  Airflow run with `airflow dags test` (no scheduler at rest)")

# 4. Lines of code -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 4.8))
simple, safe, api = [76, 78, 107], [97, 104, 131], [0, 0, 58]
w = 0.36
for x in range(3):
    ax.bar(x - w / 2 - 0.01, simple[x], width=w, color="#c3c2b7",
           label="Without protection" if x == 0 else None)
    ax.bar(x + w / 2 + 0.01, safe[x], width=w, color=colors[x],
           label=None)
    ax.text(x - w / 2 - 0.01, simple[x] + 3, str(simple[x]), ha="center", va="bottom", fontsize=10, color=INK2)
    ax.text(x + w / 2 + 0.01, safe[x] - 4 if api[x] else safe[x] + 3, str(safe[x]), ha="center",
            va="top" if api[x] else "bottom", fontsize=10, color="white" if api[x] else INK)
    ax.text(x - w / 2 - 0.01, 6, "without\nprotection", ha="center", fontsize=8.5, color=INK2)
    ax.text(x + w / 2 + 0.01, 6, "with\nprotections", ha="center", fontsize=8.5, color="white")
    if api[x]:
        ax.bar(x + w / 2 + 0.01, api[x], bottom=safe[x], width=w, color=colors[x],
               alpha=0.4, hatch="///", edgecolor=SURFACE, lw=0)
        ax.text(x + w / 2 + 0.01 + w / 2 + 0.04, safe[x] + api[x] / 2,
                "+ 58 lines of\nAirbyte API setup", va="center", fontsize=9, color=INK2)
        ax.text(x + w / 2 + 0.01, safe[x] + api[x] + 3, str(safe[x] + api[x]),
                ha="center", fontsize=10)
ax.set_xticks(range(3)); ax.set_xticklabels(names)
ax.set_xlim(-0.6, 2.95)
ax.set_ylim(0, 215); ax.set_yticks([])
clean(ax)
fig.suptitle("Useful lines of code (no blank lines, no comments)",
             x=0.01, ha="left", fontsize=15, fontweight="bold")
fig.subplots_adjust(left=0.03, right=0.99, top=0.84, bottom=0.12)
finish(fig, "lines-of-code.png",
       "Hydra ETL: YAML  ·  Airflow stacks: Python, SQL and YAML  ·  comparable volume, different nature")
