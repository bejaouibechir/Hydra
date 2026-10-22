# Changelog

All notable changes to Hydra ETL are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).


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

### Changed

- `init` no longer creates an empty `.hydra/workflows/`: Studio creates it
  when it saves a workflow canvas.

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
