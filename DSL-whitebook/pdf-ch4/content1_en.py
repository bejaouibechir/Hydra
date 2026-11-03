"""Pages 3 à la fin (EN) : 1. Workflows (dont 1.4 Sous-projets, 0.19), 2.1, 2.2 ;
la suite vient de content2_en (2.3 → 3) puis content_en (4)."""
from xml.sax.saxutils import escape as e
import content2_en
R = lambda t: ("role", "Role. " + e(t))
P = lambda t: ("p", e(t))
NEW = " (Hydra 0.19.0+)"

CH1 = [
("h1", "1. Workflows"),
P("Files: workflows/<name>.yaml and workflows/thread.yaml."),
("h2", "1.1 The workflow"),
("h3", "version: DSL format version"),
("code", 'version: "1.0"      # currently always "1.0"'),
R("allows the engine to validate the file against the appropriate grammar."),
("h3", "workflow: workflow root"),
("code", '''workflow:           # all workflow content sits under this key
  name: daily_sales'''),
R("declares a sequence of steps (jobs, actions and projects)."),
("h3", "name: workflow name (required)"),
("code", '''workflow:
  name: daily_sales     # identifier in logs and undo file'''),
R("identifies the workflow; also used by hdrctl workflow undo."),
("h3", "description: free-text description"),
("code", 'description: "Load today\'s sales"'),
R("documentation only; does not affect execution."),
("h3", "trigger: trigger (default: manual)"),
("code", "trigger: manual        # manual | schedule | webhook"),
R("indicates when the workflow starts."),
("h3", "cron: schedule (required with trigger: schedule)"),
("code", '''trigger: schedule
cron: "0 6 * * *"      # every day at 06:00'''),
R("five-field cron expression specifying the start time."),
("h3", "rollback: rollback on failure (default: false)"),
("code", "rollback: true         # undo completed steps when one fails"),
R("triggers undo operations for completed steps in reverse order."),
("h3", "steps: list of steps (required)"),
("code", '''steps:
  - name: load
    type: job
    job: ../jobs/orders'''),
R("contains the steps executed by the workflow."),

("h2", "1.2 The step"),
("h3", "name: unique step name (required)"),
("code", "- name: load_orders     # referenced in depends_on"),
R("identifies the step and allows other steps to depend on it."),
("h3", "type: step type (required)"),
("code", "type: job             # job | action | project"),
R("specifies whether the step runs a job, an action or another project (section 1.4)."),
("h3", "job: job path (with type: job)"),
("code", '''type: job
job: ../jobs/orders     # directory containing sources/destinations/pipeline'''),
R("points to the job directory to execute."),
("h3", "action: action name (with type: action)"),
("code", '''type: action
action: log             # one of 11 actions (see section 3)'''),
R("selects the action to execute."),
("h3", "params: action parameters"),
("code", '''action: log
params:
  message: "Start loading"'''),
R("provides the action inputs; supports {{ param: }} and ${SECRET:}. With type: project, the parameters passed to the called project."),
("h3", "depends_on: dependencies (default: [])"),
("code", '''- name: publish
  depends_on: [load, clean]     # starts after load AND clean finish'''),
R("builds the execution graph; independent steps can run in parallel."),
("h3", "on_failure: failure behavior (default: fail)"),
("code", "on_failure: continue     # fail | skip | continue"),
R("fail stops the workflow; skip omits dependent steps; continue still executes them."),
("h3", "enabled: enables/disables the step (default: true)"),
("code", "enabled: false    # skip the step without deleting it"),
R("temporarily disables the step."),
("h3", "when: execution condition"),
("code", 'when: "{{ param:publish_enabled }} == True"      # run only if true'),
R("runs the step according to a safe expression (parameters or another step's result)."),
("h3", "retry: retry policy"),
("code", '''retry:
  max: 3               # retries after the first failure
  delay: 10            # seconds to wait
  backoff: exponential      # fixed | exponential (delay doubled)'''),
R("handles transient failures (network or database unavailability)."),
("h3", "undo: action undo procedure"),
("code", '''type: action
action: bash
params: { command: "touch /tmp/flag" }
undo:
  action: bash
  params: { command: "rm /tmp/flag" }      # executed when rollback: true'''),
R("required for webhook, email, bash, powershell, ssh and python (or use undo: none). A job is undone automatically; a project step cannot be undone, so rollback: true refuses it."),

("h2", "1.3 The thread"),
("h3", "thread: root of thread.yaml"),
("code", '''thread:               # list of stages
  - mode: sequential
    workflows:
      - name: load_referentials'''),
R("sets the execution order of all project workflows (hdrctl run .)."),
("h3", "mode: stage execution mode (default: sequential)"),
("code", "mode: parallel        # sequential | parallel"),
R("runs workflows within a stage sequentially or in parallel."),
("h3", "delay_after: delay after the stage"),
("code", "delay_after: 5m       # wait before the next stage"),
R("allows an external system to stabilize."),
("h3", "workflows: workflows in the stage (at least one)"),
("code", '''workflows:
  - name: load_sales
  - name: load_stock'''),
R("lists the workflows run by the stage (workflows/<name>.yaml)."),
("h3", "active: enables/skips a workflow (default: true)"),
("code", '''- name: load_stock
  active: false'''),
R("disables a workflow without changing its definition."),
("h3", "delay_before: pre-start delay"),
("code", '''- name: build_reports
  delay_before: 30s'''),
R("delays the start of a workflow."),
("h3", "timeout: time limit"),
("code", '''- name: load_sales
  timeout: 20m        # exceeding limit causes failure'''),
R("prevents a workflow from blocking the thread indefinitely."),
("h3", "fallback: replacement workflow"),
("code", '''- name: load_sales
  fallback:
    use: [load_sales_backup]          # workflows tried in order
    when: "not source_available('crm')"
    on_failure: true                  # also replaces after failure
    on_probe_error: keep              # keep | replace if condition cannot be evaluated'''),
R("switches to an alternative workflow when the condition is true."),
("h3", "use / when / on_failure / on_probe_error: fallback keys"),
P("See above. Role: use lists replacements; when selects fallback before start; on_failure also covers failures; on_probe_error handles conditions that cannot be evaluated."),
("h3", "loops: replay a segment of the thread"),
("code", '''loops:
  - from: load_stock         # last workflow in segment
    to: load_sales           # first workflow in segment
    times: 3                 # total executions (1 to 1000)
    delay: 10m               # wait before each replay'''),
R("repeats a sequence (polling or batch processing)."),
("h3", "Functions available in fallback when conditions"),
("table", ([["Function", "Role"],
            ["source_available('id')", "the source responds"],
            ["destination_available('id')", "the destination responds"],
            ["file_exists('path')", "the file exists"],
            ["file_size('path')", "size, compared with 10KB, 5MB, 1GB"],
            ["file_age('path')", "age, compared with 30s, 5m, 24h, 7d"],
            ["url_ok('url')", "HTTP response 2xx/3xx"],
            ["secret_defined('NAME')", "the secret exists"],
            ["db.load('id')", "active database queries"],
            ["previous.status", "success · failed · skipped · inactive · none"],
            ["previous.rows", "rows written by the previous workflow"]], [10, 200])),
("h3", "Example"),
("code", '''fallback:
  use: [load_sales_light]
  when: "db.load('dwh') > 50 or file_size('in/orders.csv') > 1GB"'''),

("h2", "1.4 Sub-projects: type: project" + NEW),
P("A step of type project runs another Hydra project: its thread.yaml, or only the workflows listed. The calling project is the master; the called projects are its sub-projects. Nothing passes implicitly except the environment."),
("h3", "project: the called project (required with type: project)"),
("code", '''- name: crm_sync
  type: project
  project: ../crm_sync      # folder, relative to the master's root'''),
R("designates the project to run. In Hydra Studio, drop a project from the Projects section of the palette: the step is created after a cycle check."),
("h3", "ref: how project is read (default: path)"),
("code", '''ref: path      # path: folder, portable with git (default)
ref: name      # name: project name in the Studio workspace'''),
R("chooses between a path stored in the repository and a workspace name."),
("h3", "env: environment of the called project (default: inherit)"),
("code", "env: inherit   # inherit | none | <environment name>, e.g. prod"),
R("inherit applies the master's environment name with the called project's own environments/<env>.yaml, env.<env> variables and secrets.<env>; none runs without environment."),
("h3", "params: parameters passed to the called project"),
("code", '''params:
  batch_date: "{{ param:run_date }}"   # same rank as -P batch_date=...'''),
R("gives values to the called project's parameters. A required parameter without a value stops the step before anything runs."),
("h3", "variables: environment variables lent for this run"),
("code", '''variables:
  EXPORT_DIR: out/crm       # visible only inside the called project'''),
R("lends variables for the duration of the run; the master's own variables, .env and --env-file are not passed."),
("h3", "Secrets are never passed"),
("code", '''variables:
  DB_PASSWORD: "${SECRET:crm_db}"   # refused: each project keeps its own secrets'''),
R("a ${SECRET:...} in params or variables is refused at validation: the called project reads its own .hydra/secrets."),
("h3", "workflows: workflows to run (default: the thread.yaml)"),
("code", "workflows: [ingest, report]     # run one after the other"),
R("runs part of the called project instead of its whole thread."),
("h3", "outputs: parameters read back by the master"),
("code", '''outputs: [last_batch]
# next steps: {{ project:crm_sync.param.last_batch }}'''),
R("lists parameters of the called project (set_param, assign_param or declared) to read once it ends. A listed output that is not published fails the step."),
("h3", "isolation: where the project runs (default: inprocess)"),
("code", "isolation: inprocess    # inprocess | subprocess"),
R("inprocess runs in the same process with an isolated environment, restored afterwards; subprocess starts a separate hdrctl. Steps running in parallel always use subprocess."),
("h3", "timeout: maximum duration"),
("code", "timeout: 10m        # 30s, 5m, 1h or a number of seconds"),
R("stops the called project when exceeded; the step fails."),
("h3", "overlap: project already running (default: wait)"),
("code", "overlap: wait      # wait | skip | fail"),
R("a project runs once at a time (.hydra/run.lock): wait waits for the end (up to timeout), skip skips the step, fail fails it."),
("h3", "Results of the called project"),
("table", ([["Placeholder", "Value"],
            ["{{ project:STEP.status }}", "success · failed · skipped"],
            ["{{ project:STEP.rows }}", "rows written by the called project"],
            ["{{ project:STEP.duration }}", "duration in seconds"],
            ["{{ project:STEP.param.NAME }}", "a parameter listed in outputs"]], [10, 200])),
("code", '''- name: report
  type: action
  action: log
  when: "{{ project:crm_sync.status }} == 'success'"
  params: { message: "{{ project:crm_sync.rows }} rows synced" }
  depends_on: [crm_sync]'''),
R("lets the next steps of the master react to the called project."),
("h3", "Cycles and nesting"),
("code", '''hdrctl workflow validate main     # prints the tree of called projects
#   ↳ crm_sync [ingest, report]
#      ↳ billing
# cycle: master → crm_sync → master   -> refused'''),
R("a project cannot call itself, directly or through others; more than 5 levels is refused. Checked by hdrctl run, workflow validate, Studio and the MCP tool hydra_project_calls; a project computed with {{ }} is checked at run time."),
("h3", "hdrctl run -w: run only some workflows"),
("code", "hdrctl run ../crm_sync -w ingest -w report --env prod"),
R("runs the listed workflows of a project, in order, from the command line."),

("h2", "1.5 Project triggers: triggers.yaml" + NEW),
P("triggers.yaml, at the root of a project, starts the whole project (its thread.yaml, or the workflows listed) when an event happens. A workflow trigger: starts one workflow; a project trigger starts the project. They run inside hdrctl watch and hdrctl serve."),
("h3", "triggers, name, type"),
("code", '''version: "1.0"
triggers:
  - name: nightly         # unique name
    type: cron            # cron | interval | file | marker | source_change | webhook | after_project'''),
R("lists the triggers; type selects the event and its keys (a key of another type is refused)."),
("h3", "cron, timezone: at given times"),
("code", '''type: cron
cron: "0 2 * * *"         # minute hour day month weekday; */15, mon-fri, jan…
timezone: Europe/Paris    # default: the machine's time'''),
R("runs the project when the time matches. Runs missed while nothing was watching are not replayed."),
("h3", "every: interval"),
("code", '''type: interval
every: 15m                # 30s, 5m, 1h or seconds'''),
R("runs the project at a regular period."),
("h3", "path, events, debounce: a file arrives"),
("code", '''type: file
path: inbox/*.csv         # inside the project; ** for subfolders
events: [added, modified] # default [added]
debounce: 2s              # unchanged this long before it is taken (default 2s)
every: 5s                 # how often the folder is checked (default 5s)'''),
R("runs the project for new or changed files; files arriving together give one run, which receives {{ param:trigger.file }} and {{ param:trigger.files }}."),
("h3", "marker, consume: a marker file appears"),
("code", '''type: marker
path: inbox/READY
consume: true             # removed before the run (default); false keeps it'''),
R("runs the project when another system says the data is ready."),
("h3", "source: a source changes"),
("code", '''type: source_change
source: {job: jobs/ingest, id: orders, check: count}   # count | max (+ column) | checksum
every: 1m                 # default 1m'''),
R("measures a source of a job (built as in a run); the first measure is the reference, a different one starts the project with {{ param:trigger.value }} and {{ param:trigger.previous }}."),
("h3", "token: webhook"),
("code", '''type: webhook
token: ${SECRET:trigger.on_push.token}   # a secret reference only
# hdrctl trigger token on_push  → creates the value, shown once
# POST /api/projects/<id>/triggers/on_push/webhook   X-Hydra-Token: <token>'''),
R("lets another system start the project through hdrctl serve; a wrong token gets 401 and nothing from the request reaches the project."),
("h3", "project, on: after another project"),
("code", '''type: after_project
project: ../crm           # ref: path (default) or ref: name
on: success               # success | failure | any'''),
R("starts the project when another one ends, whatever started it; the run receives {{ param:trigger.project }} and {{ param:trigger.status }}. A loop a → b → a is refused."),
("h3", "env, workflows, params, overlap, timeout, retry, enabled"),
("code", '''env: prod                 # default: --env / HYDRA_ENV of watch or serve
workflows: [ingest]       # default: thread.yaml
params: {mode: full}      # like -P; no secret
overlap: skip             # skip (default) | wait | fail
timeout: 1h
retry: {max: 2, delay: 5m}
enabled: false'''),
R("set what runs and how; the project always runs in its own process, under .hydra/run.lock, and every run is recorded in .hydra/triggers/history.jsonl."),
("h3", "hdrctl trigger, hdrctl watch"),
("code", '''hdrctl trigger validate        # keys, cron, workflows, sources, secrets, loops
hdrctl trigger list            # triggers and their last run
hdrctl trigger fire nightly    # run one now
hdrctl trigger history
hdrctl watch --env prod        # run the triggers until Ctrl+C'''),
R("hdrctl watch runs the triggers without Studio; hdrctl serve runs the same engine for the projects of the Studio list."),
]

CH2 = [
("pagebreak", None),
("h1", "2. Jobs"),
P("Directory: jobs/<name>/ with sources.yaml, destinations.yaml, pipeline.yaml, transformations.yaml (optional)."),
("h2", "2.1 Sources (sources.yaml)"),
("h3", "sources: root"),
("code", '''version: "1.0"
sources:
  orders:              # "orders" is the source ID
    type: csv'''),
R("declares at least one source that can then be referenced by ID."),
("h3", "type: connector (required)"),
("code", "type: postgresql   # csv, json, parquet, mysql/mariadb, postgresql/postgres, sqlserver/mssql, mongodb"),
R("selects the reader connector; case-insensitive."),
("h3", "connection: connection settings"),
("code", '''connection:
  host: db.local
  port: 5432
  user: etl
  password: ${SECRET:db.password}         # never hard-code secrets
  database: sales'''),
R("configures access to the source ({} for a local file). SQL keys: host, port, user, password, database, schema; SQL Server: instance, tds_version, login_timeout, timeout."),
("h3", "extract: what to read (required)"),
("code", '''extract:
  table: orders.csv          # file, table, or...
  batch_size: 5000           # rows per batch (default 10000, minimum 10)'''),
R("defines the read operation; must contain table, query or collection."),
("h3", "table / query / collection"),
("code", '''extract: { table: public.orders }                          # table or file
extract: { query: "SELECT * FROM orders WHERE total>0" }   # SQL only
extract: { collection: orders }                            # MongoDB'''),
R("identifies the object to read."),
("h3", "filter and limit: MongoDB"),
("code", '''extract:
  collection: orders
  filter: { status: "paid" }        # query filter
  limit: 1000                       # maximum number of documents'''),
R("restricts the data retrieved from the database."),
("h3", "CSV options (in connection)"),
("code", '''connection:
  base_path: ./data      # base directory for table paths (default: job directory)
  delimiter: ";"         # default ,
  quotechar: '"'
  encoding: utf-8
  lineterminator: "\\n"
  strict_schema: false'''),
R("adapts reading to the file format."),
("h3", "schema: expected schema (MongoDB)"),
("code", '''schema:
  mode: infer_strict               # auto | manual | infer_strict | hybrid
  drift_policy: warn               # fail | warn | ignore | adapt
  validation_policy: strict        # strict | best_effort | permissive
  sample_size: 100                 # sampled documents
  fields:
    - name: total
      type: float                  # string, integer, float, decimal, boolean, date,
                                   # datetime, array, object, json
      path: amount.total
      required: true
      default: 0
      array_handling: flatten      # keep | flatten | explode | json
      description: "Amount"'''),
R("defines the expected document structure and response to new fields (schema drift)."),
("h2", "2.2 Destinations (destinations.yaml)"),
("h3", "destinations: root"),
("code", '''destinations:
  dwh_orders:          # destination ID
    type: postgresql'''),
R("declares where data is written."),
("h3", "table / collection: target"),
("code", "load: { table: dwh.orders }      # collection is an alias for MongoDB"),
R("specifies the destination table or file (required)."),
("h3", "mode: write mode (default: append)"),
("code", '''load:
  mode: upsert     # append | replace | upsert
  key: [order_id]  # required with upsert'''),
R("append adds rows; replace clears and writes; upsert inserts or updates using a key."),
("h3", "key: key columns"),
P("See above. Role: identifies a row for upsert."),
("h3", "batch_size: rows per write (10 to 100000; default 10000)"),
("code", "load: { batch_size: 20000 }"),
R("balances memory consumption and throughput."),
("h3", "atomic: all-or-nothing writes"),
("code", "load: { atomic: true }     # rolls back the whole write on error"),
R("avoids leaving the destination partially populated."),
]

REST = list(content2_en.SPEC)
if REST and REST[0][0] == "h2top":
    REST[0] = ("h2", REST[0][1])
SPEC = CH1 + CH2 + REST
HEADER = content2_en.HEADER
def _breaks(spec):
    """Chaque chapitre (h1) commence sur une nouvelle page."""
    out = []
    for item in spec:
        if item[0] == "h1" and out and out[-1][0] != "pagebreak":
            out.append(("pagebreak", None))
        out.append(item)
    return out


SPEC = _breaks(SPEC)
FOOTER = "hydraetl.com  ·  Hydra DSL v1.0  ·  Hydra 0.19.0"
