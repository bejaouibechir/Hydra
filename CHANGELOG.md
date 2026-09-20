# Changelog

All notable changes to Hydra ETL are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).



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
