"""Remplace le bloc WORKFLOW_TEMPLATES + cmd_workflow_init dans cli/hdrctl.py
avec une version scaffold complète (dossiers + manifests + data).
"""
from pathlib import Path

TARGET = Path(__file__).parent / "cli" / "hdrctl.py"
content = TARGET.read_text(encoding="utf-8")

# Trouver l'ancre de début du bloc à remplacer
ANCHOR = "\n# ─────────────────────────────────────────────────────────────────────────────\n# Templates workflow"
idx = content.find(ANCHOR)
if idx == -1:
    print("ERROR — anchor not found"); exit(1)

# Garder tout ce qui précède
head = content[:idx]

# Nouveau bloc complet
NEW_BLOCK = r'''

# ─────────────────────────────────────────────────────────────────────────────
# Scaffold workflow : templates manifest + job manifests
# ─────────────────────────────────────────────────────────────────────────────

# workflow.yaml par template (les chemins pointent vers ./jobs/<step>)
WORKFLOW_TEMPLATES: dict[str, str] = {
    "basic": """\
workflow:
  name: "{name}"
  description: "Sequential pipeline: job_a → job_b → notify"
  trigger:
    type: manual
  steps:
    - name: "job_a"
      type: job
      job: "./jobs/job_a"
      depends_on: []
      on_failure: fail

    - name: "job_b"
      type: job
      job: "./jobs/job_b"
      depends_on: ["job_a"]
      on_failure: fail

    - name: "notify"
      type: action
      action: log
      params:
        message: "Workflow {name} completed successfully."
      depends_on: ["job_b"]
      on_failure: skip
""",

    "parallel": """\
workflow:
  name: "{name}"
  description: "Fan-out / fan-in: extract → [transform_a, transform_b] → load"
  trigger:
    type: manual
  steps:
    - name: "extract"
      type: job
      job: "./jobs/extract"
      depends_on: []
      on_failure: fail

    - name: "transform_a"
      type: job
      job: "./jobs/transform_a"
      depends_on: ["extract"]
      on_failure: fail

    - name: "transform_b"
      type: job
      job: "./jobs/transform_b"
      depends_on: ["extract"]
      on_failure: fail

    - name: "load"
      type: job
      job: "./jobs/load"
      depends_on: ["transform_a", "transform_b"]
      on_failure: fail
""",

    "scheduled": """\
workflow:
  name: "{name}"
  description: "Scheduled pipeline — runs daily at 08:00"
  trigger:
    type: schedule
    cron: "0 8 * * *"
  steps:
    - name: "extract"
      type: job
      job: "./jobs/extract"
      depends_on: []
      on_failure: fail

    - name: "transform"
      type: job
      job: "./jobs/transform"
      depends_on: ["extract"]
      on_failure: fail

    - name: "load"
      type: job
      job: "./jobs/load"
      depends_on: ["transform"]
      on_failure: fail

    - name: "notify"
      type: action
      action: log
      params:
        message: "Scheduled workflow {name} completed."
      depends_on: ["load"]
      on_failure: skip
""",

    "notify": """\
workflow:
  name: "{name}"
  description: "Pipeline with webhook notification on completion"
  trigger:
    type: manual
  steps:
    - name: "extract"
      type: job
      job: "./jobs/extract"
      depends_on: []
      on_failure: fail

    - name: "transform"
      type: job
      job: "./jobs/transform"
      depends_on: ["extract"]
      on_failure: fail

    - name: "load"
      type: job
      job: "./jobs/load"
      depends_on: ["transform"]
      on_failure: fail

    - name: "webhook_success"
      type: action
      action: webhook
      params:
        url: "https://hooks.example.com/notify"
        method: POST
        body:
          workflow: "{name}"
          status: "success"
      depends_on: ["load"]
      on_failure: skip
""",
}

VALID_WORKFLOW_TEMPLATES = list(WORKFLOW_TEMPLATES.keys())

# ─────────────────────────────────────────────────────────────────────────────
# Contenu des manifests générés pour chaque job scaffoldé
# ─────────────────────────────────────────────────────────────────────────────

def _sources_yaml(job_name: str) -> str:
    return f"""\
version: "1.0"
sources:
  src_{job_name}:
    type: csv
    connection: {{}}
    extract:
      table: data/input.csv
      batch_size: 1000
"""

def _destinations_yaml(job_name: str) -> str:
    return f"""\
version: "1.0"
destinations:
  dst_{job_name}:
    type: csv
    connection: {{}}
    load:
      table: data/output.csv
      mode: replace
"""

def _pipeline_yaml(job_name: str) -> str:
    return f"""\
version: "1.0"
pipeline:
  from: src_{job_name}
  to: dst_{job_name}
"""

def _transformations_yaml() -> str:
    return """\
version: "1.0"
transformations:
  steps:
    - filter:
        expr: "1 == 1"   # Remplacer par votre logique
"""

SAMPLE_CSV = """\
id,name,value
1,item_a,10.5
2,item_b,20.0
3,item_c,5.75
"""

ENV_EXAMPLE = """\
# Variables d'environnement pour ce workflow
# Copier ce fichier en .env et remplir les valeurs

# DB_HOST=localhost
# DB_PORT=3306
# DB_USER=hydra
# DB_PASS=secret
"""


def _scaffold_job(jobs_dir: Path, job_name: str) -> list[str]:
    """Crée le dossier d'un job et retourne la liste des fichiers créés."""
    job_dir = jobs_dir / job_name
    data_dir = job_dir / "data"
    job_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    files = []
    for fname, content_fn in [
        ("sources.yaml",        lambda: _sources_yaml(job_name)),
        ("destinations.yaml",   lambda: _destinations_yaml(job_name)),
        ("pipeline.yaml",       lambda: _pipeline_yaml(job_name)),
        ("transformations.yaml",lambda: _transformations_yaml()),
    ]:
        path = job_dir / fname
        path.write_text(content_fn(), encoding="utf-8")
        files.append(str(path.relative_to(job_dir.parent.parent)))

    sample = data_dir / "input.csv"
    sample.write_text(SAMPLE_CSV, encoding="utf-8")
    files.append(str(sample.relative_to(job_dir.parent.parent)))
    return files


def _extract_job_steps(workflow_yaml: str) -> list[str]:
    """Extrait les noms des steps de type job depuis le YAML workflow."""
    import re
    job_names = []
    for line in workflow_yaml.splitlines():
        m = re.match(r'\s+job:\s+"?\.\/jobs\/([^"]+)"?', line)
        if m:
            job_names.append(m.group(1).strip())
    return job_names


# ─────────────────────────────────────────────────────────────────────────────
# Commande : hydra workflow init
# ─────────────────────────────────────────────────────────────────────────────

@cmd_workflow.command("init", help=t("help.workflow.init.docstring"))
@_lang_option
@click.argument("name", metavar="NAME")
@click.option("--template", "-t", default="basic",
              type=click.Choice(VALID_WORKFLOW_TEMPLATES),
              show_default=True,
              help=t("help.workflow.init.template"))
@click.option("--force", is_flag=True, default=False,
              help=t("help.workflow.init.force"))
def cmd_workflow_init(name: str, template: str, force: bool) -> None:
    """Scaffolde un projet workflow complet (dossiers + manifests)."""
    project_dir = Path(name).resolve()

    if project_dir.exists() and not force:
        error_box(t("workflow.init.exists", path=name))
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir = project_dir / "jobs"
    jobs_dir.mkdir(exist_ok=True)

    # Écrire workflow.yaml
    raw_template = WORKFLOW_TEMPLATES[template]
    workflow_content = raw_template.format(name=name)
    workflow_file = project_dir / "workflow.yaml"
    workflow_file.write_text(workflow_content, encoding="utf-8")

    # Écrire .env.example
    (project_dir / ".env.example").write_text(ENV_EXAMPLE, encoding="utf-8")

    # Scaffolder chaque job référencé dans le template
    job_names = _extract_job_steps(workflow_content)
    created_jobs = []
    for job_name in job_names:
        _scaffold_job(jobs_dir, job_name)
        created_jobs.append(job_name)

    # Affichage
    success_box(t("workflow.init.success", name=name, path=str(project_dir.name)))

    click.echo()
    info(f"  {project_dir.name}/")
    info(f"  ├── workflow.yaml")
    info(f"  ├── .env.example")
    info(f"  └── jobs/")
    for i, job in enumerate(created_jobs):
        prefix = "    └──" if i == len(created_jobs) - 1 else "    ├──"
        info(f"  {prefix} {job}/")
        info(f"  {'      ' if i == len(created_jobs) - 1 else '  │   '}  ├── sources.yaml")
        info(f"  {'      ' if i == len(created_jobs) - 1 else '  │   '}  ├── destinations.yaml")
        info(f"  {'      ' if i == len(created_jobs) - 1 else '  │   '}  ├── pipeline.yaml")
        info(f"  {'      ' if i == len(created_jobs) - 1 else '  │   '}  ├── transformations.yaml")
        info(f"  {'      ' if i == len(created_jobs) - 1 else '  │   '}  └── data/input.csv")

    click.echo()
    info(t("workflow.init.next", path="workflow.yaml"))
    click.echo()
'''

TARGET.write_text(head + NEW_BLOCK, encoding="utf-8")
print("OK — written")

import py_compile
try:
    py_compile.compile(str(TARGET), doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax error: {e}")
