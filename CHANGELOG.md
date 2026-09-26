# Changelog

All notable changes to Hydra ETL are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).



## [Unreleased]

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
