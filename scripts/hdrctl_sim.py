#!/usr/bin/env python3
"""
hdrctl CLI Simulator — Interactive UX preview.
Lance avec : python hdrctl_sim.py
"""

import os
import sys
import time
import shlex

# ── Activer ANSI + UTF-8 sur Windows ─────────────────────────────────────────
if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── Couleurs ANSI ─────────────────────────────────────────────────────────────
class C:
    GR = "\033[92m"   # Vert
    RD = "\033[91m"   # Rouge
    YL = "\033[93m"   # Jaune
    CY = "\033[96m"   # Cyan
    DM = "\033[90m"   # Gris
    WH = "\033[97m"   # Blanc vif
    BD = "\033[1m"    # Gras
    RS = "\033[0m"    # Reset

# ── ASCII Art ─────────────────────────────────────────────────────────────────
LOGO = rf"""
{C.CY}{C.BD}  _  _ _   _ ___  ___   _   ___ _____ _    {C.RS}
{C.CY}{C.BD} | || | | | |   \| _ \ /_\ / __|_   _| |   {C.RS}
{C.CY}{C.BD} | __ | |_| | |) |   // _ \ (__  | | | |__ {C.RS}
{C.CY}{C.BD} |_||_|\_, |___/|_|_\/_/ \_\___| |_| |____|{C.RS}
{C.CY}{C.BD}       |__/                                  {C.RS}"""

SPLASH = f"""{LOGO}
{C.WH}  Hydra ETL  —  DevOps Edition{C.RS}
{C.DM}  Simple  •  Robust  •  Resilient{C.RS}
{C.DM}  Version 1.2.0{C.RS}

{C.DM}  ──────────────────────────────────────────{C.RS}
{C.DM}  Tapez  {C.WH}--help{C.DM}  pour voir les commandes{C.RS}
{C.DM}  Tapez  {C.WH}exit{C.DM}    pour quitter{C.RS}
{C.DM}  ──────────────────────────────────────────{C.RS}
"""

# Simulateur d'UX, hors paquet : pas d'import de hydra_etl pour rester
# autonome. Ce numero est un decor, pas une version publiee.
VERSION = "0.0.0-preview"


# ── Helpers ───────────────────────────────────────────────────────────────────

def p(*args, **kwargs):
    print(*args, **kwargs, flush=True)

def pause(n=0.7):
    time.sleep(n)

def step_ok(n: int, total: int, name: str, info: str = ""):
    pad  = name.ljust(26)
    xtra = f"  {C.DM}({info}){C.RS}" if info else ""
    p(f"  {C.GR}[{n}/{total}]{C.RS}  {C.WH}{pad}{C.RS}  {C.GR}ok{C.RS}  {C.DM}1.{n}s{C.RS}{xtra}")
    pause()

def step_err(n: int, total: int, name: str):
    pad = name.ljust(26)
    p(f"  {C.RD}[{n}/{total}]{C.RS}  {C.WH}{pad}{C.RS}  {C.RD}ERREUR{C.RS}")
    pause()

def ok_line(text: str):
    p(f"{C.GR}  ok{C.RS}  {text}")

def section(title: str):
    p(f"\n{C.WH}{C.BD}  {title}{C.RS}")


# ── Commande : --version ──────────────────────────────────────────────────────

def cmd_version():
    p()
    p(f"{C.WH}  hdrctl version {VERSION}{C.RS}")
    p(f"{C.DM}  Hydra ETL Framework — DevOps Edition{C.RS}")
    p(f"{C.DM}  Python {sys.version.split()[0]}  |  {sys.platform}{C.RS}")
    p(f"{C.DM}  Alias actifs : hydra, hyd{C.RS}")


# ── Commande : --help ─────────────────────────────────────────────────────────

def cmd_help():
    p()
    p(f"{C.WH}{C.BD}  USAGE{C.RS}")
    p(f"{C.WH}    hdrctl <commande> [options]{C.RS}")

    p()
    p(f"{C.WH}{C.BD}  COMMANDES{C.RS}")

    p(f"\n{C.CY}    init {C.WH}<NOM>{C.RS}              Crée un nouveau job ETL")
    p(f"{C.DM}         --template <TYPE>   mysql | postgres | csv | api | mongodb | basic{C.RS}")
    p(f"{C.DM}         --force             Écrase si le dossier existe{C.RS}")
    p(f"{C.DM}         --quiet             Mode silencieux{C.RS}")

    p(f"\n{C.CY}    run  {C.WH}[CHEMIN]{C.RS}             Exécute le pipeline (défaut : .)")
    p(f"{C.DM}         -v / -vv / -vvv / -vvvv      Verbosité style Ansible{C.RS}")
    p(f"{C.DM}         --dry-run                    Simulation sans écriture{C.RS}")
    p(f"{C.DM}         --only-step <NOM>            Exécute un seul step de transform{C.RS}")
    p(f"{C.DM}         --from-step <NOM>            Démarre à partir d'un step{C.RS}")
    p(f"{C.DM}         --to-step <NOM>              Arrête après un step{C.RS}")
    p(f"{C.DM}         --skip-steps <N1,N2>         Saute des steps spécifiques{C.RS}")
    p(f"{C.DM}         --rollback                   Rollback DB + fichiers sur erreur{C.RS}")
    p(f"{C.DM}         --delay <SEC>                Délai global entre steps{C.RS}")
    p(f"{C.DM}         --delay-between <S1> <S2> <N>  Délai entre deux steps{C.RS}")
    p(f"{C.DM}         --schedule \"<CRON>\"          Génère une entrée crontab{C.RS}")
    p(f"{C.DM}         --on-success \"<CMD>\"         Hook exécuté en cas de succès{C.RS}")
    p(f"{C.DM}         --on-failure \"<CMD>\"         Hook exécuté en cas d'échec{C.RS}")
    p(f"{C.DM}         --on-finish  \"<CMD>\"         Hook toujours exécuté{C.RS}")
    p(f"{C.DM}         --error                      (démo) Simule un échec{C.RS}")

    p(f"\n{C.CY}    test     {C.WH}[CHEMIN]{C.RS}         Valide sources + destinations + DSL")
    p(f"{C.DM}             --only-sources | --only-destinations | --only-transform{C.RS}")

    p(f"\n{C.CY}    validate {C.WH}[CHEMIN]{C.RS}         Validation stricte du DSL YAML")
    p(f"{C.DM}             --strict{C.RS}")

    p(f"\n{C.CY}    list{C.RS}                       Liste les jobs du répertoire courant")
    p(f"{C.CY}    --version{C.RS}                  Affiche la version")
    p(f"{C.CY}    --help{C.RS}                     Affiche cette aide")

    p()
    p(f"{C.DM}  EXEMPLES{C.RS}")
    for ex in [
        "hdrctl init mon_job --template mysql",
        "hdrctl run . -vv --rollback",
        "hdrctl run . --only-step calculate_revenue",
        "hdrctl run . --from-step cast",
        "hdrctl run . --skip-steps filter_invalid,cast",
        'hdrctl run . --schedule "0 2 * * *"',
        'hdrctl run . --on-success "curl -s https://hooks.slack.com/..."',
        "hdrctl run . --error                  # simule un échec",
        "hdrctl test . --only-sources",
        "hdrctl validate . --strict",
    ]:
        p(f"{C.DM}    {ex}{C.RS}")


# ── Commande : init ───────────────────────────────────────────────────────────

def cmd_init(name: str, template: str = "basic", quiet: bool = False, force: bool = False):
    p()
    if not quiet:
        p(f"{C.CY}  Initialisation : {C.WH}{name}{C.CY}  [template: {C.WH}{template}{C.CY}]...{C.RS}")
        pause(1)
        p(f"{C.DM}  Création de la structure...{C.RS}")
        pause(0.8)

    files = [
        f"{name}/pipeline.yaml",
        f"{name}/sources.yaml",
        f"{name}/destinations.yaml",
        f"{name}/transformations.yaml",
        f"{name}/.env.example",
        f"{name}/README.md",
    ]
    for f in files:
        ok_line(f)

    extras = {
        "mysql":    [("sources.yaml",      "MySQL source pré-configurée"),
                     ("destinations.yaml", "MySQL destination + upsert")],
        "postgres": [("sources.yaml",      "PostgreSQL source"),
                     ("destinations.yaml", "PostgreSQL + ON CONFLICT DO UPDATE")],
        "csv":      [("data/input.csv",    "Fichier CSV exemple inclus")],
        "api":      [("sources.yaml",      "Web API + pagination cursor + OAuth2")],
        "mongodb":  [("sources.yaml",      "MongoDB + détection schéma automatique")],
    }
    if template in extras:
        p()
        for fname, desc in extras[template]:
            p(f"{C.DM}       {fname:<28}: {desc}{C.RS}")

    p()
    p(f"{C.GR}{C.BD}  ✅ Job '{C.WH}{name}{C.GR}' créé avec succès.{C.RS}")
    p()
    p(f"{C.DM}  Prochaines étapes :{C.RS}")
    p(f"{C.DM}    1. Éditez les fichiers YAML dans {C.WH}./{name}/{C.DM}{C.RS}")
    p(f"{C.DM}    2. Copiez .env.example → .env  et renseignez vos credentials{C.RS}")
    p(f"{C.DM}    3. {C.WH}hdrctl test {name}{C.DM}  pour valider la config{C.RS}")
    p(f"{C.DM}    4. {C.WH}hdrctl run  {name}{C.DM}  pour exécuter{C.RS}")


# ── Commande : run ────────────────────────────────────────────────────────────

def cmd_run(tokens: list):
    ns = _parse_run(tokens)

    if ns["dry_run"]:           _run_dryrun(ns)
    elif ns["schedule"]:        _run_schedule(ns)
    elif ns["only_step"]:       _run_only_step(ns)
    elif ns["from_step"]:       _run_from_step(ns)
    elif ns["skip_steps"]:      _run_skip_steps(ns)
    elif ns["error"]:           _run_error(ns)
    else:                       _run_success(ns)


def _parse_run(tokens):
    ns = dict(path=".", verbosity=0, dry_run=False, rollback=False,
              schedule=None, only_step=None, from_step=None, to_step=None,
              skip_steps=None, delay=0.0, error=False,
              on_success=None, on_failure=None, on_finish=None)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if   t == "-v":            ns["verbosity"] = max(ns["verbosity"], 1)
        elif t == "-vv":           ns["verbosity"] = max(ns["verbosity"], 2)
        elif t == "-vvv":          ns["verbosity"] = max(ns["verbosity"], 3)
        elif t == "-vvvv":         ns["verbosity"] = max(ns["verbosity"], 4)
        elif t == "--dry-run":     ns["dry_run"]  = True
        elif t == "--rollback":    ns["rollback"] = True
        elif t == "--error":       ns["error"]    = True
        elif t == "--schedule"  and i+1 < len(tokens): i+=1; ns["schedule"]   = tokens[i]
        elif t == "--only-step" and i+1 < len(tokens): i+=1; ns["only_step"]  = tokens[i]
        elif t == "--from-step" and i+1 < len(tokens): i+=1; ns["from_step"]  = tokens[i]
        elif t == "--to-step"   and i+1 < len(tokens): i+=1; ns["to_step"]    = tokens[i]
        elif t == "--skip-steps"and i+1 < len(tokens): i+=1; ns["skip_steps"] = tokens[i]
        elif t == "--delay"     and i+1 < len(tokens):
            i+=1
            try: ns["delay"] = float(tokens[i])
            except ValueError: pass
        elif t == "--on-success"and i+1 < len(tokens): i+=1; ns["on_success"] = tokens[i]
        elif t == "--on-failure"and i+1 < len(tokens): i+=1; ns["on_failure"] = tokens[i]
        elif t == "--on-finish" and i+1 < len(tokens): i+=1; ns["on_finish"]  = tokens[i]
        elif not t.startswith("-") and ns["path"] == ".":
            ns["path"] = t
            if t == "error_job": ns["error"] = True
        i += 1
    return ns


STEPS = [
    ("extract_customers",  "12 450 lignes"),
    ("join_catalogue",     ""),
    ("filter_invalid",     "231 filtrées"),
    ("cast",               ""),
    ("calculate_revenue",  ""),
    ("rename_columns",     ""),
    ("select_output",      ""),
    ("load_dwh",           "12 219 écrites"),
]


def _run_success(ns):
    path, vl, rollback, delay = ns["path"], ns["verbosity"], ns["rollback"], ns["delay"]
    p()
    p(f"{C.WH}  ▶  Pipeline {C.CY}\"daily_revenue\"{C.WH} démarré  "
      f"{C.DM}({path} — {len(STEPS)} étapes){C.RS}")
    p()
    for i, (name, info) in enumerate(STEPS, 1):
        if delay > 0 and i > 1:
            pause(delay)
        step_ok(i, len(STEPS), name, info)

    p()
    p(f"{C.GR}{C.BD}  ✅ Pipeline terminé avec succès en 14.2s{C.RS}")
    p(f"{C.DM}     Lignes lues    : 12 450{C.RS}")
    p(f"{C.DM}     Lignes écrites : 12 219{C.RS}")
    p(f"{C.DM}     Rapport        : .\\logs\\daily_revenue_20260426_090134.json{C.RS}")
    if rollback:
        p(f"{C.DM}     Rollback       : transactions committées (succès){C.RS}")

    if vl >= 1:
        p(f"\n{C.YL}  [v] Détail d'exécution :{C.RS}")
        for line in [
            "extract_customers : SELECT * FROM customers — batch_size=10000",
            "join_catalogue    : LEFT JOIN catalogue ON product_id",
            "filter_invalid    : price > 0 AND qty > 0",
            "calculate_revenue : revenue = price * qty",
            "load_dwh          : mode=upsert, key=[id]",
        ]:
            p(f"{C.DM}     {line}{C.RS}")

    if vl >= 2:
        p(f"\n{C.YL}  [vv] Variables résolues :{C.RS}")
        p(f"{C.DM}     DB_HOST=localhost  DB_PORT=3306  DB_NAME=warehouse{C.RS}")
        p(f"{C.DM}     BATCH_SIZE=10000   TIMEOUT=30{C.RS}")
        p(f"\n{C.YL}  [vv] Métriques par step :{C.RS}")
        for line in [
            "extract_customers : 1.2s  | 12450 rows | 0 errors",
            "join_catalogue    : 2.8s  | 12450 rows | 0 errors",
            "filter_invalid    : 0.3s  | 12219 rows | 231 filtered",
            "calculate_revenue : 0.9s  | 12219 rows | 0 errors",
            "load_dwh          : 3.4s  | 12219 rows | 0 errors",
        ]:
            p(f"{C.DM}     {line}{C.RS}")

    if vl >= 3:
        p(f"\n{C.YL}  [vvv] Log complet :{C.RS}")
        for line in [
            "2026-04-26 09:01:34 INFO  JobExecutor started — job_id=daily_revenue",
            "2026-04-26 09:01:34 INFO  Loading .env layers (root + job)",
            "2026-04-26 09:01:34 INFO  Parsing sources.yaml — OK",
            "2026-04-26 09:01:35 INFO  Connector 'src_mysql' connected in 0.4s",
            "2026-04-26 09:01:35 INFO  Batch 1/2 extracted — 10000 rows",
            "2026-04-26 09:01:36 INFO  Batch 1/2 transformed — 9831 rows (169 filtered)",
            "2026-04-26 09:01:37 INFO  Batch 1/2 loaded — 9831 rows upserted",
            "2026-04-26 09:01:37 INFO  Batch 2/2 extracted — 2450 rows",
            "2026-04-26 09:01:38 INFO  Batch 2/2 loaded — 2388 rows upserted",
            "2026-04-26 09:01:48 INFO  JobExecutor completed — 14.2s",
        ]:
            p(f"{C.DM}     {line}{C.RS}")

    if vl >= 4:
        p(f"\n{C.YL}  [vvvv] Requêtes SQL :{C.RS}")
        p(f"{C.DM}     SELECT id, name, email FROM customers LIMIT 10000 OFFSET 0{C.RS}")
        p(f"{C.DM}     SELECT c.*, p.price FROM orders c LEFT JOIN catalogue p"
          f" ON c.product_id=p.id{C.RS}")
        p(f"\n{C.YL}  [vvvv] Données brutes (3 premières lignes) :{C.RS}")
        for row in [
            '{"id":1, "name":"Alice Martin",  "revenue":142.50, "product_id":"P001"}',
            '{"id":2, "name":"Bob Dupont",    "revenue":89.90,  "product_id":"P003"}',
            '{"id":3, "name":"Claire Petit",  "revenue":231.00, "product_id":"P001"}',
        ]:
            p(f"{C.DM}     {row}{C.RS}")

    _fire_hooks(ns, "SUCCESS")


def _run_error(ns):
    rollback = ns["rollback"]
    p()
    p(f"{C.WH}  ▶  Pipeline {C.CY}\"daily_revenue\"{C.WH} démarré  {C.DM}(8 étapes){C.RS}")
    p()
    step_ok(1, 8, "extract_customers", "12 450 lignes")
    step_err(2, 8, "join_catalogue")
    p()
    p(f"{C.RD}{C.BD}  ❌ Pipeline \"daily_revenue\" ÉCHOUÉ en 9.4s  (étape 2/8){C.RS}")
    p()
    p(f"{C.WH}  Étape en échec  :{C.RS} {C.YL}join_catalogue{C.RS}  {C.DM}(op: join){C.RS}")
    p(f"{C.WH}  Cause           :{C.RS} Clé de jointure {C.YL}\"product_id\"{C.RS}"
      f" introuvable dans la source {C.YL}\"catalogue\"{C.RS}")
    p(f"{C.WH}  Suggestion      :{C.RS} Vérifiez le nom de colonne dans {C.CY}sources.yaml{C.RS}")
    p(f"{C.WH}  Hint            :{C.RS} Relancez avec {C.CY}-v{C.WH} pour voir les colonnes disponibles{C.RS}")
    p()
    p(f"{C.DM}  Rapport complet → .\\logs\\job_20260426_091203.json{C.RS}")
    if rollback:
        p()
        p(f"{C.YL}  ⟳ Rollback activé...{C.RS}")
        pause(1)
        p(f"{C.GR}  ✓ Transactions annulées — base de données restaurée.{C.RS}")
    _fire_hooks(ns, "FAILURE")


def _run_dryrun(ns):
    path = ns["path"]
    p()
    p(f"{C.YL}  ◈  Mode DRY-RUN — aucune donnée ne sera écrite{C.RS}")
    p()
    p(f"{C.WH}  Validation du pipeline {C.CY}\"daily_revenue\"{C.RS}")
    p()
    pause(0.6)
    for line in [
        "sources.yaml         — valide",
        "destinations.yaml    — valide",
        "transformations.yaml — 8 steps valides",
        "pipeline.yaml        — from: src_mysql → to: dest_dwh",
    ]:
        ok_line(line)
    pause(0.6)
    ok_line("Connexion src_mysql  — OK (localhost:3306/warehouse)")
    ok_line("Connexion dest_dwh   — OK (localhost:3306/dwh)")
    pause(0.6)
    ok_line("Secrets résolus      — DB_HOST, DB_USER, DB_PASS")
    ok_line("Upsert key           — [id] présent dans le schéma destination")
    p()
    p(f"{C.GR}{C.BD}  ✅ Dry-run terminé — tout est valide. Prêt à exécuter.{C.RS}")
    p(f"{C.DM}     Lancez {C.WH}hdrctl run .{C.DM} pour exécuter réellement.{C.RS}")


def _run_schedule(ns):
    cron = ns["schedule"]
    path = ns["path"]
    p()
    p(f"{C.YL}  ◈  Planification via crontab — \"{C.WH}{cron}{C.YL}\"{C.RS}")
    p()
    pause(0.8)
    p(f"{C.DM}  Génération de l'entrée crontab...{C.RS}")
    pause(0.8)
    p()
    p(f"{C.WH}  Entrée crontab générée :{C.RS}")
    p(f"{C.CY}  {cron} hdrctl run \"{path}\" >> .\\logs\\scheduled.log 2>&1{C.RS}")
    p()
    p(f"{C.DM}  Pour activer :{C.RS}")
    p(f"{C.DM}    Windows → Planificateur de tâches (Task Scheduler){C.RS}")
    p(f"{C.DM}    Linux   → crontab -e  (coller la ligne ci-dessus){C.RS}")
    p(f"{C.DM}    Docker  → CronJob Kubernetes ou systemd timer{C.RS}")
    p()
    p(f"{C.GR}  ✅ Entrée crontab prête.{C.RS}")
    p(f"{C.DM}     Déclenchement selon : {C.WH}{cron}{C.RS}")


def _run_only_step(ns):
    step = ns["only_step"]
    p()
    p(f"{C.YL}  ◈  Exécution partielle — step uniquement : {C.WH}{step}{C.RS}")
    p(f"{C.DM}     (extract et load s'exécutent normalement){C.RS}")
    p()
    pause(0.6)
    p(f"{C.DM}     [extract]  src_mysql → 12 450 lignes chargées{C.RS}")
    pause(0.8)
    p(f"{C.GR}  ok{C.RS}  {C.WH}[step] {step}{C.RS}  {C.DM}0.9s{C.RS}")
    pause(0.6)
    p(f"{C.DM}     [load]     dest_dwh  ← 12 219 lignes écrites{C.RS}")
    p()
    p(f"{C.GR}{C.BD}  ✅ Exécution partielle terminée — step '{step}' seul.{C.RS}")


def _run_from_step(ns):
    from_name = ns["from_step"]
    p()
    p(f"{C.YL}  ◈  Exécution partielle — à partir du step : {C.WH}{from_name}{C.RS}")
    p(f"{C.DM}     (steps précédents ignorés){C.RS}")
    p()
    pause(0.6)
    p(f"{C.DM}     [extract]  src_mysql → 12 450 lignes chargées{C.RS}")
    for s in ["extract_customers", "join_catalogue", "filter_invalid", "cast"]:
        p(f"{C.DM}     [skip]     {s:<26} ⊘  (avant --from-step){C.RS}")
    pause(0.8)
    step_ok(5, 8, from_name)
    step_ok(6, 8, "rename_columns")
    step_ok(7, 8, "select_output")
    pause(0.6)
    p(f"{C.DM}     [load]     dest_dwh  ← 12 219 lignes écrites{C.RS}")
    p()
    p(f"{C.GR}{C.BD}  ✅ Exécution à partir de '{from_name}' terminée.{C.RS}")


def _run_skip_steps(ns):
    skip = ns["skip_steps"]
    skipped = {s.strip() for s in skip.split(",")}
    p()
    p(f"{C.YL}  ◈  Exécution avec steps ignorés : {C.WH}{skip}{C.RS}")
    p()
    for i, (name, info) in enumerate(STEPS, 1):
        if name in skipped:
            p(f"  {C.DM}[{i}/{len(STEPS)}]  {name:<26} ⊘  ignoré (--skip-steps){C.RS}")
            pause(0.3)
        else:
            step_ok(i, len(STEPS), name, info)
    p()
    p(f"{C.GR}{C.BD}  ✅ Pipeline terminé ({len(skipped)} steps ignorés).{C.RS}")


def _fire_hooks(ns, status):
    if ns.get("on_success") and status == "SUCCESS":
        p()
        p(f"{C.DM}  [hook] --on-success → {ns['on_success']}{C.RS}")
        pause(0.8)
        p(f"{C.GR}  ✓ Hook success exécuté avec succès.{C.RS}")
    if ns.get("on_failure") and status == "FAILURE":
        p()
        p(f"{C.DM}  [hook] --on-failure → {ns['on_failure']}{C.RS}")
        pause(0.8)
        p(f"{C.GR}  ✓ Hook failure exécuté.{C.RS}")
    if ns.get("on_finish"):
        p()
        p(f"{C.DM}  [hook] --on-finish → {ns['on_finish']}{C.RS}")
        pause(0.8)
        p(f"{C.GR}  ✓ Hook finish exécuté.{C.RS}")


# ── Commande : test ───────────────────────────────────────────────────────────

def cmd_test(path: str, only_src: bool, only_dst: bool, only_trf: bool):
    p()
    p(f"{C.WH}  🔍 Test du job {C.CY}'{path}'{C.RS}")
    p()
    pause(0.6)
    if not only_dst and not only_trf:
        ok_line("sources.yaml              — syntaxe valide")
        ok_line(f"Source 'src_mysql'        — connexion OK  {C.DM}(localhost:3306){C.RS}")
    pause(0.6)
    if not only_src and not only_trf:
        ok_line("destinations.yaml         — syntaxe valide")
        ok_line(f"Destination 'dest_dwh'    — connexion OK  {C.DM}(localhost:3306){C.RS}")
        ok_line("Mode upsert               — key [id] présent dans le schéma")
    pause(0.6)
    if not only_src and not only_dst:
        ok_line("transformations.yaml      — 8 steps valides")
        ok_line("Opérations                — cast, filter, calculate, rename, select")
        ok_line("Secrets                   — DB_HOST, DB_USER, DB_PASS résolus")
    p()
    p(f"{C.GR}{C.BD}  ✅ Tous les tests passent — prêt à exécuter.{C.RS}")
    p(f"{C.DM}     Lancez : {C.WH}hdrctl run {path}{C.RS}")


# ── Commande : validate ───────────────────────────────────────────────────────

def cmd_validate(path: str, strict: bool):
    p()
    label = "Validation STRICTE" if strict else "Validation"
    p(f"{C.WH}  🔍 {label} du DSL — {C.CY}'{path}'{C.RS}")
    p()
    pause(0.6)
    ok_line("pipeline.yaml         — champs 'from' et 'to' présents")
    ok_line("sources.yaml          — schéma Pydantic valide")
    ok_line("destinations.yaml     — mode 'upsert' + key définie")
    ok_line("transformations.yaml  — 8 steps, opérations reconnues")
    pause(0.6)
    if strict:
        ok_line("Types de colonnes      — vérifiés")
        ok_line("Colonnes clé           — présentes dans le schéma source")
        ok_line("Expressions 'calculate'— évaluées sans erreur")
        ok_line("Aucun step orphelin    — détecté")
    p()
    p(f"{C.GR}{C.BD}  ✅ DSL valide — aucune erreur détectée.{C.RS}")


# ── Commande : list ───────────────────────────────────────────────────────────

def cmd_list():
    p()
    p(f"{C.WH}  Jobs détectés dans le répertoire courant :{C.RS}")
    p()
    p(f"{C.DM}  ──────────────────────────────────────────────────────────{C.RS}")
    jobs = [
        ("daily_revenue",   f"{C.GR}✅ OK{C.RS}",   "2026-04-26 02:00  (14.2s)"),
        ("weekly_export",   f"{C.GR}✅ OK{C.RS}",   "2026-04-24 03:00  (42.1s)"),
        ("api_sync",        f"{C.YL}⚠ WARN{C.RS}", "2026-04-25 08:15  (erreur 429)"),
        ("customer_report", f"{C.DM}— {C.RS}",      "jamais exécuté"),
    ]
    for name, status, info in jobs:
        p(f"  {C.CY}{name:<20}{C.RS}  {status:<20}  {C.DM}{info}{C.RS}")
    p(f"{C.DM}  ──────────────────────────────────────────────────────────{C.RS}")
    p()
    p(f"{C.DM}  4 jobs trouvés  |  2 OK  |  1 avertissement  |  1 non exécuté{C.RS}")
    p(f"{C.DM}  Utilisez {C.WH}hdrctl run <nom>{C.DM} pour exécuter un job spécifique.{C.RS}")


# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch(raw: str):
    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()

    if not tokens:
        return

    cmd   = tokens[0].lower()
    rest  = tokens[1:]

    if cmd in ("exit", "quit", "q"):
        p()
        p(f"{C.DM}  Au revoir !{C.RS}")
        p()
        sys.exit(0)

    elif cmd in ("--version", "version"):
        cmd_version()

    elif cmd in ("--help", "help", "-h"):
        cmd_help()

    elif cmd == "init":
        name  = rest[0] if rest and not rest[0].startswith("-") else "my_job"
        tmpl  = "basic"
        quiet = False
        force = False
        i = 0
        while i < len(rest):
            if rest[i] == "--template" and i+1 < len(rest): tmpl  = rest[i+1]; i+=2
            elif rest[i] == "--quiet":  quiet = True; i+=1
            elif rest[i] == "--force":  force = True; i+=1
            else: i+=1
        cmd_init(name, tmpl, quiet, force)

    elif cmd == "run":
        cmd_run(rest)

    elif cmd == "test":
        path     = "."
        only_src = only_dst = only_trf = False
        for t in rest:
            if   t == "--only-sources":      only_src = True
            elif t == "--only-destinations": only_dst = True
            elif t == "--only-transform":    only_trf = True
            elif not t.startswith("-"):      path = t
        cmd_test(path, only_src, only_dst, only_trf)

    elif cmd == "validate":
        path   = "."
        strict = False
        for t in rest:
            if   t == "--strict":       strict = True
            elif not t.startswith("-"): path = t
        cmd_validate(path, strict)

    elif cmd == "list":
        cmd_list()

    else:
        p()
        p(f"{C.RD}  Commande inconnue : '{C.WH}{cmd}{C.RD}'{C.RS}")
        p(f"{C.DM}  Tapez {C.WH}--help{C.DM} pour voir les commandes disponibles.{C.RS}")


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    os.system("cls" if sys.platform == "win32" else "clear")
    print(SPLASH)

    prompt = f"{C.CY}hdrctl{C.RS}> "
    while True:
        try:
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            p()
            p(f"\n{C.DM}  Au revoir !{C.RS}\n")
            break

        if not raw:
            continue

        try:
            dispatch(raw)
        except SystemExit:
            break
        except Exception as e:
            p(f"{C.RD}  Erreur interne : {e}{C.RS}")


if __name__ == "__main__":
    main()
