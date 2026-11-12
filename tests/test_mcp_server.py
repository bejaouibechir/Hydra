"""
Tests du serveur MCP.

Ils verrouillent les deux garanties qui font la valeur du serveur :

1. **Aucune ecriture sans validation.** Un agent ne doit jamais pouvoir laisser
   un job invalide sur le disque de l'utilisateur.
2. **Aucune sortie de l'espace de travail.** Un agent qui suivrait une consigne
   malveillante trouvee dans un fichier de donnees ne doit pas pouvoir lire ou
   ecrire ailleurs.

Le reste verifie que la decouverte du DSL reste branchee sur la specification
generee depuis le code.
"""
from __future__ import annotations

import asyncio

import pytest

mcp = pytest.importorskip("mcp", reason="SDK MCP absent : pip install 'hydra-etl[mcp]'")

from hydra_etl.mcp.server import build_server  # noqa: E402

SOURCES = """version: "1.0"
sources:
  src:
    type: csv
    connection: {}
    extract:
      table: ventes.csv
"""
DESTINATIONS = """version: "1.0"
destinations:
  dst:
    type: csv
    connection: {}
    load:
      table: sortie.csv
      mode: replace
"""
PIPELINE_OK = """version: "1.0"
pipeline:
  from: src
  to: dst
"""
PIPELINE_KO = PIPELINE_OK.replace("from: src", "from: inexistant")
TRANSFORMATIONS = """version: "1.0"
steps:
  - select:
      columns: [id, nom]
"""


@pytest.fixture()
def call(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_MCP_WORKSPACE", str(tmp_path))
    server = build_server()

    def _call(name: str, **kwargs) -> str:
        result = asyncio.run(server.call_tool(name, kwargs))
        return result.content[0].text

    _call.workspace = tmp_path          # type: ignore[attr-defined]
    return _call


# --- Decouverte du DSL, branchee sur spec_export.py ------------------------

def test_liste_les_connecteurs_reels(call):
    out = call("hydra_list_connectors")
    for connector in ("csv", "json", "parquet", "postgresql", "mongodb", "web_api"):
        assert connector in out
    assert "s3" not in out and "bigquery" not in out


def test_liste_toutes_les_operations(call):
    from hydra_etl.internal.parser.transform import _OP_MODEL_MAP
    lignes = [l for l in call("hydra_list_operations").splitlines() if l.strip()]
    assert len(lignes) == len(_OP_MODEL_MAP) == 20
    assert any(l.startswith("window") for l in lignes) and any(l.startswith("text_to_rows") for l in lignes)
    assert any(l.startswith("cast") for l in lignes)


def test_operation_inconnue_propose_les_existantes(call):
    out = call("hydra_describe_operation", operation="lowercase")
    assert "unknown" in out.lower()
    assert "clean" in out          # la bonne piste est donnee au modele


# --- Garantie 1 : aucune ecriture sans validation ---------------------------

def test_ecriture_valide(call):
    out = call("hydra_write_job", job_path="jobs/ventes",
               sources_yaml=SOURCES, destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_OK, transformations_yaml=TRANSFORMATIONS)
    assert out.startswith("WRITTEN")
    job = call.workspace / "jobs" / "ventes"
    assert (job / "pipeline.yaml").exists()
    assert (job / "transformations.yaml").exists()


def test_cablage_casse_refuse_et_n_ecrit_rien(call):
    out = call("hydra_write_job", job_path="jobs/casse",
               sources_yaml=SOURCES, destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_KO)
    assert out.startswith("REFUSED")
    assert "inexistant" in out              # la raison est rendue au modele
    assert not (call.workspace / "jobs" / "casse").exists()


def test_yaml_invalide_refuse_sans_appeler_la_cli(call):
    out = call("hydra_write_job", job_path="jobs/pasyaml",
               sources_yaml="sources: [", destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSED")
    assert "YAML" in out
    assert not (call.workspace / "jobs" / "pasyaml").exists()


def test_correction_apres_refus(call):
    call("hydra_write_job", job_path="jobs/cycle", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_KO)
    assert not (call.workspace / "jobs" / "cycle").exists()

    out = call("hydra_write_job", job_path="jobs/cycle", sources_yaml=SOURCES,
               destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("WRITTEN")
    assert (call.workspace / "jobs" / "cycle" / "pipeline.yaml").exists()


# --- Garantie 2 : l'agent ne sort pas de l'espace de travail ----------------

@pytest.mark.parametrize("chemin", ["../..", "../../../etc", "/etc", "..\\..\\.."])
def test_evasion_refusee(call, chemin):
    for outil in ("hydra_read_job", "hydra_validate_job", "hydra_run_job"):
        out = call(outil, job_path=chemin)
        assert out.startswith("REFUSED"), f"{outil} a laissé passer {chemin!r}"


def test_ecriture_hors_espace_refusee(call):
    out = call("hydra_write_job", job_path="../evade",
               sources_yaml=SOURCES, destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSED")
    assert not (call.workspace.parent / "evade").exists()


# --- Lecture et validation --------------------------------------------------

def test_liste_et_valide_un_job_ecrit(call):
    call("hydra_write_job", job_path="jobs/lisible", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert "jobs/lisible" in call("hydra_list_jobs")
    assert call("hydra_validate_job", job_path="jobs/lisible").startswith("VALIDE")
    assert "sources.yaml" in call("hydra_read_job", job_path="jobs/lisible")


def test_erreur_expliquee_en_clair(call):
    out = call("hydra_explain_error",
               error_message="pipeline.from='x' not found in sources.yaml")
    assert "sources.yaml" in out


# --- Workflows --------------------------------------------------------------

WORKFLOW_OK = """version: "1.0"
workflow:
  name: quotidien
  trigger:
    type: manual
  steps:
    - name: extraire
      type: job
      job: ./jobs/ventes
      depends_on: []
    - name: prevenir
      type: action
      action: log
      params:
        message: "termine"
      depends_on: ["extraire"]
"""
WORKFLOW_KO = WORKFLOW_OK.replace('action: log', 'action: ""')


def test_workflow_valide_ecrit(call):
    out = call("hydra_write_workflow", workflow_path="wf/quotidien.yaml",
               workflow_yaml=WORKFLOW_OK)
    assert out.startswith("WRITTEN")
    assert (call.workspace / "wf" / "quotidien.yaml").exists()
    assert "wf/quotidien.yaml" in call("hydra_list_workflows")
    assert "quotidien" in call("hydra_read_workflow",
                               workflow_path="wf/quotidien.yaml")


def test_workflow_invalide_refuse_sans_ecrire(call):
    out = call("hydra_write_workflow", workflow_path="wf/casse.yaml",
               workflow_yaml=WORKFLOW_KO)
    assert out.startswith("REFUSED")
    assert not (call.workspace / "wf" / "casse.yaml").exists()


def test_workflow_evasion_refusee(call):
    out = call("hydra_read_workflow", workflow_path="../../secret.yaml")
    assert out.startswith("REFUSED")


# --- Voir les données -------------------------------------------------------

def test_preview_montre_colonnes_et_lignes(call):
    (call.workspace / "ventes.csv").write_text(
        "id,nom,montant\n1,a,150\n2,b,50\n", encoding="utf-8")
    out = call("hydra_preview_data", file_path="ventes.csv")
    assert "montant" in out and "150" in out
    assert "cast" in out.lower()          # le piege des types est rappele


def test_preview_refuse_hors_espace(call):
    assert call("hydra_preview_data",
                file_path="../../../etc/passwd").startswith("REFUSED")


# --- Coherence avec la demande ---------------------------------------------

def test_check_job_signale_une_operation_absente(call):
    call("hydra_write_job", job_path="jobs/sans_tri", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    out = call("hydra_check_job",
               user_request="trie les ventes par montant decroissant",
               job_path="jobs/sans_tri")
    assert out.startswith("ALERTS")
    assert "sort" in out


def test_check_job_signale_un_connecteur_absent(call):
    call("hydra_write_job", job_path="jobs/en_csv", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    out = call("hydra_check_job",
               user_request="charge le resultat dans postgres",
               job_path="jobs/en_csv")
    assert out.startswith("ALERTS")
    assert "postgres" in out


def test_check_job_sans_alerte_quand_conforme(call):
    call("hydra_write_job", job_path="jobs/simple", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    out = call("hydra_check_job",
               user_request="copie ventes.csv dans sortie.csv",
               job_path="jobs/simple")
    assert out.startswith("NO ALERT")


# --- Exemples ---------------------------------------------------------------

def test_find_example_privilegie_un_job_pertinent(call):
    out = call("hydra_find_example",
               user_request="joindre commandes et clients", count=1)
    assert "### Example" in out
    assert "sources.yaml" in out


# --- Environnements, paramètres, secrets (0.18) ----------------------------

def _env_project(root):
    from hydra_etl.internal.config import env_admin as ea
    (root / ".hydra").mkdir(parents=True, exist_ok=True)
    (root / "parameters.yaml").write_text(
        "parameters:\n  batch_size: {type: int, default: 500}\n  region: {type: string, default: eu}\n",
        encoding="utf-8")
    (root / "environments").mkdir(exist_ok=True)
    (root / "environments" / "prod.yaml").write_text("parameters:\n  batch_size: 5000\n", encoding="utf-8")
    ea.set_global_var(None, "PG_HOST", "db.local")
    ea.set_global_var("prod", "PG_DATABASE", "shop_prod")
    ea.set_secret_value(root, "pg.password", "COMMON-SECRET-VALUE")
    ea.set_secret_value(root, "mysql.password", "PROD-SECRET-VALUE", env="prod")


def test_project_settings_names_only(call):
    root = call.workspace
    _env_project(root)
    out = call("hydra_project_settings", project_path=".", env="prod")
    assert "prod" in out and "PG_HOST" in out and "PG_DATABASE" in out
    assert "batch_size" in out and "effective in prod: 5000" in out
    assert "mysql.password [prod]" in out and "pg.password [common]" in out
    for value in ("COMMON-SECRET-VALUE", "PROD-SECRET-VALUE", "db.local", "shop_prod"):
        assert value not in out


def test_project_settings_refuses_outside_and_non_project(call):
    assert call("hydra_project_settings", project_path="../..").startswith("REFUS")
    (call.workspace / "plain").mkdir()
    assert "Not a Hydra project" in call("hydra_project_settings", project_path="plain")
    _env_project(call.workspace)
    assert call("hydra_project_settings", project_path=".", env="bad name").startswith("REFUSED")


# --- Sous-projets (0.19) ------------------------------------------------------

def _sub(base, name, calls=()):
    import json as _json
    root = base / name
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(_json.dumps({"id": name, "name": name}))
    (root / "workflows").mkdir()
    steps = "    - name: hello\n      type: action\n      action: log\n      params: {message: hi}\n"
    for i, value in enumerate(calls):
        steps += f"    - name: call{i}\n      type: project\n      project: {value}\n"
    (root / "workflows" / "main.yaml").write_text("workflow:\n  name: main\n  steps:\n" + steps)
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    return root


def test_project_calls_tree(call):
    ws = call.workspace
    _sub(ws, "master", ["../slave_a", "../slave_b"])
    _sub(ws, "slave_a", ["../slave_c"])
    _sub(ws, "slave_b")
    _sub(ws, "slave_c")
    out = call("hydra_project_calls", project_path="master")
    assert "main.yaml › call0" in out and "slave_a" in out and "slave_b" in out
    assert "↳ slave_c" in out
    assert "OK — no cycle" in out


def test_project_calls_cycle_and_missing(call):
    ws = call.workspace
    _sub(ws, "a", ["../b", "../ghost"])
    _sub(ws, "b", ["../a"])
    out = call("hydra_project_calls", project_path="a", workflow="main")
    assert "cycle" in out and "a → b → a" in out.replace("[main]", "").replace("  ", " ")
    assert "NOT FOUND" in out and "Errors" in out


def test_project_calls_refuses_outside_and_non_project(call):
    assert call("hydra_project_calls", project_path="../..").startswith("REFUS")
    (call.workspace / "plain").mkdir()
    assert "Not a Hydra project" in call("hydra_project_calls", project_path="plain")
    _sub(call.workspace, "solo")
    assert "calls no other project" in call("hydra_project_calls", project_path="solo")


# --- Déclencheurs de projet (0.19) -------------------------------------------

def test_project_triggers(call):
    ws = call.workspace
    root = _sub(ws, "shop")
    (root / "triggers.yaml").write_text(
        "triggers:\n"
        "  - {name: nightly, type: cron, cron: '0 2 * * *', env: prod, workflows: [main]}\n"
        "  - {name: on_push, type: webhook, token: '${SECRET:trigger.on_push.token}'}\n"
        "  - {name: broken, type: interval, every: 1m, workflows: [nope]}\n")
    (root / ".hydra" / "secrets").write_text("trigger.on_push.token=SUPER-SECRET-TOKEN\n")
    out = call("hydra_project_triggers", project_path="shop")
    assert "nightly (cron): cron 0 2 * * *" in out and "next run:" in out and "env: prod" in out
    assert "secret 'trigger.on_push.token'" in out and "SUPER-SECRET-TOKEN" not in out
    assert "workflow(s) not found: nope" in out


def test_project_triggers_none_invalid_refused(call):
    _sub(call.workspace, "plain")
    assert "No trigger" in call("hydra_project_triggers", project_path="plain")
    (call.workspace / "plain" / "triggers.yaml").write_text("triggers:\n  - {name: x, type: cron}\n")
    assert "requires 'cron'" in call("hydra_project_triggers", project_path="plain")
    assert call("hydra_project_triggers", project_path="../..").startswith("REFUS")


def test_preview_data_lit_une_base_sqlite(call, tmp_path):
    import sqlite3
    db = tmp_path / "data" / "shop.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, amount REAL, status TEXT)")
    c.executemany("INSERT INTO orders VALUES (?, ?, ?)", [(1, 10.5, "paid"), (2, 3.0, "refunded")])
    c.commit(); c.close()
    out = call("hydra_preview_data", file_path="data/shop.db")
    assert "orders (2 rows): order_id INTEGER, amount REAL, status TEXT" in out
    out = call("hydra_preview_data", file_path="data/shop.db", table="orders")
    assert "order_id | amount | status" in out and "2 | 3.0 | refunded" in out


def test_refus_detaille_et_forme_attendue(tmp_path, monkeypatch):
    """A refused job tells which field is wrong and the shape each manifest must have
    (the pydantic details used to be dropped: « 2 validation errors for SourcesConfig »)."""
    from hydra_etl.mcp import server as S

    monkeypatch.setenv("HYDRA_MCP_WORKSPACE", str(tmp_path))
    job = tmp_path / "jobs" / "x"
    job.mkdir(parents=True)
    (job / "sources.yaml").write_text(
        "sources:\n  orders_db:\n    type: sqlite\n    connection:\n      path: ../../data/shop.db\n"
        "    table: orders\n", encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  out:\n    type: csv\n    file: ../../outputs/r.csv\n", encoding="utf-8")
    (job / "transformations.yaml").write_text(
        "transformations:\n  a:\n    input: orders_db\n", encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  - from: a\n    to: out\n", encoding="utf-8")
    ok, text = S._hdrctl("validate", str(job))
    assert not ok
    assert "sources.orders_db.extract: missing" in text
    assert "destinations.out.load: missing" in text
    assert "validation error" not in text
    for name in ("sources.yaml", "destinations.yaml", "transformations.yaml", "pipeline.yaml"):
        assert f"{name}:" in text
    assert text.count("Expected shape:") == 4
    assert "a mapping, not a list" in text


# --- Paths written from the project root instead of the job folder (MCP campaign) ---

def test_chemin_depuis_la_racine_refuse_avec_le_bon_chemin(call):
    (call.workspace / "data").mkdir()
    (call.workspace / "data" / "products.csv").write_text("id,nom\n1,a\n", encoding="utf-8")
    (call.workspace / "outputs").mkdir()
    src = SOURCES.replace("table: ventes.csv", "table: data/products.csv")
    out = call("hydra_write_job", job_path="jobs/load", sources_yaml=src,
               destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSED"), out
    assert "'../../data/products.csv'" in out
    assert not (call.workspace / "jobs" / "load").exists()
    dst = DESTINATIONS.replace("table: sortie.csv", "table: outputs/r.csv")
    out = call("hydra_write_job", job_path="jobs/load",
               sources_yaml=SOURCES.replace("table: ventes.csv", "table: ../../data/products.csv"),
               destinations_yaml=dst, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSED") and "'../../outputs/r.csv'" in out
    out = call("hydra_write_job", job_path="jobs/load",
               sources_yaml=SOURCES.replace("table: ventes.csv", "table: ../../data/products.csv"),
               destinations_yaml=dst.replace("outputs/r.csv", "../../outputs/r.csv"), pipeline_yaml=PIPELINE_OK)
    assert out.startswith("WRITTEN") and "Note:" not in out


def test_source_absente_signalee_sans_refus(call):
    out = call("hydra_write_job", job_path="jobs/later",
               sources_yaml=SOURCES.replace("table: ventes.csv", "table: ../../outputs/later.csv"),
               destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("WRITTEN") and "does not exist yet" in out


def test_workflow_chemin_de_job_depuis_la_racine_refuse(call):
    (call.workspace / "jobs" / "a").mkdir(parents=True)
    wf = ('version: "1.0"\nworkflow:\n  name: daily\n  steps:\n'
          '    - name: a\n      type: job\n      job: jobs/a\n')
    out = call("hydra_write_workflow", workflow_path="workflows/daily.yaml", workflow_yaml=wf)
    assert out.startswith("REFUSED") and "'../jobs/a'" in out
    out = call("hydra_write_workflow", workflow_path="workflows/daily.yaml",
               workflow_yaml=wf.replace("job: jobs/a", "job: ../jobs/a"))
    assert out.startswith("WRITTEN")


def test_refus_de_workflow_sans_chemin_temporaire(call):
    out = call("hydra_write_workflow", workflow_path="workflows/x.yaml",
               workflow_yaml='name: x\nversion: "1.0"\nworkflow:\n  name: x\n  steps: []\n')
    assert out.startswith("REFUSED")
    assert "hydra_mcp_wf_" not in out and "workflows/x.yaml" in out


def test_connecteurs_en_lecture_seule_annonces(call):
    """The model must know that web_api and the CDC sources cannot be destinations."""
    from pathlib import Path

    import hydra_etl.internal.connector as conn
    from hydra_etl.mcp.server import SOURCE_ONLY

    out = call("hydra_list_connectors")
    only = out.split("Source only (cannot be a destination):")[1].splitlines()[0]
    assert {"web_api", "postgresql_cdc", "postgres_cdc"} == {c.strip() for c in only.split(",")}
    assert "csv" in out.split("Source only")[0]
    assert "snowflake" in out.split("Source only")[0]       # source and destination since 0.21
    web_api = (Path(conn.__file__).parent / "web_api_connector_v2.py").read_text(encoding="utf-8")
    assert "def load_batches" not in web_api  # still read-only: keep SOURCE_ONLY in sync
    assert set(SOURCE_ONLY) <= set(call("hydra_list_connectors").replace(",", " ").split())


def test_base_path_relatif_au_dossier_du_job(call):
    """connection.base_path was resolved from the process' current folder: the job read files
    outside the workspace (in the Hydra ETL install folder)."""
    (call.workspace / "data").mkdir()
    (call.workspace / "data" / "p.csv").write_text("id,nom\n1,a\n2,b\n", encoding="utf-8")
    src = ('version: "1.0"\nsources:\n  src:\n    type: csv\n    connection:\n      base_path: ../../data\n'
           '    extract:\n      table: p.csv\n')
    dst = DESTINATIONS.replace("table: sortie.csv", "table: ../../outputs/p.csv")
    out = call("hydra_write_job", job_path="jobs/p", sources_yaml=src, destinations_yaml=dst,
               pipeline_yaml=PIPELINE_OK)
    assert out.startswith("WRITTEN") and "Note:" not in out, out
    out = call("hydra_run_job", job_path="jobs/p")
    assert out.startswith("RUN SUCCEEDED"), out
    assert (call.workspace / "outputs" / "p.csv").exists()


def test_chemin_hors_espace_de_travail_refuse(call):
    src = SOURCES.replace("table: ventes.csv", "table: ../../../secret.csv")
    out = call("hydra_write_job", job_path="jobs/x", sources_yaml=src,
               destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSED") and "outside the workspace" in out
    src = ('version: "1.0"\nsources:\n  src:\n    type: csv\n    connection:\n      base_path: /etc\n'
           '    extract:\n      table: hosts\n')
    out = call("hydra_write_job", job_path="jobs/x", sources_yaml=src,
               destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSED") and "outside the workspace" in out


def test_base_path_relatif_a_la_racine_du_projet(call):
    """In a project (.hydra/project.json), a relative base_path starts from the project root."""
    (call.workspace / ".hydra").mkdir()
    (call.workspace / ".hydra" / "project.json").write_text('{"id": "t", "name": "t"}', encoding="utf-8")
    (call.workspace / "data").mkdir()
    (call.workspace / "data" / "p.csv").write_text("id,nom\n1,a\n", encoding="utf-8")
    src = ('version: "1.0"\nsources:\n  src:\n    type: csv\n    connection:\n      base_path: data\n'
           '    extract:\n      table: p.csv\n')
    dst = DESTINATIONS.replace("table: sortie.csv", "table: ../../outputs/p.csv")
    out = call("hydra_write_job", job_path="jobs/deep/p", sources_yaml=src, destinations_yaml=dst.replace(
        "../../outputs", "../../../outputs"), pipeline_yaml=PIPELINE_OK)
    assert out.startswith("WRITTEN") and "Note:" not in out, out
    out = call("hydra_run_job", job_path="jobs/deep/p")
    assert out.startswith("RUN SUCCEEDED"), out


def test_source_sqlite_en_ligne_dans_une_jointure_verifiee(call):
    """A join's inline sqlite source with a path written from the project root (seen in Claude Code:
    `database: Data/shop.db`) is refused with the right path, like the sources of sources.yaml."""
    import sqlite3

    (call.workspace / "Data").mkdir()
    con = sqlite3.connect(call.workspace / "Data" / "shop.db")
    con.executescript("create table orders(id int, cid int); insert into orders values (1, 7);"
                      "create table customers(cid int, country text); insert into customers values (7, 'FR');")
    con.close()
    src = ('version: "1.0"\nsources:\n  o:\n    type: sqlite\n    connection:\n      database: ../../Data/shop.db\n'
           '    extract:\n      table: orders\n')
    tr = ('version: "1.0"\nsteps:\n  - join:\n      right:\n        type: sqlite\n        connection:\n'
          '          database: Data/shop.db\n        extract:\n          table: customers\n      key: cid\n')
    dst = DESTINATIONS.replace("table: sortie.csv", "table: ../../outputs/r.csv")
    pipe = PIPELINE_OK.replace("from: src", "from: o")
    out = call("hydra_write_job", job_path="jobs/r", sources_yaml=src, transformations_yaml=tr,
               destinations_yaml=dst, pipeline_yaml=pipe)
    assert out.startswith("REFUSED") and "join.right" in out and "'../../Data/shop.db'" in out, out
    out = call("hydra_write_job", job_path="jobs/r", sources_yaml=src,
               transformations_yaml=tr.replace("database: Data/shop.db", "database: ../../Data/shop.db"),
               destinations_yaml=dst, pipeline_yaml=pipe)
    assert out.startswith("WRITTEN"), out
    (call.workspace / "outputs").mkdir(exist_ok=True)
    out = call("hydra_run_job", job_path="jobs/r")
    assert out.startswith("RUN SUCCEEDED"), out
    assert "FR" in (call.workspace / "outputs" / "r.csv").read_text(encoding="utf-8")


def test_suppression_de_job_vers_la_corbeille(call):
    """hydra_delete_job: never while a workflow runs the job; the folder goes to .hydra/trash."""
    import json

    ws = call.workspace
    (ws / ".hydra").mkdir()
    (ws / ".hydra" / "project.json").write_text(json.dumps(
        {"id": "t", "jobs": [{"name": "job1", "path": "jobs/job1"}, {"name": "r", "path": "jobs/r"}]}), encoding="utf-8")
    for j in ("job1", "r"):
        out = call("hydra_write_job", job_path=f"jobs/{j}", sources_yaml=SOURCES,
                   destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
        assert out.startswith("WRITTEN"), out
    wf = ('version: "1.0"\nworkflow:\n  name: w\n  steps:\n    - name: job1\n      type: job\n      job: ../jobs/job1\n')
    assert call("hydra_write_workflow", workflow_path="workflows/w.yaml", workflow_yaml=wf).startswith("WRITTEN")

    out = call("hydra_delete_job", job_path="jobs/job1")
    assert out.startswith("REFUSED") and "workflows/w.yaml" in out
    assert (ws / "jobs" / "job1" / "pipeline.yaml").exists()

    wf2 = wf.replace("name: job1", "name: r").replace("../jobs/job1", "../jobs/r")
    assert call("hydra_write_workflow", workflow_path="workflows/w.yaml", workflow_yaml=wf2).startswith("WRITTEN")
    out = call("hydra_delete_job", job_path="jobs/job1")
    assert out.startswith("MOVED to trash"), out
    assert not (ws / "jobs" / "job1").exists()
    trashed = list((ws / ".hydra" / "trash").glob("*/jobs/job1/pipeline.yaml"))
    assert len(trashed) == 1
    jobs = json.loads((ws / ".hydra" / "project.json").read_text(encoding="utf-8"))["jobs"]
    assert [j["path"] for j in jobs] == ["jobs/r"]

    assert call("hydra_delete_job", job_path="workflows").startswith(("REFUSED", "Folder not found"))
    assert call("hydra_delete_job", job_path="../x").startswith("REFUSED")
