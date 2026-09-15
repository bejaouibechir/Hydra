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


def test_liste_les_18_operations(call):
    lignes = [l for l in call("hydra_list_operations").splitlines() if l.strip()]
    assert len(lignes) == 18
    assert any(l.startswith("cast") for l in lignes)


def test_operation_inconnue_propose_les_existantes(call):
    out = call("hydra_describe_operation", operation="lowercase")
    assert "inconnue" in out.lower()
    assert "clean" in out          # la bonne piste est donnee au modele


# --- Garantie 1 : aucune ecriture sans validation ---------------------------

def test_ecriture_valide(call):
    out = call("hydra_write_job", job_path="jobs/ventes",
               sources_yaml=SOURCES, destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_OK, transformations_yaml=TRANSFORMATIONS)
    assert out.startswith("ÉCRIT")
    job = call.workspace / "jobs" / "ventes"
    assert (job / "pipeline.yaml").exists()
    assert (job / "transformations.yaml").exists()


def test_cablage_casse_refuse_et_n_ecrit_rien(call):
    out = call("hydra_write_job", job_path="jobs/casse",
               sources_yaml=SOURCES, destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_KO)
    assert out.startswith("REFUSÉ")
    assert "inexistant" in out              # la raison est rendue au modele
    assert not (call.workspace / "jobs" / "casse").exists()


def test_yaml_invalide_refuse_sans_appeler_la_cli(call):
    out = call("hydra_write_job", job_path="jobs/pasyaml",
               sources_yaml="sources: [", destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSÉ")
    assert "YAML" in out
    assert not (call.workspace / "jobs" / "pasyaml").exists()


def test_correction_apres_refus(call):
    call("hydra_write_job", job_path="jobs/cycle", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_KO)
    assert not (call.workspace / "jobs" / "cycle").exists()

    out = call("hydra_write_job", job_path="jobs/cycle", sources_yaml=SOURCES,
               destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    assert out.startswith("ÉCRIT")
    assert (call.workspace / "jobs" / "cycle" / "pipeline.yaml").exists()


# --- Garantie 2 : l'agent ne sort pas de l'espace de travail ----------------

@pytest.mark.parametrize("chemin", ["../..", "../../../etc", "/etc", "..\\..\\.."])
def test_evasion_refusee(call, chemin):
    for outil in ("hydra_read_job", "hydra_validate_job", "hydra_run_job"):
        out = call(outil, job_path=chemin)
        assert out.startswith("REFUSÉ"), f"{outil} a laissé passer {chemin!r}"


def test_ecriture_hors_espace_refusee(call):
    out = call("hydra_write_job", job_path="../evade",
               sources_yaml=SOURCES, destinations_yaml=DESTINATIONS,
               pipeline_yaml=PIPELINE_OK)
    assert out.startswith("REFUSÉ")
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
    assert out.startswith("ÉCRIT")
    assert (call.workspace / "wf" / "quotidien.yaml").exists()
    assert "wf/quotidien.yaml" in call("hydra_list_workflows")
    assert "quotidien" in call("hydra_read_workflow",
                               workflow_path="wf/quotidien.yaml")


def test_workflow_invalide_refuse_sans_ecrire(call):
    out = call("hydra_write_workflow", workflow_path="wf/casse.yaml",
               workflow_yaml=WORKFLOW_KO)
    assert out.startswith("REFUSÉ")
    assert not (call.workspace / "wf" / "casse.yaml").exists()


def test_workflow_evasion_refusee(call):
    out = call("hydra_read_workflow", workflow_path="../../secret.yaml")
    assert out.startswith("REFUSÉ")


# --- Voir les données -------------------------------------------------------

def test_preview_montre_colonnes_et_lignes(call):
    (call.workspace / "ventes.csv").write_text(
        "id,nom,montant\n1,a,150\n2,b,50\n", encoding="utf-8")
    out = call("hydra_preview_data", file_path="ventes.csv")
    assert "montant" in out and "150" in out
    assert "cast" in out.lower()          # le piege des types est rappele


def test_preview_refuse_hors_espace(call):
    assert call("hydra_preview_data",
                file_path="../../../etc/passwd").startswith("REFUSÉ")


# --- Coherence avec la demande ---------------------------------------------

def test_check_job_signale_une_operation_absente(call):
    call("hydra_write_job", job_path="jobs/sans_tri", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    out = call("hydra_check_job",
               user_request="trie les ventes par montant decroissant",
               job_path="jobs/sans_tri")
    assert out.startswith("ALERTES")
    assert "sort" in out


def test_check_job_signale_un_connecteur_absent(call):
    call("hydra_write_job", job_path="jobs/en_csv", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    out = call("hydra_check_job",
               user_request="charge le resultat dans postgres",
               job_path="jobs/en_csv")
    assert out.startswith("ALERTES")
    assert "postgres" in out


def test_check_job_sans_alerte_quand_conforme(call):
    call("hydra_write_job", job_path="jobs/simple", sources_yaml=SOURCES,
         destinations_yaml=DESTINATIONS, pipeline_yaml=PIPELINE_OK)
    out = call("hydra_check_job",
               user_request="copie ventes.csv dans sortie.csv",
               job_path="jobs/simple")
    assert out.startswith("AUCUNE ALERTE")


# --- Exemples ---------------------------------------------------------------

def test_find_example_privilegie_un_job_pertinent(call):
    out = call("hydra_find_example",
               user_request="joindre commandes et clients", count=1)
    assert "### Exemple" in out
    assert "sources.yaml" in out
