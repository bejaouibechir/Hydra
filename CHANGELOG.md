# Changelog

All notable changes to Hydra ETL are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).


## [Unreleased]

### Added

- PostgreSQL CDC source — **the replication slot is checked before each run**: retained WAL, `wal_status` and
  `safe_wal_size` (PostgreSQL 13+). Above `lag_warning_mb` (new connection key, 1024 MB by default, `0` turns it
  off), or when less than that is left before `max_slot_wal_keep_size`, the run writes a warning: a mirror that
  keeps failing makes the source keep its WAL and can fill its disk. A slot past `max_slot_wal_keep_size`
  (`wal_status = unreserved`) is reported too.
- PostgreSQL CDC source — **a slot invalidated by PostgreSQL makes the run fail** (`wal_status = lost`, for
  example after `max_slot_wal_keep_size`), with the steps to rebuild the mirror: drop the slot, empty the
  destination, run again. The changes made since the last success can no longer be read; the run no longer
  goes on with a gap.
- Fallback conditions — `cdc.slot_lag('source')` (WAL kept by the slot of a `postgresql_cdc` source, compared
  with `500MB`, `2GB`) and `cdc.slot_status('source')` (`reserved`, `extended`, `unreserved`, `lost`, `missing`).
  A fallback can run a workflow that sends an alert (webhook, email) and then the same job, before the source's
  disk fills up. DSL white book: « Alert on a CDC replication slot ».
- `examples/postgres-cdc-mirror` — « When the load keeps failing: protect the source »: `max_slot_wal_keep_size`,
  what Hydra ETL does in each state of the slot, and the query to watch it.
- README — « PostgreSQL CDC: protect the source ».

- Studio — the terminal opens in **tabs**, as in VS Code: **+** opens a new terminal (pwsh or bash), × closes one,
  and each session keeps running when another tab, or LOGS / PARAMETERS / SECRETS, is shown. The terminal button
  of a PowerShell or Bash action opens a new tab.
- Studio — **paste** in the terminal: Ctrl+V or Ctrl+Shift+V, and **Paste** in the right-click menu. Ctrl+C copies
  when text is selected (otherwise it interrupts the command, as before); Ctrl+Shift+C copies.

## [0.20.0] — 2026-11-10

### Added

- **SQLite connector** (`type: sqlite`), source and destination, built in: `sqlite3` is part of Python, nothing to
  install, no server. `connection.path` is the database file, relative to the job folder. Source: `table` or
  `query`; a missing file is an error and is never created by a read or by `hdrctl test`. Destination: the file
  and the table are created at the first batch (types from the data; in `upsert` the key becomes the primary
  key); `append`, `replace`, `upsert` (`INSERT … ON CONFLICT … DO UPDATE`, primary key or unique index required
  on an existing table, with the `CREATE UNIQUE INDEX` to run in the error). All-or-nothing by default in the
  three modes (one transaction, table creation included; `load.atomic: false` commits batch by batch).
  `rollback: true` undoes a SQLite load; `source_change` triggers count and max with one SQL query. The
  database uses the WAL journal, so a job can read one table while it writes another in the same file.
- Studio — **SQLite** source and destination nodes in the palette: database file, table or SQL query; in
  destination, mode, key columns for `upsert` and all-or-nothing. Read from and written to the YAML files like
  the other nodes; **View data** reads the destination table. The node catalogue of the API (`/api/nodes`) lists
  SQLite, and its descriptions are in English. The data viewer also reads SQL Server destinations (it fell back
  to CSV).
- VS Code extension 0.1.10: `type: sqlite` in `sources.yaml` and `destinations.yaml` (`connection.path`
  required, server keys refused), `sqlserver` / `mssql` in the list of types; snippets `hsrc-sqlite`,
  `hdst-sqlite`.
- **Snowflake connector** (`type: snowflake`), read-only source (`pip install "hydra-etl[snowflake]"`).
  `connection`: `account`, `user`, `password` (or `private_key_file` / `authenticator`), `warehouse`,
  `database`, `schema`, `role`. Source: `table` (`table`, `schema.table` or `database.schema.table`) or
  `query`, which must start with SELECT, WITH, SHOW or DESCRIBE; `extract.limit` is applied. Values keep their
  exact type: `NUMBER(p,0)` → integers, even beyond 64 bits; `NUMBER(p,s)` → exact decimals; `DATE` → dates;
  `TIMESTAMP_NTZ` → timestamps without time zone; `TIMESTAMP_TZ` / `TIMESTAMP_LTZ` → timestamps with their time
  zone; `VARIANT`, `OBJECT`, `ARRAY` → JSON values (`connection.json: text` keeps the JSON text).
  `connection.column_case: lower` lowercases the column names (what PostgreSQL expects); two columns that only
  differ by case are refused before any row is read. Reads Arrow batches when the driver provides them,
  otherwise `fetchmany`, with the same values. Refused as a destination. Every query is tagged `hydra-etl`
  (`QUERY_TAG`). `source_change` triggers count and max with one SQL query. An unknown account
  (`404 Not Found` at login) gets a hint on the expected `connection.account` format.
- **PostgreSQL CDC source** (`type: postgresql_cdc`, alias `postgres_cdc`): the changes of a table (inserts,
  updates, deletes) read by logical replication (`pgoutput` plugin, nothing to install on the server), in the order
  of the transactions. `connection`: the usual PostgreSQL keys plus `slot` and `publication`, created at the first
  run (`create: false` to require them); `extract.table`. The first run reads the whole table (`snapshot: false` to
  skip it), the next runs only the changes. Each row carries `_op` (`snapshot`, `insert`, `update`, `delete`),
  `_lsn` and `_commit_time`; values keep their PostgreSQL type (integers, exact decimals, dates, timestamps with
  their time zone, JSON). The changes are read without being consumed, and the slot only moves on after the
  destination has published (the job confirms the source at the end): a failed load reads the same changes again
  at the next run. A workflow with `rollback: true` refuses a CDC source. Needs `wal_level = logical`, PostgreSQL 11+
  and a role with `REPLICATION`. Example: `examples/postgres-cdc-mirror`.
- PostgreSQL destination — in `upsert`, rows that carry `_op` (from a CDC source) are applied as changes: the last
  change of each key in a batch wins, deletes are applied by key, an update whose large value was not changed
  (TOAST) keeps the current value, and `_op`, `_lsn`, `_commit_time` are not written. In `append`, they are all
  written (a log of the changes).
- Studio — **Snowflake** source node in the palette: account, user, private key file or password, warehouse,
  database, schema, role, column names (`preserve` / `lower`), JSON columns (`parse` / `text`), table or SELECT
  query. Read from and written to `sources.yaml` like the other nodes; a field emptied in the form is removed
  from the file, and references such as `{{ env:SNOWFLAKE_ACCOUNT }}` are kept as written.
- Studio — **PostgreSQL CDC** source node: host, port, database, user, password, table, replication slot,
  publication, and two yes / no lists (create slot and publication if missing; first run copies the whole table).
- VS Code extension 0.1.11: `type: snowflake` in `sources.yaml` (`account` and `user` required, unknown
  connection keys refused, `column_case` and `json` offered as lists, `extract.query` limited to SELECT /
  WITH / SHOW / DESCRIBE), refused in `destinations.yaml`; snippet `hsrc-snowflake`.
- VS Code extension 0.1.12: `type: postgresql_cdc` / `postgres_cdc` in `sources.yaml` (`user`, `database`, `slot`,
  `publication` required, slot and publication names checked, `create` and `snapshot` booleans, `extract.table`
  required and `extract.query` refused), refused in `destinations.yaml`; snippet `hsrc-cdc`.

### Changed

- PostgreSQL destination — a table created by Hydra ETL now gets exact types from all the values of the first
  batch: exact decimals and integers beyond 64 bits → `NUMERIC` (decimals were `TEXT`), dates → `DATE` (were
  `TIMESTAMP`), timestamps with a time zone → `TIMESTAMPTZ` (the time zone was dropped), dicts and lists →
  `JSONB` (were refused). In `upsert`, a missing table is created with the key as primary key (the load used to
  fail and ask for a `CREATE UNIQUE INDEX`); an existing table still needs a primary key or unique index on the
  key. Existing tables are not changed.
- PostgreSQL destination — an integer too large for a `smallint`, `integer` or `bigint` column is reported before
  the batch is written, with the column, the value and the `ALTER TABLE … TYPE NUMERIC(38,0)` to run (the error
  was `bigint out of range`, without the column).
- PostgreSQL destination — rows are written in multi-row statements of 1,000 rows instead of one statement per
  row, in the three modes (in `upsert`, a batch that holds the same key twice is still written row by row, so the
  last row wins as before). In `append`, a missing table is now created at the first batch, as in `replace` and
  `upsert`.

### Fixed

- Studio — saving no longer damages the YAML files written by hand: a file whose content did not change is not
  rewritten at all; a changed file keeps, for every unchanged line, its original text (quotes, inline lists,
  end-of-line comments) and the comments above it. The `description` of a workflow is kept, and Studio no longer
  adds `trigger: {type: manual}` or `pipeline.name` to files that did not have them.
- Studio — a workflow file added on disk after the project was opened (by `hdrctl`, `git pull`, or after Studio's
  metadata was deleted) now appears in the project's list without reopening the project. A YAML file of
  `workflows/` that is not a workflow is no longer listed as one.

## [0.19.1] — 2026-11-05

### Fixed

- `aggregate` with `sum` or `mean` on a text column concatenated the values instead of adding them
  (`"19.9" + "49.9"` → `"19.949.9"`), with no error: a CSV column read without `cast` is text, so a job that
  re-read a CSV written by another job produced a wrong total. The step now fails with
  `aggregate.agg.revenue: sum needs a numeric column ('amount' is object). Add a cast step before aggregate,
  for example: cast: {mapping: {amount: float}}`. Same message with the large-volume engine (DuckDB hands the
  step back to pandas instead of raising a Binder Error). `count`, `min`, `max`, `first` and `last` still
  accept text.
- The `log` action's message was written to the logger only, so `hdrctl run` did not show it. It is now the
  step's output: shown under the step, like the output of a script action, and kept in the run result.
- Error messages still in French are in English: transformations (`select`, `rename`, `cast`, `filter`,
  `calculate`, `clean`, `join`, `merge`, `union`, `script`, `transpose`, `aggregate`), manifest checks
  (`clean.case must be none, lower or upper`, `join.how`, cast types), the job runner (`Cannot create the
  source 'raw_orders' (type='csv')`, `Step 2/3: …` instead of `Erreur à l'étape 2/3`), parameters, `.env`
  files, the MCP workspace guard and the API routes.

### Added

- `examples/end-to-end-retail`: a master project runs two sub-projects in parallel, then a job and actions
  read what they returned. Files only, runs in a few seconds.

## [0.19.0] — 2026-11-04

### Added

- Workflow step `type: project`: a workflow of a "master" project runs another project (its `thread.yaml`, or
  only the `workflows` listed, one after the other). Keys: `project` (path relative to the master's root, or with `ref: name` the
  name of a project of the Studio workspace), `env` (`inherit` by default, `none` or a name), `params`,
  `variables`, `workflows`, `outputs`, `isolation` (`inprocess` by default, or `subprocess`). Nothing is
  passed implicitly except the environment, and a called project keeps its own secrets: `${SECRET:…}` in
  `params` or `variables` is refused.
- Called projects are checked by `hdrctl run` (and `--dry-run`), `hdrctl workflow validate` and the Studio
  Check: missing or ambiguous project, cycles (`cycle: a → b → a`, a project calling itself), more than 5
  levels. `hdrctl workflow validate` prints the tree of the called projects. A project computed with
  `{{ … }}` is reported as checked only at run time. `rollback: true` refuses a `type: project` step.
- Running a called project: in the same process by default, its environment cleaned of the caller's — the
  caller's `.env`, `--env-file`, `--secrets-file` and the global variables of its environment do not leak — and
  restored afterwards; or `isolation: subprocess`. Steps that run in parallel (parallel stage, steps without a
  dependency between them) always use a separate process. `params` have the rank of `-P`; a `required`
  parameter of the called project without a value stops the step before anything runs. A cycle missed by
  validation (computed path) is stopped at run time.
- Results of a called project, readable by the next steps of the master workflow (`when`, any field):
  `{{ project:STEP.status }}` (`success`, `failed`, `skipped`), `{{ project:STEP.rows }}` (rows written),
  `{{ project:STEP.duration }}`, and `{{ project:STEP.param.NAME }}` for each name listed in `outputs` — a
  parameter of the called project at the end of its run (`set_param`, `assign_param`, or declared). A listed
  output that the project does not publish fails the step. The output shows the called project as a tree
  (workflows, steps, their output).
- `timeout` on a `type: project` step (30s, 5m, 1h): in the same process the called project stops at its next
  checkpoint, and its following workflows do not start; in a separate process the process is stopped.
- A called project runs once at a time (lock `.hydra/run.lock`, also between processes; a lock left by a
  process that no longer exists is taken over). `overlap`: `wait` (default, until `timeout`), `skip` (step
  skipped, status `skipped`) or `fail`.
- `hdrctl run <project> -w <workflow>` (repeatable): run only these workflows of the project.
- Studio — **Project** node (third node type of a workflow, next to actions and jobs): a **Projects** section in
  the palette lists the projects open in Studio; dropping one adds a `type: project` step after an API check
  (a cycle such as `master → crm → master`, or a project calling itself, is refused with the path). Its window
  sets the project (by path, portable with git — saved relative — or by workspace name), environment,
  workflows to run, parameters (the called project's declarations are listed, `required` ones flagged),
  variables, outputs, process, timeout, overlap and on-failure, and links to the called project. The side
  panel summarises the step. The step is read from and written to `workflow.yaml` like the other steps.
- Project triggers, `triggers.yaml` at the project root (lot 2.1: file, checks and manual run; the engine
  that watches the events comes with `hdrctl watch`). Types: `cron` (`cron`, `timezone`), `interval`
  (`every`), `file` (`path` glob, `events: [added, modified]`, `debounce`), `marker` (`path`, `consume`),
  `source_change` (`source: {job, id, check: count | max | checksum, column}`), `webhook` (`token` — a
  `${SECRET:…}` reference only), `after_project` (`project`, `ref`, `on: success | failure | any`). Common
  keys: `env`, `workflows` (default: the thread), `params` (no secret), `overlap` (`skip` by default),
  `timeout`, `retry: {max, delay}`, `enabled`, `description`. A trigger always runs the project in a
  separate process, under its `.hydra/run.lock`.
- `hdrctl trigger list | validate | fire <name> | history`. `validate` also checks the workflows listed, the
  projects they call, the job and source of `source_change`, the secret of a webhook (warning), and refuses
  `after_project` loops (`a → b → a`). `fire` runs the project now as the trigger would, with its retries
  (`--no-retry`). Every run is recorded in `.hydra/triggers/history.jsonl` (last 1000, not versioned).
- `hdrctl watch [PROJECT]... [--env]` runs the triggers of one or more projects (lot 2.2: `cron` and
  `interval`; the other types are loaded, checked and listed as not watched yet — `hdrctl trigger fire`
  runs them). It prints each trigger with its next run, then every start and end; a change to
  `triggers.yaml` is picked up without restarting (an invalid file keeps the previous triggers running).
  A trigger still running is not started again (the missed run is recorded as `skipped`); runs missed while
  watch was stopped are not replayed. Ctrl+C stops starting new runs and waits for the running projects
  (they run in their own process group, out of reach of the Ctrl+C); a second Ctrl+C stops at once.
- `hdrctl watch` also watches files (lot 2.3): `file` (a file matching `path` is added or, with
  `events: [added, modified]`, modified) and `marker` (a marker file such as `inbox/READY` appears; it is
  removed before the run, `consume: false` keeps it). The folder is checked every `every` (default 5s); a
  file is taken once it has stayed unchanged for `debounce` (default 2s), so a file still being copied is not
  read half-written. Files already there when watch starts do not trigger; a file deleted then created again
  does. Files arriving together start one run, which receives the parameters `{{ param:trigger.file }}` (the
  first) and `{{ param:trigger.files }}` (all, comma-separated). A file arriving during a run is not lost: it
  starts the next run once this one ends. `path` accepts `**` for subfolders. Remote folders (SFTP, S3) share
  the same file-event interface and will come later.
- `hdrctl watch` also watches data (lot 2.4): a `source_change` trigger measures a source of one of the
  project's jobs every `every` (default 1m) — `check: count` (rows), `max` (largest value of `column`, numbers
  compared as numbers, dates and text as text) or `checksum` — and starts the project when the value changes.
  The first measure is the reference; the run receives `{{ param:trigger.value }}` and
  `{{ param:trigger.previous }}`. The source is built as in a run (parameters, secrets, environment). On
  PostgreSQL, MySQL/MariaDB and SQL Server, `count` and `max` are a single `SELECT COUNT(*)` / `SELECT MAX(col)`
  on the table or the query of `extract`; a file source with `checksum` hashes the file; other cases read
  the rows. A measure runs apart from the engine (a slow database does not hold up the other triggers); a
  failed measure is reported and the reference kept; a change during a run starts the next run.
- Project webhooks and the trigger engine in `hdrctl serve` (lot 2.5). `hdrctl trigger token <name>
  [--env] [--rotate]` creates the token of a `webhook` trigger: a random value saved as the secret named by
  its `token:` (`.hydra/secrets`, or `.hydra/secrets.<env>`), shown once with the address to call. A caller
  starts the project with `POST /api/projects/{id}/triggers/{name}/webhook` and the header
  `X-Hydra-Token: <token>` (or `Authorization: Bearer <token>`): the token is compared in constant time; a
  missing or wrong token gets 401, an unknown or non-webhook trigger 404, a token not set yet 503; nothing
  from the request is passed to the project. Also `GET /api/projects/{id}/triggers` (triggers, next run,
  last run, problems), `GET …/triggers/history` and `POST …/triggers/{name}/fire` (run now, any type; 409
  if already running). `hdrctl serve` now runs the same engine as `hdrctl watch` for every project of the
  Studio list (followed when a project is opened or removed); environment: the trigger's `env:`, else
  `HYDRA_ENV`. Keep `hdrctl serve` on `127.0.0.1` unless a reverse proxy with HTTPS stands in front of it.
- `after_project` triggers are watched (lot 2.6): the end of another project starts this one, according to
  `on: success` (default), `failure` or `any`. Every project run — `hdrctl run`, Studio, a trigger, a
  `type: project` step — now notes its end in `.hydra/triggers/ends.jsonl` (status, workflows, duration,
  environment; last 1000, not versioned), read by `hdrctl watch` and `hdrctl serve` every 5s, whichever
  process ran the project. Ends older than the start of the engine are ignored; ends during a run of the
  watching project give one more run, with the most recent end. The run receives
  `{{ param:trigger.project }}` and `{{ param:trigger.status }}`. Loops (`a → b → a`) are refused by
  `hdrctl trigger validate` and are not watched.
- VS Code extension 0.1.9: `triggers.yaml` — the seven types and their keys, a key of another type refused,
  `path` kept inside the project, `token` as a `${SECRET:…}` reference only, `check: max` requires `column`;
  snippets `htriggers` and `hptrig-cron`, `-interval`, `-file`, `-marker`, `-source`, `-webhook`, `-after`.
- MCP: `hydra_project_triggers` (read-only) — the triggers of a project, what they run, the next run of a
  cron trigger, the last runs and the problems; a webhook token by its secret name only.
- Studio — **Project settings › Triggers** (step 3): the triggers of the project with their event, what they
  run, environment, next run, running state and last run (refreshed every 5s); add or edit a trigger in a
  form per type (cron presets and time zone, interval, file path and events, marker, source chosen among
  the project's jobs, webhook token reference, project to wait for and `on`), with environment, workflows,
  parameters, overlap, timeout and retries; enable/disable, delete, **Run now**; create or replace a webhook
  token (shown once, with PowerShell and curl calls); history of the runs. Each change writes
  `triggers.yaml` (comments are not kept; the previous file is copied to `~/.hydra/_backups`); an invalid
  trigger or a change that `hdrctl trigger validate` would refuse is not written.
- API: `PUT /api/projects/{id}/triggers` (write triggers.yaml, 422 with the problems) and
  `POST /api/projects/{id}/triggers/{name}/token` (`rotate`, `env`; 409 if a token exists).
  `GET …/triggers` also returns each trigger's `config`, `token_set`, and the project's workflows and job
  sources.
- Cron expressions are read by Hydra itself (no extra package): `*`, lists, ranges, steps, month and day
  names, 0 or 7 for Sunday; as in cron, when both day-of-month and day-of-week are set, either one matches.
  `timezone` takes an IANA name (`Europe/Paris`; `tzdata` is now installed with Hydra on Windows);
  without it, the machine's time.
- API: `POST /api/projects/{id}/project-step` — what a `type: project` step would call (parameters,
  workflows, environments of the called project) and the problems it would create.
- VS Code extension 0.1.8: `type: project` in `workflow.yaml` — its keys, completion and hover help, `project`
  required, `${SECRET:…}` refused in `params` and `variables`, project keys refused on `job` and `action`
  steps; snippet `hstep-project`.
- MCP: `hydra_project_calls` (read-only) — the `type: project` steps of a project, the tree of the called
  projects, and the problems (project not found, cycle, more than 5 levels).

### Fixed

- Workflow actions lost the values of the environment (`environments/<env>.yaml`) when a `required`
  parameter was given at run time (`-P`, `params` of a `type: project` step): `{{ param:X }}` fell back
  to the defaults, while the jobs of the same run used the environment.
- `hdrctl workflow run` refuses a workflow whose `type: project` steps form a cycle, call a project that
  cannot be found or nest more than 5 levels, before anything runs (as `hdrctl run` and
  `hdrctl workflow validate`).
- An optional `{{ env:NAME }}` (or a parameter without value) inside a text is replaced by an empty
  string instead of `None`.
- Parameter errors are in English: `missing required parameter`, `unresolved parameter`,
  `missing environment variable`.

### Documentation

- White paper (FR/EN, `DSL-whitebook/`): chapter 1 gets **1.4 Sub-projects: type: project**; `type`,
  `params` and `undo` mention project steps; chapters 1 to 4 regenerated, each starting on a new page.
  `03-workflows.md`: new *Sub-projects* section. README: sub-projects in *Workflows*.
- White paper (FR/EN): **1.5 Project triggers: triggers.yaml**. `03-workflows.md`: new *Project triggers*
  section. README: *Project triggers* in *Workflows*.

## [0.18.0] — 2026-11-02

### Added

- Global environment variables, shared by every project of the machine: `~/.hydra/env` (all
  environments) and `~/.hydra/env.<env>` (one environment: dev, prod…), selected by `--env` /
  `HYDRA_ENV`. Location: `HYDRA_HOME` (default `~/.hydra`). Order, weakest first: `env` < `env.<env>` <
  project `.env` < job `.env` < `--env-file`; as for `.env` files, a file wins over a variable already set
  in the system. When a run switches environment (Studio, API), the variables of the previous one are
  removed. Workflow actions now see these variables and the project `.env` from the first step.
- Secrets per environment: `.hydra/secrets.<env>` (plain or SOPS-encrypted) wins over `.hydra/secrets`
  when the run uses `--env <env>`; `sops.file` accepts `{env}` (`.hydra/secrets.{env}.sops.yaml`).
  `.gitignore` written by `hdrctl init` ignores `.hydra/secrets.*` but keeps `.hydra/secrets.yaml` and
  SOPS-encrypted files.
- `--env-file FILE` on `hdrctl run` and `hdrctl workflow run`: extra variables for one run, above every
  other layer. A missing file stops the run.
- `hdrctl workflow run` accepts `--env` and `-P/--param`, like `hdrctl run`.
- `hdrctl env list|show|create|rename|delete|set|unset`: environments and global variables. `create`
  writes `~/.hydra/env.<name>` and, in a project, `environments/<name>.yaml`; `rename` and `delete` also
  move/remove the parameter values and `.hydra/secrets.<name>`, after a copy to `~/.hydra/_backups/`.
- `hdrctl param list|set|unset`: parameters of a project — declaration and default value in
  `parameters.yaml` (`--type`, `--description`, `--required`), value per environment with `--env`.
- `hdrctl secret list|set|delete`: secrets of a project, common or per environment (`--env`). The value
  is typed hidden or read from stdin (`--stdin`), never passed as an argument; `list` shows names only.

- Studio — active environment: a selector on the project page and in the editor header (shared, kept
  per project). Run project, Run Workflow, running a job, a step or an action node use it: global variables,
  parameter values and secrets of that environment. The Expression Assistant shows the same environment.
- Studio — Global settings › Environments: create, rename and delete environments and edit their global
  variables (`~/.hydra/env`, `~/.hydra/env.<env>`), saved on the machine that runs Hydra.
- Studio — Project settings gets the tabs Execution order, Parameters (one column per environment;
  `parameters.yaml` + `environments/<env>.yaml`) and Secrets (common or per environment, names only).
- API: `/api/global-env` (environments and global variables; `/names` lists the environments of the machine
  and of a project); `/api/secrets` accepts `env`; inline job and action runs accept `env`.

- VS Code extension 0.1.7: schemas for `parameters.yaml`, `environments/<env>.yaml` and
  `.hydra/secrets.yaml`; snippets `hparams`, `hparam`, `henv`, `hsecrets-sops`, `hrefparam`, `hrefsecret`,
  `hrefenv`.
- MCP: `hydra_project_settings` (read-only) lists the environments, the names of the global variables, the
  parameters per environment and the names of the secrets; never a secret or variable value.
  `hydra_run_workflow` accepts `env`.

- `parameters.yaml` accepts the short form `name: value` (a parameter of type `any` with that default); it
  used to stop the run with an internal error.
- Documentation: README (parameters, environments and secrets), `docs/MCP.md`, DSL white papers (chapter 4).

### Fixed

- `hdrctl run jobs/<job>` now reads the `.env` at the project root (the folder that contains `.hydra/`),
  not only the one of the job's parent folder.
- Workflow actions `bash`, `powershell` and `python` without `working_dir` now run in the project root,
  whatever the current folder; a relative `working_dir` is resolved from the project root. Scheduled and
  webhook runs (started by `hdrctl serve`) used to run in the server's folder, so relative paths failed.
- Studio: opening a project whose `.hydra/project.json` has no `id` (written by hand) gave it the id `""`;
  the id is now added to the file. The `schedule` workflows of a project opened in Studio are planned at once
  instead of at the next start of `hdrctl serve`.
- Studio runs with no environment selected sent `env: "default"`, which looked for `environments/default.yaml`;
  "default" now means no environment.

## [0.17.0] — 2026-11-01

### Added

- Studio: the **Expression Assistant** (SSIS-style) now lists the project's **Parameters**, with type,
  default and value in the **active environment** shown in its header (shared with the Parameters tab), and
  **Environment variables** (required `${ENV:NAME}` or optional `{{ env:NAME }}`). Double-click an item, or
  drag it into the edit area; **Insert** writes the result into the field. It opens from **fx** on
  expressions (Derive, Filter) and from a new **{x}** button on the fields where a reference is useful
  (file paths, host, port, database, schema, user, table, SQL query, URL, `fill_null` value, `max_rows`,
  action commands, recipients, timeouts…); there it also lists the **Secrets** (`${SECRET:name}`), and
  password fields offer secrets and environment variables only. Numeric fields accept a reference;
  references are kept as written in the YAML files.
- Secrets are masked everywhere Hydra shows or keeps text: logs (every logger, step logs, API), error
  messages, tracebacks, the output of `bash`, `powershell`, `python` and `ssh` actions, `webhook` and
  `email` log lines, the rollback (undo) report and the runs stored by the API. The values sent to
  connectors, scripts and webhooks are unchanged. URL-encoded and JSON-escaped forms are masked too.
- Secrets visibility, as in GitLab: `plain` (debugging, with a warning), `masked` (default, `[MASKED]`) or
  `hidden` (lines that contain a secret are dropped and counted). Set it in `.hydra/secrets.yaml`
  (`visibility:`), with `HYDRA_SECRETS_VISIBILITY` or with `--secrets-visibility` on `hdrctl run` and
  `hdrctl workflow run`. Values shorter than 4 characters are not masked; a warning names them.
- `.hydra/secrets.yaml`: project secrets settings (no secret inside, safe to commit) — `visibility`,
  `provider` and the provider block. Unknown keys, values and providers are reported, never ignored.
- SOPS provider (`provider: sops`, `sops.file`, optional `sops.format` and `sops.age_key_file`): secrets
  encrypted with [SOPS](https://github.com/getsops/sops) (age, PGP, cloud KMS) are decrypted in memory, on
  first use; nested YAML/JSON keys are read as `${SECRET:db.password}`. A SOPS-encrypted `.hydra/secrets`
  or `--secrets-file` is detected and decrypted as well; Studio refuses to edit an encrypted file.
- Provider interface (`SecretProvider`, `register_provider`) for external vaults.
- `join` with `how: cross`: cartesian product (every row × every row of `right`, in order), no key
  (`key`, `left_key`, `right_key` are refused). Guard `max_rows` (default 10,000,000 rows produced,
  counted over all batches): the run stops before producing the batch that would exceed it.
- `text_to_rows`: one row per value of a text column (`"a;b;c"` → 3 rows, other columns copied).
  Options: `sep` (default `,`), `regex`, `trim` (default true), `keep_empty` (default false) and
  `index_column` (position 1, 2, 3…). A null value, or one with no non-empty part, keeps one row with a
  null value: no input row is lost. Unknown options are refused.
- `window` (window functions): adds columns, keeps every row in its input order. `partition_by`
  (optional), `order_by` (columns or `{col, desc}`; nulls last, ties kept in input order),
  `columns: {name: {func: ...}}` with:
  - rank: `row_number`, `rank`, `dense_rank`;
  - offset: `lag`, `lead` (`col`, `offset` ≥ 1, `default`);
  - running: `cumsum`, `cumcount`, `cummin`, `cummax` (a null value is skipped, the row keeps the running
    value);
  - whole partition: `sum`, `mean`, `min`, `max`, `count`, `first`, `last` (nulls ignored, as in
    `aggregate`; `order_by` optional, used by `first` / `last`).

  Rank, offset and running functions require `order_by`; `cumsum`, `cummin`, `cummax`, `sum` and
  `mean` require a numeric column. Global operation: with the large-volume engine it runs in DuckDB
  (`OVER (PARTITION BY … ORDER BY …)`), same rows, values and types as pandas; a case DuckDB cannot
  guarantee is handed to pandas.
- Studio: **Text to Rows** and **Window** nodes in the palette; **Window** has a row editor (output name,
  function grouped by family, column, offset, default) with a JSON mode. The **Join** node offers
  `cross`: the key fields are hidden and a *Max rows* field appears. Round-trips with the YAML files keep
  every option and its type.
- DSL specification (`hydra_etl/ai/schemas`, `tools/spec_export.py`): JSON schemas for `text_to_rows` and
  `window` (functions, options and their types), `join.how: cross` and `join.max_rows`; 20 operations.
- MCP server: `hydra_list_operations` lists the 20 operations; `hydra_explain_error` explains the new
  errors (`order_by` missing, `max_rows`, key given with `how: cross`, `text_to_rows`, non-numeric column
  in a window); `hydra_check_job` warns when a request asks for ranks, running totals, one row per value
  or every combination and the job lacks `window`, `text_to_rows` or `join`.
- VS Code extension 0.1.6 (`vscode-extension/`): schema and snippets for the three additions.

### Fixed

- Studio: the **Script** node showed a generic icon in the palette and its configuration dialog.
- Studio: the **MySQL** and **PostgreSQL** nodes show the official logos (from the CC0 `simple-icons`
  package) instead of hand-drawn shapes; the **SQL Server** node showed a generic icon in the palette and
  now shows a database icon.

### Unchanged

- `${SECRET:NAME}` syntax and lookup order: environment (normalised, then exact name) > local secrets file
  > configured provider.

## [0.16.1] — 2026-11-01

### Fixed

- MongoDB source: `schema.drift_policy` (`fail` / `warn` / `adapt` / `ignore`) was inoperative. The `schema`
  block never reached the connector, and documents were normalised before drift detection. Now:
  `fail` raises `SchemaDriftError` naming the field and the document; `warn` logs each new field once plus a
  summary; `adapt` extends the schema; `ignore` stays silent. `schema.sample_size` is honoured.
  Regression tests: `tests/test_mongodb_drift.py`.

## [0.16.0] — 2026-10-29

### Added

- `engine: auto | pandas | duckdb` in `transformations.yaml` (root or under `transformations:`) chooses the
  engine of a job's global operations; `HYDRA_ENGINE` still takes precedence. Studio: **Engine** selector
  on a job's canvas, kept on round-trips with the YAML files. JSON schemas (Hydra DSL, VS Code) updated.
- Large-volume engine: right and outer `join` run in DuckDB, with the same rows, columns, order and types
  as pandas; only the columns the following aggregation needs are copied. 20 million rows, right join then
  aggregation (2 CPUs): 71.8 s / 3.4 GB → 27.7 s / 2.6 GB.

### Changed

- `sort` is stable: rows with equal sort keys keep their input order (it was so already for several
  columns, not always for one).

## [0.15.0] — 2026-10-29

### Added

- **Large-volume engine** (optional, `pip install "hydra-etl[duckdb]"`, which now also installs pyarrow):
  above `HYDRA_LARGE_VOLUME_ROWS` estimated rows (2,000,000 by default), a job with a global operation
  reads its CSV source with pyarrow and runs `aggregate` and `sort` in a temporary DuckDB database on
  disk; pandas keeps every other step and stays the default below the threshold. `HYDRA_ENGINE=auto |
  pandas | duckdb`. No silent fallback: an untranslatable global step goes back to pandas with a log
  message, the fast reader hands over to the Python reader with a warning. On 20 million rows (2 CPUs):
  112.8 s / 5.4 GB → 34.3 s / 1.4 GB, identical results.
- `--profile` shows the engine chosen and why.

## [0.14.0] — 2026-10-28

### Added

- Studio Project settings: a **wait** field on each workflow of the execution
  order (`delay_before`: `500ms`, `30s`, `5m`, `1h`; empty = no wait), checked
  before Save. The Preview shows an orange clock and the duration above the
  block; the run page shows a *waited …* badge on the step, and "Not started —
  another workflow of the stage failed" for a parallel start cancelled by a
  failure. The run API returns `waited` (seconds) on each step.
- **Fallback after a failure** (`fallback.on_failure: true`, step 5b): a
  workflow that fails is replaced by its first backup, only if it left nothing
  published — no load published and no outside action done (except actions
  marked `undo: none`), or everything undone by `rollback: true`. If the backup
  fails too, the next one in `use` runs. Otherwise the project stops with the
  reason (`⛔ … fallback … not started — step 'load1' had already published its
  data`). The replaced run is reported as *recovered* (CLI `↯`, Studio badge
  *replaced by …*); the project succeeds if the backup does.
- `thread.yaml`: **`timeout`** per workflow (`30s`, `5m`, `1h`, more than 0):
  beyond it the workflow is stopped at the next step or batch (an
  all-or-nothing load is cancelled; an action already started finishes) and
  counts as failed, which can trigger the fallback. Shown by `--dry-run`, in
  Studio (**max** field, ⏳ in the Preview, *timed out* badge on the run page),
  in the VS Code schema and in the Hydra DSL reference.
- `hdrctl run --dry-run` (and Studio's **Check**) warns when a workflow with
  `on_failure` publishes in several steps without `rollback: true`.

### Changed

- Studio: the fallback option "also after a failure" is applied (the "not
  applied yet" note is gone).
- CLI: durations of whole minutes or hours are shown as `5m`, `1h`.

- Studio: **Settings** has two tabs. *Global settings*: the editor
  preferences, kept in this browser. *Project settings*: the execution order
  of the current project (Define, Preview, Check, loops, fallbacks), written in
  `workflows/thread.yaml`, with the project name and path. It opens on the
  project of the link (`/settings/project/<id>`), else on the last project
  opened in this browser, else asks for one.
- Studio project page: the workflows, plus **Project settings** and **Run
  project** (checks the project first; errors are listed with a link to
  Project settings).
- Studio asks before leaving the execution order with unsaved changes.
- A workflow opened from the Preview opens on its Workflow configuration
  tab, and returns to Project settings.

## [0.13.0] — 2026-10-26

### Added

- `thread.yaml`: a workflow can declare a **fallback** — backup workflow(s),
  kept outside the thread, with `use` (tried in order), `when` (condition
  checked just before the start), `on_failure` (also after a failure) and
  `on_probe_error` (`keep` by default). Step 1 of the fallback mechanism: the
  fallback is declared, saved and checked; the switch at run time comes next.
- `when` conditions use a closed language analysed by Hydra (never Python
  `eval`): `source_available`, `destination_available`, `file_exists`,
  `file_size`, `file_age`, `url_ok`, `secret_defined`, `db.load`,
  `previous.status`, `previous.rows`, `and` / `or` / `not`, comparisons,
  durations (`24h`) and sizes (`5MB`). Names reserved for future performance
  rules (`estimate`, `resources`, `volume`, `deadline`) are refused for now.
- `hdrctl run <project> --dry-run` (and Studio's **Check**) checks fallbacks:
  backup files and their jobs, sources / destinations named in `when`; it
  shows each fallback and warns when a backup writes to other destinations
  than the workflow it replaces. `POST /api/projects/{id}/check` returns
  `warnings`.
- `hdrctl workflow add <name> --fallback-for <workflow>` creates a backup
  workflow and declares it; `workflow list` shows backups as
  `fallback of …`; `workflow remove` also removes the name from fallbacks.
- VS Code schema: `fallback` in `thread.yaml`, with examples.
- Fallback at run time (step 2): `when` is checked just before the
  workflow starts, by quick **checks** with a time limit
  (`HYDRA_PROBE_TIMEOUT`, 15 s by default) that read no data. True → the
  first backup runs in its place (same stage, same loop pass; re-checked on
  every pass); the CLI shows `↪ Fallback: a → a_backup — <reason>` and the
  backup as `(fallback, in place of a)`. A check that cannot answer follows
  `on_probe_error` (`keep` by default, or `replace`). Inactive workflows are
  not checked. `previous.status` / `previous.rows` describe the workflow (or
  parallel stage) run just before.
- `hdrctl run <project> --use-fallback <workflow>` forces a fallback, to
  rehearse a recovery scenario (refused for a single job, and for a workflow
  without fallback).
- Studio / `POST /api/runs` on a project: a backup appears as
  `<backup> — fallback of <workflow>`, with the decision first in its log;
  checks that kept the workflow and failed checks are logged too.

- Studio (step 3): **Define** edits the fallback of each workflow (life-buoy
  button): backups (a workflow taken from the thread leaves it), `when`
  checked as you type, with a helper that inserts a function and a source,
  destination or secret of the project, "also after a failure" (saved, not
  applied yet) and `on_probe_error`. **Preview** draws backups as dashed
  blocks under their workflow, with the condition on the link. **Check**
  shows warnings. The run page shows the decision of each fallback (switched,
  not needed, check failed) and its reason; project cards show
  `fallback of …`.
- API: `GET /api/projects/{id}/conditions` (functions, sources,
  destinations and secret names for `when`) and
  `POST /api/projects/{id}/conditions/check`; project run steps carry a
  `fallback` object (`workflow`, `action`, `use`, `trigger`, `reason`).
- `thread.yaml`: `delay_before` on a workflow — wait before starting it.
  Sequential stage: counted from the end of the previous workflow; parallel
  stage: from the start of the stage (staggered starts). Same format as
  `delay_after`. Fallback conditions are checked after the wait; in a
  parallel stage, a failure cancels the starts still waiting ("not started").
  Shown by `hdrctl run --dry-run` (`⏱ waits 23s before starting`) and during
  the run; Studio run logs say `waited … before starting`. VS Code schema and
  spec updated.

- **Workflow rollback** (fallback step 5a): `rollback: true` in
  `workflow.yaml` — if the workflow fails, the steps already done are undone,
  the last one first. Jobs automatically: previous file kept next to the new
  one until the end of the run (CSV / Parquet), CSV append back to its size,
  replaced table restored from a `hydra_bak_…` copy, rows added by `append` /
  `upsert` removed and rows changed by `upsert` restored (PostgreSQL,
  MySQL / MariaDB, SQL Server). Actions: `undo:` (an action, or `none`),
  required for `webhook`, `email`, `bash`, `powershell`, `ssh`, `python`.
- Checked before the run (`workflow validate`, `run --dry-run`, Check):
  undoable destination and mode, `load.key` for a database `append`, `undo:`
  on actions that act outside Hydra. With rollback, a database `append` only
  adds new keys, so that they can be removed exactly.
- A destination changed by someone else since the run wrote it is not undone
  (row count / file size and date): the rollback stops. The rest stays in
  `.hydra/undo/<workflow>.json`; the workflow refuses to run until
  `hdrctl workflow undo <workflow>` (new) finishes it. Successful run: the
  backups are removed.
- Studio: **Rollback on/off** in the workflow toolbar, **Undo** section in
  the settings of an action, undone steps in the run page; the Hydra DSL
  panel shows `rollback` and `undo`. VS Code schema, spec (DSL reference:
  "Tout ou rien et annulation"), `DSL_GRAMMAR_TREE.md`.

- **All-or-nothing load per job** (fallback step 4): a job writes its
  destination through one load session (`begin → stage → publish | abort`,
  common to every connector); nothing is visible before the end of the job
  and a failure or Ctrl+C leaves the destination as it was. On by default
  for `replace` (PostgreSQL / SQL Server: TRUNCATE inside one transaction;
  MySQL / MariaDB: DELETE inside one transaction, InnoDB table required;
  CSV / Parquet: temporary file in the same folder, then swapped) and for
  CSV / Parquet `append` (CSV goes back to its original size).
- `load.atomic` in `destinations.yaml`: `true` makes `append` / `upsert`
  into a database one transaction; `false` restores batch-by-batch
  commits. `true` on a connector or mode that cannot do it is an error
  before anything is read. Studio: "All-or-nothing" field on database
  destinations. VS Code schema and spec updated.
- Two jobs of the same run writing the same destination take turns; temporary
  files left by a crashed run are removed on the next run.
- `JobResult.atomic` and `JobResult.partial_write` (a failure left rows
  written), for the fallback after a failure (next step).

### Changed

- Studio keeps the fallbacks of `thread.yaml` when it saves the execution
  order, and no longer offers to add a backup workflow to the thread.
- A job keeps one connection / one open file for all its batches (it opened
  one per batch). Parquet no longer copies the whole file again for every
  batch.
- Without all-or-nothing, a failed job logs that the destination keeps the
  batches written before the failure.

### Fixed

- Studio: opening a workflow whose jobs keep their operations as `steps:` at
  the top of `transformations.yaml` (the form written by `hdrctl init`, the
  CLI or by hand) lost those operations when the job was written back
  (`transformations: steps: []`). Both forms are now read.

## [0.12.3] — 2026-10-23

### Fixed

- Studio: a job rebuilt from its YAML files and saved again no longer loses
  what the canvas does not edit. `batch_size` was reset to 1000, fields such as
  `delimiter` or `encoding` were dropped, and source/destination keys were
  renamed (`src_csv` → `source_csv__csv`), changing `pipeline.from`/`to`.
- Studio keeps a job and its files `jobs/<name>/*.yaml` in sync, both ways:
  **the latest change wins**, made in Studio or outside (editor, Notepad,
  `hdrctl`, git). Before, a file changed outside Studio was not seen while the
  editor was open, and the sync button of the **Hydra DSL** panel only
  regenerated the YAML from the canvas.
  - The sync button (same icon, in the Hydra DSL panel; **Sync with disk** in
    the toolbar) compares the canvas and the files: only the disk changed →
    the canvas is rebuilt from it (node positions kept); only Studio changed →
    the files are written; both changed → the most recent change wins. The
    result is shown next to the button.
  - Automatic sync of the open job every few seconds, set in **Settings**
    (default 5 s, 0 = off), and when a job is opened. In automatic mode a
    Studio change is written only if auto-save is on, unless both sides changed.
  - Formatting and comments are not changes: Studio compares the content.
  - API: `GET /api/jobs/files` also returns `hashes`, `hash` and `mtime`.
  - Every manual sync, and every automatic sync that changes something, also
    posts a notification. The sync button spins while it works.
- Studio: the buttons of the **Hydra DSL** panel header (sync, copy, close)
  show three states: **ready** (dark icon and border; main colour on hover),
  **busy** (main colour, spinning icon, not clickable) and **unavailable**
  (grey, not clickable — e.g. copy with nothing to copy). They were light grey
  icons that looked disabled. The panel header shows the automatic sync
  interval (`auto-sync every 5s` / `auto-sync off`) until the first result.
- `hdrctl serve`: `index.html` is sent with `Cache-Control: no-cache`, so the
  browser loads the new Studio after an update instead of a cached one.
  `/api/health` returns `studio_build` (the Studio script served); a tab still
  running an older build shows **New Studio version — reload**.
- Studio **Templates**: names and descriptions in English (they were in French).
- `hdrctl validate`: the total counts every error shown. It printed
  "0 error(s) detected" when the only errors were in `pipeline.yaml` (broken
  `pipeline.from` / `to`), in strict checks or a missing file.
- `pipeline.yaml` is checked the way the engine reads it: the old nested
  `job: pipeline:` format, a missing or empty `from` / `to`, and unknown keys
  (`form:`) are errors; a `${param}` value is reported as resolved at run time.
  Same check in `hdrctl run <job> --dry-run`.
- `hdrctl run <project>` (and `--dry-run`, Studio's **Check** / **Run
  project**) now checks `pipeline.yaml` of every job used by an active
  workflow before starting: a broken `pipeline.from` no longer passes as
  "the project is valid".

### Changed

- Connector error and log messages are in English (CSV, JSON, Parquet,
  PostgreSQL, MySQL/MariaDB, SQL Server), like the rest of the CLI. Example:
  `CSVConnector [src]: source file not found.` instead of
  `Fichier source introuvable.`

## [0.12.2] — 2026-10-22

### Added

- Studio: the workflow cards of a project page can be rearranged by drag and
  drop: grab a card by its title and drop it on another card (dashed outline)
  to swap them. Display only: the order is kept in `.hydra/card-order.json`
  and does not change `thread.yaml` or `hdrctl run`.
  API: `PUT /api/projects/{id}/card-order`.

## [0.12.1] — 2026-10-22

### Added

- Project secrets in `.hydra/secrets`: one `name=value` per line, read by
  `${SECRET:name}` in jobs and in workflow action parameters. `init` (and a
  project created in Studio) writes a commented template and a `.gitignore`
  that excludes `.hydra/secrets` and `.env`. An environment variable wins over
  the file (`${SECRET:db.password}` first reads `DB_PASSWORD`). To keep the
  file elsewhere: `HYDRA_SECRETS_FILE=<path>` or `--secrets-file <path>` on
  `hdrctl run` and `hdrctl workflow run`. Parse errors give the line, never
  the value.
- Studio: a **Secrets** tab in the bottom panel of the workflow editor lists
  the project's secrets (names only: values never leave the server), adds,
  replaces and deletes them, copies the `${SECRET:name}` reference, and shows
  when an environment variable overrides one. In a node's password field, a
  plain-text value now offers "Move to Secrets": the value goes to
  `.hydra/secrets` and the field keeps `${SECRET:<node>.<field>}`. The hints no
  longer point to "Environments" (`.env.<name>` files the engine never reads).
  API: `GET|PUT /api/secrets`, `DELETE /api/secrets/{name}`.
- Studio: an **Execution order** panel on the project page edits
  `workflows/thread.yaml` — stages, `sequential`/`parallel`, `delay_after`,
  active or skipped workflows, order (up/down, across stages), workflows not
  in the thread — with **Check** (same checks as `hdrctl run --dry-run`) and
  **Run project** (every active workflow in that order, like
  `hdrctl run <project>`; one run, one line per workflow, followed live).
  API: `GET|PUT /api/projects/{id}/thread`, `POST /api/projects/{id}/check`;
  `POST /api/runs` with the project folder as `workflow_path` runs the project.
- Loops in `workflows/thread.yaml` (optional): `loops: [{from, to, times, delay}]`
  replays the part of the thread from `to` to `from`, `times` passes in total,
  with an optional pause before each repeat. A loop can link any two workflows
  of the thread (`to` before `from`, or the same workflow); loops must not
  overlap. `hdrctl run` shows `(pass i/N)` and `↻ Loop …`, `--dry-run` lists the
  loops; `workflow remove` drops the loops that cite the removed workflow. The
  VS Code schema validates the `loops` block.
- Studio: the **Execution order** panel has two tabs. **Define** edits the
  stages and the loops (from / to / passes / pause, checked as you type).
  **Preview** draws the thread: blocks left to right by stage, stacked when
  parallel, a diamond for each delay, inactive workflows dashed, loops as
  dashed return arrows labelled ×N. Clicking a block opens the workflow.

### Changed

- `init` no longer creates an empty `.hydra/workflows/`: Studio creates it
  when it saves a workflow canvas.
- The demo project (Studio's "Install demo") has the same layout as
  `hdrctl init`: `outputs/` (was `output/`), `environments/`, `scripts/`,
  `parameters.yaml`, `workflows/thread.yaml`, `.hydra/secrets` and
  `.gitignore`; `hdrctl run .` runs it whole. Studio's file path examples for
  CSV/JSON/Parquet destinations point to the project's `outputs/`
  (`../../outputs/file.csv` from a job).
- The generated `.gitignore` also excludes `.env.*` (keeping `.env.example`),
  so the `.env.<name>` files written by Studio's environments API stay out of
  git.

### Fixed

- Studio no longer overwrites changes made outside it. It draws a workflow
  from its saved canvas and, on save, rewrites the workflow file and the files
  of its jobs: a job attached with `hdrctl job attach`, or a file edited by
  hand, was not shown and was then erased by the next save (or auto-save).
  Studio now records a fingerprint of every file it writes. When a workflow is
  opened and one of its files has changed since, the canvas is rebuilt from
  the files and a notice lists them. When a file changes while the workflow is
  open, the save is refused (HTTP 409, nothing written), auto-save pauses, and
  Studio offers "Reload from disk" or "Overwrite with Studio's version".
  API: `GET /api/workflows/{id}` returns `external_changes` and `disk_state`;
  `PUT` accepts `base_disk` and `force`.


## [0.12.0] — 2026-10-22

CLI reform: a project is now the unit you create and run. Delivered step by step
on the `cli-reform` branch.

### Changed

- `hdrctl init <path>` (or `hdrctl init .`) creates the full project layout:
  `.hydra/`, `Data/`, `environments/`, `jobs/job1/`, `outputs/`,
  `parameters.yaml`, `README.md`, `scripts/` and `workflows/` holding
  `workflow1.yaml` and `thread.yaml`. The results folder is now `outputs/`
  (was `output/`), also for projects created from Studio.
- The "Next steps" printed by `init` are numbered without gaps (they read
  1, 3, 4 for templates without `.env.example`).
- The README generated in `jobs/job1/` lists `hdrctl validate`, `hdrctl test`
  and `hdrctl run` (it suggested the old `hydra test`). The hints printed by
  `run --dry-run` and `list` no longer suggest the old `hydra` command.
- `init` now suggests `hdrctl run <project> --dry-run` and `hdrctl run <project>`.

### Fixed

- A workflow stored in `workflows/` did not see the project's `parameters.yaml`
  and `environments/`: its actions looked for them in `workflows/`, so
  `{{ param:X }}` stayed unresolved. The runner now finds the project root (the
  folder holding `.hydra/`). A `python` action's `file_path` is also looked up
  from the project root when it is not found next to the workflow, so
  `scripts/x.py` works from any workflow.
- When a workflow failed, the engine's own log line ("Workflow 'x' failed at
  step 'y'…") was printed a second time on stderr, under the CLI's summary. The
  CLI now owns that output.
- The output of a `python`, `bash`, `powershell` or `ssh` action that fails is
  now shown under the step, as it already was on success (it was dropped). The
  error reads `Python script exited with code 3: <last stderr line>` instead of
  repeating the whole stderr.
- Workflow engine messages are in English, like the rest of the CLI: action
  errors (`set_param`, `assign_param`, `webhook`, `delay`, `python`, `ssh`,
  `email`…), unconfigured job, cycles, unknown dependency, duplicate step names,
  `when` guards and retry logs. They were in French.
- `hdrctl list` printed "OK" twice in its summary ("3 job(s)  3 OK OK").
- `hdrctl --help` showed "Examples: …" as the summary of `clear`, `list`,
  `test` and `validate`; each command now has a one-line description.
- Help texts still showed the old `hydra` command (`hydra test`,
  `hydra workflow run`…); they now show `hdrctl`.

### Removed

- `hdrctl workflow init` and its templates, and `POST /api/jobs/workflow/init`.
  They wrote a `workflow.yaml` plus `jobs/job_a`… in the old layout; use
  `hdrctl workflow add`.
- The French, German, Portuguese, Japanese and Chinese CLI translations, which
  the CLI never loaded (`--lang` only accepts `en` and `es`) and which were
  incomplete. Moved to `tools/cli-locales-archive/`. The Spanish translation is now
  complete, and a test keeps every supported language in step with English.

### Added

- `workflows/thread.yaml`: the order in which the project's workflows run.
  Stages run one after the other; each stage is `sequential` or `parallel`,
  takes an optional `delay_after` (`30s`, `5m`, `1h`), and each workflow can be
  set `active: false` to skip it while debugging. Model and validation in
  `hydra_etl/workflow/thread.py`.
- `hdrctl run <project>` (or `hdrctl run .`) runs a whole project: every
  workflow, in the order of `workflows/thread.yaml`. Before starting anything it
  checks the thread, every active workflow manifest and the job folders they
  reference, and lists every problem found. A failed workflow stops the project
  (exit code 1); workflows not reached are reported as not run. Without
  `thread.yaml`, every `workflows/*.yaml` runs one after the other in
  alphabetical order. `--dry-run` prints the execution plan; `--env`, `-P` and
  the `--on-success/--on-failure/--on-finish` hooks apply to the whole project;
  `-s/-d/-p/-t` and `--profile` are refused, as they only make sense for one
  job. `hdrctl run <job folder>` is unchanged. Engine in
  `hydra_etl/workflow/project.py`.
- `hdrctl workflow add [name]` creates `workflows/<name>.yaml` with no step and
  adds it at the end of `thread.yaml` (last stage if sequential, otherwise a new
  sequential stage); without a name it is `workflow-<8 hex>`. `hdrctl workflow
  remove <name>` deletes the file and its thread entry (and Studio's metadata
  for it), keeps the jobs, and asks for confirmation unless `-y`. Both work on
  the project containing the current folder or on `--project <path>`, and stop
  with an error outside a project.
- `hdrctl workflow list` lists a project's workflows in thread order with
  stage, mode, active/inactive and step count, plus workflows missing from
  `thread.yaml` and thread entries without a file. Outside a project it still
  searches for `workflow.yaml` files.
- `hdrctl job add <job> [workflow] [-p N] [--template T]` creates
  `jobs/<job>/` from the `init` templates and, given a workflow, attaches it.
  `hdrctl job attach <job> <workflow> [-p N]` attaches an existing job.
  Steps form a chain: at the end, the job runs after the last step; at
  position N it runs after step N-1 and the former step N runs after it.
  `hdrctl job detach <job> [workflow]` removes it from one workflow or from all;
  the steps that ran after it inherit its dependencies, and the job folder is
  kept. Messages say when a job is free or not in that workflow. Every change
  is validated before the workflow file is written; nothing is created when a
  check fails (unknown workflow, position out of range, existing job).
  API: `POST /api/jobs/job/add`, `/job/attach`, `/job/detach`.
- `hdrctl job list` lists a project's jobs: free, or the workflows that use
  them, or the required files they lack, plus job folders a workflow refers
  to that do not exist. `hdrctl list` on a project folder shows the same list
  (it answered "No jobs found"; only `hdrctl list <project>/jobs` worked).
- `hdrctl workflow run` and `workflow validate` accept a workflow name
  (`hdrctl workflow run daily_sales`) as well as a file path, and `--project`.
- API: `POST /api/jobs/workflow/add` and `POST /api/jobs/workflow/remove`
  (Postman collection updated).
- Studio keeps `workflows/thread.yaml` in step: creating a workflow adds it at
  the end, deleting one removes it, and opening a project no longer registers
  `thread.yaml` itself as a workflow.
- `parameters.yaml` at the project root, empty, with a commented example.


## [0.11.4] — 2026-10-17

### Fixed

- `mode: upsert` now works on PostgreSQL. Until now every PostgreSQL destination
  using upsert failed with `KeyError: 0`, whatever the target table, even when a
  PRIMARY KEY existed on exactly the columns listed in `key` — so the mode was
  effectively unusable. Two defects in the pre-flight constraint check were at
  fault: `array_agg` over `information_schema.key_column_usage.column_name`
  (type `sql_identifier`) is returned by psycopg2 as the raw text `{col}` rather
  than a list, so the comparison matched characters instead of column names; and
  the `RealDictCursor` row was unpacked as a tuple, which bound the dict keys and
  made the error branch raise `KeyError: 0`, hiding the real diagnostic. The
  aggregate is now cast to `text` and the row read by key. `hdrctl validate` was
  unaffected and still reported a valid DSL, so the failure only showed at run
  time.

### Changed

- The "driver missing" errors now name the extra to install rather than the
  underlying package: `pip install "hydra-etl[postgres]"` and
  `pip install "hydra-etl[mysql]"`, matching what the SQL Server connector
  already did. Same for the MongoDB connector, which pointed at `pymongo`.

- `hdrctl init` now scaffolds a **project**, not a bare job folder: `jobs/job1`,
  `workflows/workflow1.yaml`, `Data/`, `output/`, and a `.hydra/project.json`
  that marks the directory as a Hydra project. The six job templates are
  unchanged and still selected with `--template`. Commands that used to read
  `hdrctl run my_job` now take the path to a job inside the project, for example
  `hdrctl run my_project/jobs/job1`, or the workflow with
  `hdrctl workflow run my_project/workflows/workflow1.yaml`.
- The Studio file picker tells a Hydra project from an ordinary directory: the
  listing endpoint reports `is_project` for each entry, based on the presence of
  `.hydra/project.json`, so an existing project can be opened directly instead of
  being rebuilt by hand.

### Added

- A demo project shipped inside the package (`hydra_etl/samples/hydra-demo`) and
  an endpoint that installs it, so a fresh install has something to run without
  writing any YAML first.
- `tests/test_postgresql_upsert_key_validation.py` — unit coverage for the upsert
  key validation, with no database or driver required. The existing end-to-end
  PostgreSQL tests do cover this path but are skipped at module level because
  they need live containers, which is why the regression shipped.

## [0.11.3] — 2026-09-27

### Fixed

- `${SECRET:NAME}` now resolves. Until now the CLI built its resolver with an
  empty secret store, so every `${SECRET:...}` placeholder failed with
  `Secret manquant`, even though the README and the DSL reference documented it
  as a supported way to keep credentials out of a manifest. A secret is now
  looked up in the injected store first — leaving the door open for Vault, AWS
  or Azure backends — and otherwise in the process environment, under the name
  upper-cased with dots and dashes turned into underscores, so
  `${SECRET:db.password}` reads `DB_PASSWORD` and the documented
  `${SECRET:DB_PASSWORD}` works as written. When a secret really is missing the
  error now names the environment variable to define.

## [0.11.2] — 2026-09-26

### Fixed

- A workflow step with an unknown action is now rejected instead of being
  silently skipped. Before, a typo such as `powersheII` made the step do nothing
  while the run still reported success. `hdrctl workflow validate` now fails,
  names the valid actions and suggests the closest one
  (`did you mean 'powershell'?`), and `hdrctl workflow run` refuses to start.
  As a second safeguard, the runner marks any unknown action it still meets as
  failed rather than successful.

- `hdrctl workflow run` no longer ends in a Python traceback on an invalid
  manifest, lists the steps that never ran after a failure as skipped, and
  prints validation errors one per line without Pydantic's internal details.
  Shell step failures now read `Command exited with code N`.

- A workflow file with a misspelled or misplaced key is now rejected instead of
  having that key ignored. Before, `depend_on: [fetch]` validated fine and the
  step ran without its dependency; `mesage:` under a `log` step was dropped.
  Validation now refuses unknown keys at every level (top level, `workflow`,
  steps, `trigger`, `retry`) and unknown action parameters, suggests the
  closest valid name, and checks each action's required parameters (`command`
  for `bash`, `url` for `webhook`, `script` or `file_path` for `python`…).
  A workflow that relied on an ignored key will now fail validation: the error
  names the key to remove or fix.
- The `webhook` action now sends the `headers` parameter that Studio offers,
  and sends a text `body` as written. Before, headers were ignored and a text
  body was re-encoded as a JSON string.

## [0.11.1] — 2026-09-23

### Added

- Hydra Studio offers SQL Server as a source and as a destination. The engine
  had the connector since 0.11.0, but the visual editor gave no way to pick it,
  so a SQL Server pipeline could not be built there at all.

  The form carries `host`, `instance`, `port`, `database`, `schema`, `user` and
  `password`, then table or query as a source, table and mode as a destination.

  The port is deliberately not defaulted to 1433 the way MySQL and PostgreSQL
  default to 3306 and 5432. An explicit port short-circuits the SQL Browser
  lookup, so writing one by default would make named instances unreachable from
  Studio — that is, SQL Express, whose instance is named by construction. The
  field label says so: leave it empty for a named instance.

  Proven end to end: a SQL Server source resolved through SQL Browser, no port
  given, loading into a CSV destination.

## [0.11.0] — 2026-09-22

### Added

- Microsoft SQL Server connector, aliases `sqlserver` and `mssql`. Extract with
  a table or a query, load in `append`, `replace` or `upsert` mode, with
  auto-creation of the target table. Install it with
  `pip install "hydra-etl[mssql]"`.

  The driver is `pymssql`, which ships FreeTDS inside its wheels, rather than
  `pyodbc`, which needs the `msodbcsql` system driver installed separately.
  One command, nothing to deploy.

  Upsert runs `UPDATE` then `INSERT ... WHERE NOT EXISTS` inside a
  transaction. `MERGE` is deliberately not used: its concurrency problems are
  documented and many SQL Server teams ban it outright.

  Auto-created tables use `NVARCHAR` rather than `VARCHAR` and `DATETIME2`
  rather than `DATETIME`, so accented text and timestamps behave identically
  whatever the server's collation.

  A named instance is resolved by Hydra itself. `pymssql` embeds FreeTDS,
  which unlike the Microsoft drivers never queries the SQL Browser service, so
  `MACHINE\\SQLEXPRESS` would reach port 1433 and fail — the default setup of
  SQL Express, that is, of the audience this connector targets. Hydra sends
  the SSRP datagram itself over UDP 1434 and connects on the port it gets
  back. An explicit port short-circuits the lookup; a silent SQL Browser falls
  back to an error message that says which of the two to fix.

  Tested end to end against two live servers: SQL Server 2022 on Windows with
  a named instance on a static TCP port, and
  `mcr.microsoft.com/mssql/server:2022-latest` in Docker on Linux. Same major
  version on both, so the operating system was the only variable. 74 unit
  tests need no server; 11 end-to-end tests are skipped unless
  `HYDRA_E2E_MSSQL` is set.

### Known limitation

- Azure AD authentication and Always Encrypted are out of reach with
  `pymssql`. They need `pyodbc` and the `msodbcsql` system driver, which will
  be added as an option the day a user asks for it.

## [0.10.3] — 2026-09-21

### Changed

- The MCP server now speaks English. The instructions of the server and the
  descriptions and annotation titles of its 17 tools were in French; they are
  what an AI client reads to decide which tool to call, and what MCP
  registries publish.
- `serverInfo` reported an empty version. It now carries the package version,
  and adds a title and the website URL when the installed MCP SDK accepts
  them. The server name is `hydra-etl`, matching the package.
- `hydra-mcp --help` is in English.

## [0.10.2] — 2026-09-20

### Fixed

- `hdrctl validate --strict` now recognises the steps of a `transformations.yaml`
  written as `transformations: steps:`; it previously reported "none" on the
  manifests shipped in `examples/`.
- `hdrctl validate --strict` checks the syntax of `filter` and `calculate`
  expressions with pandas' own parser, without evaluating them. An invalid
  expression now fails validation (exit code 1) instead of failing at run time.

### Added

- `hdrctl workflow run` prints what a `python`, `bash` or `powershell` action
  wrote on stdout/stderr, under the corresponding step (capped at 20 lines).
  `StepResult` carries it in a new `output` field.

## [0.10.1] — 2026-09-17

### Fixed

- `hdrctl run` no longer ends with "Critical error: TypeError" on Python 3.9
  (click 8.1 passed `None` as verbosity when no `-v` flag was given).
- The `mcp` extra now installs only on Python 3.10+, so
  `pip install "hydra-etl[all]"` works again on Python 3.9.

### Changed

- `httpx` and `requests-mock` are declared in the `dev` extra.
- CI now runs on Linux, Windows and macOS, Python 3.9 to 3.13.



## [0.10.1] — 2026-09-15

### Added

- **MCP server** (`hydra-mcp`) — connect Hydra to any AI assistant: Claude
  Desktop, Cursor, VS Code, or any MCP client. Install with
  `pip install "hydra-etl[mcp]"`. Seventeen tools covering DSL discovery,
  reading and writing jobs and workflows, validation, execution, data preview
  and consistency checking. See [docs/MCP.md](docs/MCP.md).
  - **Nothing invalid is ever written**: `hydra_write_job` and
    `hydra_write_workflow` validate in a temporary folder and write only on
    success. A rejected job leaves no trace, and the assistant receives the
    exact error.
  - **Nothing outside the workspace is touched**: absolute paths, `..`
    segments and symlinks leading out are refused, identically on Windows,
    macOS and Linux.
  - **Nothing runs unasked**: execution tools are separate calls and carry the
    MCP `destructiveHint` annotation, so clients can ask for confirmation.
  - Both transports: `stdio` by default, `--transport streamable-http` for
    clients that cannot start a local process.
- `hydra_check_job` — twelve deterministic rules comparing the user's request
  to the manifests produced. The validator says whether the YAML is correct;
  this says whether the job does what was asked.
- `hydra_preview_data` — columns and first rows of a CSV, JSON or Parquet file.
- `tools/spec_export.py` — generates the DSL specification from the engine's
  own models: JSON schemas for the five manifests, the eighteen operations,
  the nine connectors and the workflow actions, plus a readable reference.
  `--check` fails in CI when the specification has drifted from the code.
- `hydra_etl/internal/parser/pipeline.py` — a Pydantic model for
  `pipeline.yaml`, which had none.

### Fixed

- `hdrctl` no longer crashes with `UnicodeEncodeError` when its output is not
  UTF-8 — a redirected output, a pipe, a CI job or a subprocess on Windows.
  The command failed while the work itself had succeeded.

### Known issues

- `hdrctl validate` reports `0 error(s) detected` after signalling an error:
  the counter does not account for `pipeline.from` / `pipeline.to` resolution
  failures. Cosmetic, and worked around in the MCP server.
- The HTTP transport has no authentication. It is meant for your own machine
  or a tunnel you control — never a public address.
