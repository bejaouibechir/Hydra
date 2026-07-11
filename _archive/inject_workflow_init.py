"""Injecte cmd_workflow_init dans cli/hdrctl.py."""
from pathlib import Path

TARGET = Path(__file__).parent / "cli" / "hdrctl.py"
content = TARGET.read_text(encoding="utf-8")

TEMPLATES = '''
# ─────────────────────────────────────────────────────────────────────────────
# Templates workflow
# ─────────────────────────────────────────────────────────────────────────────

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

'''

INIT_CMD = '''
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
    """Cree un fichier workflow.yaml depuis un template."""
    filename = name if name.endswith(".yaml") else f"{name}.yaml"
    dest = Path(filename).resolve()

    if dest.exists() and not force:
        error_box(t("workflow.init.exists", path=dest.name))
        sys.exit(1)

    raw = WORKFLOW_TEMPLATES[template]
    content_out = raw.format(name=name)
    dest.write_text(content_out, encoding="utf-8")

    success_box(t("workflow.init.success", name=name, path=dest.name))
    info(t("workflow.init.next", path=dest.name))
    click.echo()

'''

# Anchor : insérer les templates avant le groupe workflow
ANCHOR_TEMPLATES = "# Groupe de commandes : workflow"
# Anchor : insérer cmd_workflow_init après cmd_workflow_list

ANCHOR_CMD = "@cmd_workflow.command(\"list\""

if "WORKFLOW_TEMPLATES" in content:
    print("SKIP — already present")
else:
    # 1. Injecter les templates avant le groupe workflow
    idx = content.find(ANCHOR_TEMPLATES)
    if idx == -1:
        print("ERROR — templates anchor not found")
        exit(1)
    section_start = content.rfind("\n\n#", 0, idx)
    content = content[:section_start+2] + TEMPLATES + content[section_start+2:]

    # 2. Injecter cmd_workflow_init après cmd_workflow_list (trouver la fin de cmd_workflow_list)
    idx2 = content.find(ANCHOR_CMD)
    if idx2 == -1:
        print("ERROR — cmd anchor not found")
        exit(1)
    # Trouver la fin de cette fonction (prochain @cmd_workflow ou # ──)
    next_block = content.find("\n\n\n", idx2)
    if next_block == -1:
        print("ERROR — end of list cmd not found")
        exit(1)
    content = content[:next_block+3] + INIT_CMD + content[next_block+3:]

    TARGET.write_text(content, encoding="utf-8")
    print("OK — injected")

import py_compile
try:
    py_compile.compile(str(TARGET), doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax error: {e}")
