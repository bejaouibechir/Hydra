"""Phase 3 — Airflow + Airbyte + dbt (PostgreSQL). Étapes appelées par run.py.

Airbyte s'installe avec sa méthode officielle (`abctl`, Kubernetes léger dans
Docker). Les CSV de data/ sont servis en SFTP (conteneur `bench-sftp`) ;
Airbyte les copie dans PostgreSQL (conteneur `bench-pg`) ; dbt calcule ;
export.py écrit les CSV.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

D: dict = {}            # dépendances fournies par run.py (setup)
PH = "phase3_airflow_airbyte_dbt"
HERE = Path(__file__).resolve().parent
REPEAT = int(os.environ.get("BENCH_REPEAT_AIRBYTE", "1"))   # une synchronisation Airbyte est lente


def setup(**deps) -> None:
    D.update(deps)


def _extra(**kv) -> None:
    p = D["RESULTS"] / PH / "extra.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    data.update(kv)
    D["write_json"](p, data)


def _host_ip() -> str:
    return subprocess.run("hostname -I | awk '{print $1}'", shell=True, capture_output=True,
                          text=True).stdout.strip()


def _mem_gb() -> float:
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemTotal"):
            return int(ln.split()[1]) / 1024 / 1024
    return 0.0


def s_docker(log):
    if subprocess.run("command -v docker", shell=True, capture_output=True).returncode == 0:
        print("    Docker déjà présent (mesure gardée de la première installation)")
        return
    t0 = time.monotonic()
    D["sh"]("curl -fsSL https://get.docker.com | sudo sh", log)
    _extra(docker_install_seconds=round(time.monotonic() - t0, 1))


def s_abctl(log):
    t0 = time.monotonic()
    D["sh"]("curl -LsfS https://get.airbyte.com | bash -", log)
    _extra(abctl_install_seconds=round(time.monotonic() - t0, 1))
    D["sh"]("command -v abctl || ls ~/.local/bin/abctl", log)


def s_airbyte(log):
    low = _mem_gb() < 15.5
    flags = "--low-resource-mode" if low else ""
    print(f"    mémoire {_mem_gb():.1f} Go → {'mode réduit' if low else 'mode normal'} ; "
          f"compter 15 à 40 minutes (téléchargement des images)")
    abctl = "abctl" if subprocess.run("command -v abctl", shell=True).returncode == 0 else "~/.local/bin/abctl"
    t0 = time.monotonic()
    D["sh"](f"sudo DO_NOT_TRACK=1 {abctl} local install {flags}", log)
    _extra(airbyte_install_seconds=round(time.monotonic() - t0, 1), airbyte_low_resource_mode=low)
    out = D["sh"](f"sudo {abctl} local credentials", log)
    cid = _field(out, "Client-Id")
    sec = _field(out, "Client-Secret")
    if not cid or not sec:
        raise D["StepError"]("identifiants Airbyte introuvables dans `abctl local credentials`")
    (HERE / ".credentials.json").write_text(json.dumps({"client_id": cid, "client_secret": sec}))


def _field(text: str, name: str) -> str:
    import re
    m = re.search(rf"{name}\s*:\s*(\S+)", re.sub(r"\x1b\[[0-9;]*m", "", text))
    return m.group(1) if m else ""


def s_services(log):
    sh = D["sh"]
    sh("sudo docker rm -f bench-pg >/dev/null 2>&1 || true", log)
    sh("sudo docker run -d --name bench-pg -e POSTGRES_PASSWORD=bench -e POSTGRES_DB=bench "
       "-p 5433:5432 postgres:16", log)
    sh("for i in $(seq 1 30); do sudo docker exec bench-pg pg_isready -U postgres && break; sleep 2; done", log)
    # CSV servis en SFTP pour Airbyte (data/ est rempli par chaque scénario)
    _serve(log)


def s_python(log):
    r = D["install_measure"](PH, "Airflow + Airbyte + dbt", D["venv"]("airbyte"), [
        f"{{pip}} install apache-airflow=={D['AIRFLOW_VERSION']} --constraint {D['constraints']()}",
        "{pip} install dbt-postgres requests psycopg2-binary",
    ], log)
    print(f"    {D['G']}{r['install_seconds']}s, {r['packages']} paquets, {r['env_size_mb']:.0f} Mo{D['X']}")


def _py() -> str:
    return f"{D['venv']('airbyte')}/bin/python"


def _abctl() -> str:
    return "abctl" if subprocess.run("command -v abctl", shell=True, capture_output=True).returncode == 0 \
        else "~/.local/bin/abctl"


def _serve(log):
    """(Re)démarre le serveur SFTP des CSV (conteneur bench-sftp, port 2222) sur
    data/. À refaire si le dossier airbyte/ a été remplacé.
    La source « File » d'Airbyte force https:// pour une URL web : SFTP évite
    d'avoir à fabriquer un certificat."""
    (HERE / "data").mkdir(exist_ok=True)
    D["sh"]("sudo docker rm -f bench-sftp >/dev/null 2>&1 || true", log)
    D["sh"](f"sudo docker run -d --name bench-sftp -p 2222:22 -v {HERE}/data:/home/bench/data:ro "
            f"atmoz/sftp bench:bench:1001", log)
    D["sh"]("sleep 3", log)


def _copy_data(log):
    """Données du scénario normal dans data/ : Airbyte lit les fichiers dès la
    création des connexions (découverte du schéma)."""
    D["sh"](f"mkdir -p data/backup && cp {D['HERE']}/shared/data/orders.csv data/orders.csv && "
            f"cp {D['HERE']}/shared/data/customers.csv data/customers.csv && "
            f"cp {D['HERE']}/shared/data/orders_backup.csv data/backup/orders.csv", log, cwd=HERE)
    _serve(log)
    ip = _host_ip()
    D["sh"](f"sudo docker exec bench-sftp ls /home/bench/data/orders.csv && echo fichiers visibles par SFTP", log)
    D["sh"](f"sudo docker exec airbyte-abctl-control-plane bash -c '</dev/tcp/{ip}/2222' "
            f"&& echo SFTP joignable depuis Airbyte || echo 'ATTENTION : SFTP non joignable depuis Airbyte'", log)


def _credentials(log) -> dict:
    """Identifiants de l'API Airbyte (.credentials.json), relus si besoin."""
    p = HERE / ".credentials.json"
    if not p.exists():
        out = D["sh"](f"sudo {_abctl()} local credentials", log)
        cid, sec = _field(out, "Client-Id"), _field(out, "Client-Secret")
        if not cid or not sec:
            raise D["StepError"]("identifiants Airbyte introuvables dans `abctl local credentials`")
        p.write_text(json.dumps({"client_id": cid, "client_secret": sec}))
    return json.loads(p.read_text())


def s_configure(log):
    _copy_data(log)
    cred = _credentials(log)
    D["sh"](f"{_py()} airbyte_setup.py {cred['client_id']} {cred['client_secret']} {_host_ip()}", log, cwd=HERE)


def s_check_sync(log):
    sh = D["sh"]
    # données du scénario normal, puis une synchronisation de chaque connexion utile
    _copy_data(log)
    for c in ("orders_main", "customers"):
        t0 = time.monotonic()
        sh(f"{_py()} airbyte_sync.py {c}", log, cwd=HERE)
        _extra(**{f"first_sync_{c}_seconds": round(time.monotonic() - t0, 1)})
    sh(f"{D['venv']('airbyte')}/bin/dbt run --profiles-dir . --threads 1", log, cwd=HERE / "dbt")


def _env() -> str:
    return f"source {D['venv']('airbyte')}/bin/activate && source env.sh"


def s_airflow(log):
    import shutil
    shutil.rmtree(HERE / "airflow_home", ignore_errors=True)
    D["sh"](f"{_env()} && airflow db migrate && airflow dags reserialize", log, cwd=HERE)
    out = D["sh"](f"{_env()} && airflow dags list", log, cwd=HERE)
    if "daily_revenue_safe" not in out:
        raise D["StepError"]("les DAG ne sont pas chargés (voir le journal)")


FILES = ("airbyte_sync.py export.py dags/{dag}.py dbt/dbt_project.yml dbt/profiles.yml "
         "dbt/models/*/*.sql dbt/models/*/*.yml env.sh")


def s_lines(log):
    D["count_lines"](PH, "simple", HERE, FILES.format(dag="daily_revenue_simple"), log)
    D["count_lines"](PH, "safe", HERE, FILES.format(dag="daily_revenue_safe"), log)
    D["count_lines"](PH, "configuration_api", HERE, "airbyte_setup.py", log)


def _scen(variant, log):
    # repartir d'un schéma analytics vide (anciennes vues sur les tables brutes)
    D["sh"]("sudo docker exec bench-pg psql -U postgres -d bench -c 'DROP SCHEMA IF EXISTS analytics CASCADE'", log)
    rows = _run_scen(variant, log)
    D["print_runs"](rows)


def _run_scen(variant, log):
    import re
    out = D["RESULTS"] / PH / f"scenarios_{variant}.json"
    tools = Path.home() / "bench-envs" / "tools" / "bin" / "python"

    def prog(line):
        m = re.match(r"PROGRESS (\d+)/(\d+)", line)
        return (int(m.group(1)), int(m.group(2))) if m else None
    D["sh"](f"{tools} shared/scenarios.py airbyte \"{_env()} && airflow dags test daily_revenue_{variant}\" "
            f"--repeat {REPEAT} --out {out}", log, cwd=D["HERE"], progress=prog)
    return json.loads(out.read_text())


def s_simple(log):
    _scen("simple", log)


def s_safe(log):
    _scen("safe", log)


def s_resources(log):
    sh = D["sh"]
    imgs = sh("sudo docker exec airbyte-abctl-control-plane crictl images -q 2>/dev/null | wc -l", log).strip()
    pods = sh("sudo docker exec airbyte-abctl-control-plane crictl ps -q 2>/dev/null | wc -l", log).strip()
    size = sh("sudo docker exec airbyte-abctl-control-plane du -sm /var/lib/containerd 2>/dev/null "
              "| cut -f1 || echo 0", log).strip()
    docker_df = sh("sudo docker system df --format '{{.Type}} {{.Size}}'", log).strip().replace("\n", "; ")
    _extra(airbyte_images=imgs, airbyte_running_containers=pods, airbyte_images_mb=size, docker_df=docker_df)
    print(f"    images Airbyte : {imgs} ({size} Mo), conteneurs en marche : {pods}")


STEPS = [
    ("3.1", "Docker — installation", s_docker, {"confirm": True}),
    ("3.2", "abctl — installation", s_abctl, {}),
    ("3.3", "Airbyte — installation (abctl local install, long)", s_airbyte, {"confirm": True}),
    ("3.4", "PostgreSQL et serveur SFTP des CSV (conteneurs)", s_services, {}),
    ("3.5", "Airflow + dbt-postgres — installation (sans cache)", s_python, {}),
    ("3.6", "Airbyte — sources, destination, connexions (API)", s_configure, {
        "confirm": True,
        "hint": "Si cette étape échoue, créez-les dans l'interface (http://localhost:8000 via un tunnel SSH) "
                "avec les mêmes noms : orders_main, orders_backup, customers, bench_postgres ; puis relancez."}),
    ("3.7", "Airbyte — première synchronisation et dbt (vérification)", s_check_sync, {}),
    ("3.8", "Airflow — base interne et chargement des DAG", s_airflow, {}),
    ("3.9", "Airflow + Airbyte + dbt — lignes de code", s_lines, {}),
    ("3.10", f"Airflow + Airbyte + dbt — pannes, variante simple ({REPEAT} fois)", s_simple, {"confirm": True}),
    ("3.11", f"Airflow + Airbyte + dbt — pannes, variante sûre ({REPEAT} fois)", s_safe, {}),
    ("3.12", "Airbyte — ressources (images, conteneurs, disque)", s_resources, {}),
]
