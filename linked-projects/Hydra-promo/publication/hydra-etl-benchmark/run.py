#!/usr/bin/env python3
"""
run.py — banc de comparaison Hydra ETL / Airflow + dlt + dbt / Airflow + Airbyte + dbt.

Lancement (Ubuntu 24.04, depuis ce dossier) :
    python3 run.py                 # tout, avec confirmations
    python3 run.py --phase 1       # une phase (0 préparation, 1, 2, 3, 4 compte rendu)
    python3 run.py --status        # où en est-on
    python3 run.py --redo 2.4      # refaire une étape (et les suivantes de sa phase)
    python3 run.py --yes           # sans confirmation (déconseillé la première fois)

Transparence :
  - confirmation avant chaque étape importante ;
  - barre de progression générale et barre par étape ;
  - points de reprise : chaque étape réussie est notée dans results/state.json.
    En cas d'erreur, relancer `python3 run.py` reprend à l'étape en échec, après
    l'avoir remise à zéro (son « nettoyage »). Rien n'est refait inutilement.
  - journaux : results/logs/<étape>.log ; mémoire et processeur chaque seconde :
    results/metrics.csv.

Uniquement la bibliothèque standard de Python.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
LOGS = RESULTS / "logs"
STATE = RESULTS / "state.json"
ENVS = Path.home() / "bench-envs"
TOOLS_PY = ENVS / "tools" / "bin" / "python"
PYV = f"{sys.version_info.major}.{sys.version_info.minor}"
HYDRA_VERSION = "0.14.0"
AIRFLOW_VERSION = "3.3.2"
REPEAT = 3

# ── Affichage ────────────────────────────────────────────────────────────────
TTY = sys.stdout.isatty()
B, G, R, Y, C, D, X = (("\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m")
                       if TTY else ("",) * 7)


def bar(done: int, total: int, width: int = 30) -> str:
    total = max(total, 1)
    n = int(width * done / total)
    return f"[{'#' * n}{'.' * (width - n)}] {100 * done // total:3d}%"


def fmt_s(s: float) -> str:
    s = int(s)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def ask(question: str, choices: str, default: str, auto: bool) -> str:
    if auto:
        return default
    while True:
        try:
            a = input(f"{Y}?{X} {question} [{choices}] ").strip().lower() or default
        except EOFError:
            return default
        if a and a[0] in choices.replace("/", "").lower():
            return a[0]


# ── État (points de reprise) ─────────────────────────────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_state(st: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    os.replace(tmp, STATE)


# ── Mesure mémoire / processeur ──────────────────────────────────────────────
class Sampler(threading.Thread):
    """Écrit chaque seconde dans results/metrics.csv : mémoire utilisée, processeur, disque."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.step = "idle"
        self.stop_ev = threading.Event()
        self.peak_mb = 0.0
        RESULTS.mkdir(parents=True, exist_ok=True)
        self.path = RESULTS / "metrics.csv"
        if not self.path.exists():
            self.path.write_text("ts,step,mem_used_mb,cpu_pct,disk_used_gb\n")

    @staticmethod
    def _cpu() -> tuple:
        v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        return sum(v), v[3] + v[4]

    @staticmethod
    def _mem_mb() -> float:
        m = {}
        for ln in open("/proc/meminfo"):
            k, val = ln.split(":")
            m[k] = int(val.split()[0])
        return (m["MemTotal"] - m["MemAvailable"]) / 1024

    def run(self) -> None:
        t0, i0 = self._cpu()
        with open(self.path, "a") as f:
            while not self.stop_ev.wait(1.0):
                t1, i1 = self._cpu()
                cpu = 100.0 * (1 - (i1 - i0) / max(t1 - t0, 1))
                t0, i0 = t1, i1
                mem = self._mem_mb()
                self.peak_mb = max(self.peak_mb, mem)
                du = shutil.disk_usage("/")
                f.write(f"{time.time():.0f},{self.step},{mem:.0f},{cpu:.1f},{du.used / 1e9:.2f}\n")
                f.flush()


SAMPLER: Sampler | None = None


# ── Commandes ────────────────────────────────────────────────────────────────
class StepError(RuntimeError):
    pass


def sh(cmd: str, log: Path, cwd: Path = HERE, env: dict | None = None, progress=None) -> str:
    """Lance `cmd` (bash) ; sortie dans `log`. Affiche le temps écoulé et la
    dernière ligne ; `progress(line)` peut renvoyer (fait, total) pour une barre."""
    log.parent.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, **(env or {})}
    out_lines = []
    t0 = time.monotonic()
    with open(log, "a") as lf:
        lf.write(f"\n$ {cmd}\n")
        p = subprocess.Popen(["bash", "-c", cmd], cwd=cwd, env=full_env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
        state = {"last": "", "pr": None}

        def ticker():
            while p.poll() is None:
                el = fmt_s(time.monotonic() - t0)
                pr = f" {bar(*state['pr'], width=20)}" if state["pr"] else ""
                last = re.sub(r"\s+", " ", state["last"])[:60]
                if TTY:
                    print(f"\r    {D}⏱ {el}{X}{pr} {D}{last}{X}\033[K", end="", flush=True)
                time.sleep(1)
        th = threading.Thread(target=ticker, daemon=True)
        th.start()
        for line in p.stdout:
            lf.write(line)
            out_lines.append(line)
            if line.strip():
                state["last"] = line.strip()
            if progress:
                r = progress(line)
                if r:
                    state["pr"] = r
        p.wait()
        th.join(timeout=2)
    if TTY:
        print("\r\033[K", end="")
    if p.returncode != 0:
        tail = "".join(out_lines[-15:])
        raise StepError(f"commande en échec (code {p.returncode}) : {cmd}\n{tail}")
    return "".join(out_lines)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))


def du_mb(path: Path) -> float:
    out = subprocess.run(["du", "-sm", str(path)], capture_output=True, text=True).stdout
    return float(out.split()[0]) if out else 0.0


def venv(name: str) -> Path:
    return ENVS / name


def pip_count(env: Path) -> int:
    out = subprocess.run([str(env / "bin" / "pip"), "list", "--format=freeze"], capture_output=True,
                         text=True).stdout
    return len([ln for ln in out.splitlines() if ln.strip()])


def install_measure(phase: str, name: str, env: Path, commands: list, log: Path) -> dict:
    """Crée un environnement neuf et mesure l'installation (sans cache pip)."""
    shutil.rmtree(env, ignore_errors=True)
    sh(f"python3 -m venv {env} && {env}/bin/pip -q install -U pip", log)
    t0 = time.monotonic()
    for c in commands:
        sh(c.format(pip=f"{env}/bin/pip --no-cache-dir", py=PYV), log)
    secs = time.monotonic() - t0
    res = {"stack": name, "install_seconds": round(secs, 1), "packages": pip_count(env),
           "env_size_mb": du_mb(env), "python": PYV}
    write_json(RESULTS / phase / "install.json", res)
    return res


def scenarios(phase: str, stack: str, cmd: str, out_name: str, log: Path) -> list:
    out = RESULTS / phase / out_name
    def prog(line):
        m = re.match(r"PROGRESS (\d+)/(\d+)", line)
        return (int(m.group(1)), int(m.group(2))) if m else None
    sh(f"{TOOLS_PY} shared/scenarios.py {stack} \"{cmd}\" --repeat {REPEAT} --out {out}", log,
       progress=prog)
    rows = json.loads(out.read_text())
    return rows


def count_lines(phase: str, name: str, cwd: Path, files: str, log: Path) -> None:
    txt = sh(f"{TOOLS_PY} {HERE}/shared/count_lines.py {files}", log, cwd=cwd)
    (RESULTS / phase).mkdir(parents=True, exist_ok=True)
    (RESULTS / phase / f"lines_{name}.txt").write_text(txt)


def summarize_runs(rows: list) -> dict:
    out = {}
    for sc in sorted({r["scenario"] for r in rows}, key=lambda x: ["normal", "missing_source",
                                                                     "bad_amount", "bad_date"].index(x)):
        rs = [r for r in rows if r["scenario"] == sc]
        secs = sorted(r["seconds"] for r in rs)
        out[sc] = {"median_seconds": secs[len(secs) // 2],
                   "outputs": sorted({f"{r['revenue_by_country']}/{r['revenue_by_month']}" for r in rs}),
                   "consistent": all(r["consistent"] for r in rs)}
    return out


# ── Étapes ───────────────────────────────────────────────────────────────────
class Step:
    def __init__(self, sid, title, run, clean=None, confirm=False, note="", hint=""):
        """note : message après la réussite ; hint : conseil affiché en cas d'échec."""
        self.id, self.title, self.run, self.clean, self.confirm = sid, title, run, clean, confirm
        self.note, self.hint = note, hint

    @property
    def phase(self) -> str:
        return self.id.split(".")[0]


def p0_machine(log):
    info = {"cpus": os.cpu_count(), "python": PYV}
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemTotal"):
            info["mem_gb"] = round(int(ln.split()[1]) / 1024 / 1024, 1)
    du = shutil.disk_usage("/")
    info["disk_free_gb"] = round(du.free / 1e9, 1)
    try:
        info["os"] = re.search(r'PRETTY_NAME="([^"]+)"', Path("/etc/os-release").read_text()).group(1)
    except Exception:  # noqa: BLE001
        info["os"] = "?"
    write_json(RESULTS / "machine.json", info)
    print(f"    {info}")
    problems = []
    if info["mem_gb"] < 7.5:
        problems.append("moins de 8 Go de mémoire : Airbyte ne tiendra pas")
    if info["disk_free_gb"] < 30:
        problems.append("moins de 30 Go libres sur le disque")
    if problems:
        print(f"    {Y}⚠ " + " ; ".join(problems) + X)


def p0_apt(log):
    sh("sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
       "python3-venv python3-pip curl git ca-certificates >/dev/null", log)


def p0_tools(log):
    env = venv("tools")
    shutil.rmtree(env, ignore_errors=True)
    sh(f"python3 -m venv {env} && {env}/bin/pip -q install -U pip && {env}/bin/pip -q install pandas", log)


def p0_data(log):
    sh(f"{TOOLS_PY} shared/make_data.py shared/data", log)


def p1_install(log):
    r = install_measure("phase1_hydra", "Hydra ETL", venv("hydra"),
                        [f"{{pip}} install hydra-etl=={HYDRA_VERSION}"], log)
    print(f"    {G}{r['install_seconds']}s, {r['packages']} paquets, {r['env_size_mb']:.0f} Mo{X}")


HYDRA_FILES_SIMPLE = "parameters.yaml jobs/*/*.yaml workflows/daily_revenue.yaml workflows/thread.yaml"
HYDRA_FILES_SAFE = "parameters.yaml jobs/*/*.yaml workflows/*.yaml"


def p1_lines(log):
    count_lines("phase1_hydra", "simple", HERE / "hydra_simple", HYDRA_FILES_SIMPLE, log)
    count_lines("phase1_hydra", "safe", HERE / "hydra", HYDRA_FILES_SAFE, log)


def _hydra_cmd():
    return f"{venv('hydra')}/bin/hdrctl run ."


def p1_simple(log):
    rows = scenarios("phase1_hydra", "hydra_simple", _hydra_cmd(), "scenarios_simple.json", log)
    print_runs(rows)


def p1_safe(log):
    rows = scenarios("phase1_hydra", "hydra", _hydra_cmd(), "scenarios_safe.json", log)
    print_runs(rows)


MODERN = HERE / "modern"


def _constraints() -> str:
    return (f"https://raw.githubusercontent.com/apache/airflow/constraints-{AIRFLOW_VERSION}/"
            f"constraints-{PYV}.txt")


def p2_install(log):
    r = install_measure("phase2_airflow_dlt_dbt", "Airflow + dlt + dbt", venv("modern"), [
        f"{{pip}} install apache-airflow=={AIRFLOW_VERSION} --constraint {_constraints()}",
        "{pip} install 'dlt[duckdb]' dbt-duckdb pandas pyarrow",
    ], log)
    print(f"    {G}{r['install_seconds']}s, {r['packages']} paquets, {r['env_size_mb']:.0f} Mo{X}")


def _modern_env(stack: Path) -> str:
    """Active l'environnement Python de la pile et ses variables (env.sh)."""
    return f"source {venv(stack.name)}/bin/activate && source env.sh"


def p2_airflow(log):
    shutil.rmtree(MODERN / "airflow_home", ignore_errors=True)
    for f in (MODERN / "warehouse.duckdb", MODERN / "warehouse.duckdb.wal"):
        f.unlink(missing_ok=True)
    shutil.rmtree(MODERN / ".dlt_pipelines", ignore_errors=True)
    t0 = time.monotonic()
    sh(f"{_modern_env(MODERN)} && airflow db migrate && airflow dags reserialize", log, cwd=MODERN)
    write_json(RESULTS / "phase2_airflow_dlt_dbt" / "setup.json", {"airflow_db_seconds": round(time.monotonic() - t0, 1)})
    out = sh(f"{_modern_env(MODERN)} && airflow dags list", log, cwd=MODERN)
    if "daily_revenue_safe" not in out:
        raise StepError("les DAG ne sont pas chargés (voir le journal)")


MODERN_FILES = ("ingest.py dags/{dag}.py dbt/dbt_project.yml dbt/profiles.yml dbt/models/*/*.sql "
                "dbt/models/*/*.yml env.sh")


def p2_lines(log):
    count_lines("phase2_airflow_dlt_dbt", "simple", MODERN, MODERN_FILES.format(dag="daily_revenue_simple"), log)
    count_lines("phase2_airflow_dlt_dbt", "safe", MODERN, MODERN_FILES.format(dag="daily_revenue_safe"), log)


def p2_simple(log):
    rows = scenarios("phase2_airflow_dlt_dbt", "modern",
                     f"{_modern_env(MODERN)} && airflow dags test daily_revenue_simple",
                     "scenarios_simple.json", log)
    print_runs(rows)


def p2_safe(log):
    rows = scenarios("phase2_airflow_dlt_dbt", "modern",
                     f"{_modern_env(MODERN)} && airflow dags test daily_revenue_safe",
                     "scenarios_safe.json", log)
    print_runs(rows)


def print_runs(rows):
    for sc, v in summarize_runs(rows).items():
        ok = f"{G}cohérent{X}" if v["consistent"] else f"{R}INCOHÉRENT{X}"
        print(f"    {sc:<15} {', '.join(v['outputs']):<22} {ok}  médiane {v['median_seconds']}s")


# Phase 3 et 4 : voir airbyte/steps.py et shared/report.py
def phase3_steps():
    sys.path.insert(0, str(HERE / "airbyte"))
    import steps as ab  # noqa: E402
    ab.setup(sh=sh, StepError=StepError, write_json=write_json, du_mb=du_mb, venv=venv, pip_count=pip_count,
             install_measure=install_measure, scenarios=scenarios, count_lines=count_lines,
             print_runs=print_runs, RESULTS=RESULTS, HERE=HERE, PYV=PYV, AIRFLOW_VERSION=AIRFLOW_VERSION,
             constraints=_constraints, G=G, Y=Y, X=X)
    return [Step(*a[:3], **a[3]) for a in ab.STEPS]


def p4_report(log):
    sh(f"{TOOLS_PY} shared/report.py {RESULTS}", log)
    print(f"    {G}→ {RESULTS / 'raw-report.md'}{X}")


def all_steps() -> list:
    steps = [
        Step("0.1", "Vérifier la machine", p0_machine, confirm=True),
        Step("0.2", "Paquets système (python3-venv, curl, git)", p0_apt),
        Step("0.3", "Outils de mesure (pandas)", p0_tools),
        Step("0.4", "Générer les données (200 000 commandes)", p0_data),
        Step("1.1", "Hydra ETL — installation (sans cache)", p1_install, confirm=True),
        Step("1.2", "Hydra ETL — lignes de code", p1_lines),
        Step("1.3", f"Hydra ETL — pannes, variante simple ({REPEAT} fois)", p1_simple),
        Step("1.4", f"Hydra ETL — pannes, variante sûre ({REPEAT} fois)", p1_safe),
        Step("2.1", "Airflow + dlt + dbt — installation (sans cache)", p2_install, confirm=True),
        Step("2.2", "Airflow — base interne et chargement des DAG", p2_airflow),
        Step("2.3", "Airflow + dlt + dbt — lignes de code", p2_lines),
        Step("2.4", f"Airflow + dlt + dbt — pannes, variante simple ({REPEAT} fois)", p2_simple),
        Step("2.5", f"Airflow + dlt + dbt — pannes, variante sûre ({REPEAT} fois)", p2_safe,
             note="Fin de la phase 2 : c'est le bon moment pour un instantané (snapshot) du disque "
                  "dans la console AWS, avant Airbyte."),
    ]
    try:
        steps += phase3_steps()
    except Exception as e:  # noqa: BLE001
        print(f"{Y}⚠ phase 3 indisponible : {e}{X}")
    steps.append(Step("4.1", "Compte rendu brut (tableaux)", p4_report, confirm=True))
    return steps


PHASES = {"0": "Préparation", "1": "Hydra ETL", "2": "Airflow + dlt + dbt",
          "3": "Airflow + Airbyte + dbt", "4": "Compte rendu"}


# ── Boucle principale ────────────────────────────────────────────────────────
def main() -> int:
    global SAMPLER
    ap = argparse.ArgumentParser(description="Banc de comparaison (voir l'en-tête du fichier).")
    ap.add_argument("--phase", choices=list(PHASES), help="ne lancer qu'une phase")
    ap.add_argument("--redo", metavar="ÉTAPE", help="refaire une étape et les suivantes de sa phase")
    ap.add_argument("--status", action="store_true", help="afficher l'avancement et quitter")
    ap.add_argument("--yes", action="store_true", help="répondre oui à toutes les confirmations")
    a = ap.parse_args()

    steps = all_steps()
    st = load_state()
    if a.redo:
        ids = [s.id for s in steps]
        if a.redo not in ids:
            print(f"{R}étape inconnue : {a.redo}{X} ({', '.join(ids)})")
            return 2
        ph = a.redo.split(".")[0]
        for s in steps:
            if s.phase == ph and ids.index(s.id) >= ids.index(a.redo):
                st.pop(s.id, None)
        save_state(st)

    todo = [s for s in steps if not a.phase or s.phase == a.phase]
    done_n = sum(1 for s in todo if st.get(s.id, {}).get("status") == "done")

    print(f"\n{B}Banc de comparaison{X} — {len(todo)} étapes, {done_n} déjà faites  {bar(done_n, len(todo))}")
    for s in todo:
        mark = {"done": f"{G}✓{X}", "failed": f"{R}✗{X}"}.get(st.get(s.id, {}).get("status"), f"{D}·{X}")
        extra = f" {D}({fmt_s(st[s.id]['seconds'])}){X}" if st.get(s.id, {}).get("seconds") else ""
        print(f"  {mark} {s.id}  {s.title}{extra}")
    if a.status:
        return 0

    SAMPLER = Sampler()
    SAMPLER.start()
    current_phase = None
    for s in todo:
        if st.get(s.id, {}).get("status") == "done":
            continue
        if s.phase != current_phase:
            current_phase = s.phase
            print(f"\n{B}{C}══ Phase {s.phase} — {PHASES[s.phase]} ══{X}")
        done_n = sum(1 for x in todo if st.get(x.id, {}).get("status") == "done")
        print(f"\n{B}▶ {s.id}  {s.title}{X}   {D}général {bar(done_n, len(todo), 20)}{X}")
        if s.confirm and ask("Lancer cette étape ?", "O/n/q", "o", a.yes) != "o":
            print("  Arrêt demandé. Relancez `python3 run.py` pour reprendre ici.")
            return 0
        while True:
            log = LOGS / f"{s.id}.log"
            if st.get(s.id, {}).get("status") == "failed" and s.clean:
                print(f"  {D}remise à zéro de l'étape avant de recommencer…{X}")
                try:
                    s.clean(log)
                except Exception as e:  # noqa: BLE001
                    print(f"  {Y}⚠ nettoyage incomplet : {e}{X}")
            SAMPLER.step = s.id
            t0 = time.monotonic()
            try:
                s.run(log)
                secs = time.monotonic() - t0
                st[s.id] = {"status": "done", "seconds": round(secs, 1), "ended": time.strftime("%H:%M:%S"),
                            "peak_mem_mb": round(SAMPLER.peak_mb)}
                save_state(st)
                print(f"  {G}✓ {s.id} terminé en {fmt_s(secs)}{X}  {D}(point de reprise enregistré){X}")
                if s.note:
                    print(f"  {Y}ℹ {s.note}{X}")
                    ask("Continuer ?", "O/n", "o", a.yes) == "o" or sys.exit(0)
                break
            except (StepError, Exception) as e:  # noqa: BLE001
                st[s.id] = {"status": "failed", "error": str(e)[:2000], "ended": time.strftime("%H:%M:%S")}
                save_state(st)
                print(f"\n  {R}✗ {s.id} en échec{X}\n{D}{str(e)[-1500:]}{X}\n  Journal : {log}")
                if s.hint:
                    print(f"  {Y}ℹ {s.hint}{X}")
                c = ask("Réessayer cette étape, la passer, ou quitter ?", "r/s/q", "q", False)
                if c == "r":
                    continue
                if c == "s":
                    print(f"  {Y}étape passée : les résultats de cette phase seront incomplets{X}")
                    break
                print("  Arrêt. Relancez `python3 run.py` : la reprise se fera à cette étape.")
                return 1
        SAMPLER.step = "idle"
    print(f"\n{G}{B}Terminé.{X} Résultats : {RESULTS}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Y}Interrompu. Relancez `python3 run.py` pour reprendre.{X}")
        sys.exit(130)
