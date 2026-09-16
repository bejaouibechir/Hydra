# HYDRA ETL

 **[hydraetl.com](https://hydraetl.com)**

[![PyPI](https://img.shields.io/pypi/v/hydra-etl.svg)](https://pypi.org/project/hydra-etl/) [![Python](https://img.shields.io/pypi/pyversions/hydra-etl.svg)](https://pypi.org/project/hydra-etl/) [![License AGPL v3](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE) [![Status](https://img.shields.io/badge/status-beta-orange.svg)](#project-status)

**Your data pipelines are described, not programmed.**

Hydra is a declarative ETL engine: you write what the pipeline *is* in YAML, and
Hydra decides how to run it. The same manifests run from the terminal, from a
REST API, or from a browser canvas — one engine underneath, and one `pip install` to get all three.

```bash
pip install "hydra-etl[server]"
hdrctl serve
```

Guides, DSL reference and a browser playground: **[hydraetl.com](https://hydraetl.com)**

## HYDRA Studio  "Your Kitchen"

Open **[http://localhost:5678](http://localhost:5678)** — that is Hydra Studio. No Node, no build step,
no database, no broker, nothing else to start.

<img title="" src="assets/hydrastudio.png" alt="" width="657">

---

## What you get

|               |                                                                          |
| ------------- | ------------------------------------------------------------------------ |
| **Engine**    | Declarative jobs: one source, N transformations, one destination         |
| **CLI**       | `hdrctl` — scaffold, validate, run, inspect. English and Spanish         |
| **API**       | FastAPI, with interactive docs at `/docs`                                |
| **Studio**    | Visual editor for jobs and workflows, served by the same process         |
| **Workflows** | Multi-job DAG with dependencies, actions, retries and runtime parameters |

**Connectors**

Out of the box, Hydra connects to the following sources and destinations

| **CSV**             | <img title="" src="file:///C:/Users/DELL/Desktop/Hydra/assets/connectors/csv.png" alt="" width="50" data-align="inline"> |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **JSON**            | <img title="" src="assets/connectors/json.png" alt="" width="50">                    |
| **Parquet**         | <img title="" src="assets/connectors/parquet.png" alt="" width="50">                 |
| **MySQL / MariaDB** | <img title="" src="assets/connectors/mysql.png" alt="" width="53">                   |
| **PostgreSQL**      | <img title="" src="assets/connectors/postgresql.png" alt="" width="53">              |
| **MongoDB**         | <img title="" src="assets/connectors/mongo.png" alt="" width="53">                   |
| **Web API**         | <img title="" src="assets/connectors/api.png" alt="" width="53">                     |

Transformation engines: **Pandas** and **DuckDB**. 

### MCP server: talk to Hydra in plain language.

Your assistant writes the pipelines; Hydra validates them.

![MCP server: talk to Hydra in plain language](assets/1/mcp-server-natural-language-pipelines.svg)

### The combination of declarative, visual, and nothing to deploy.

Taken separately, none of the three is unique. Together, they are: Airbyte's interface requires a deployment, Talend is dead, Apache Hop and Pentaho require a JVM, and NiFi is heavy. You are alone on this combination.

![The combination of declarative, visual, and nothing to deploy](assets/2/triplet-declaratif-visuel-zero-deploiement%20.svg)

### Validation before execution is your only truly isolated advantage.

dbt catches reference errors at compile time, but no file-and-database pipeline tool can answer deterministically, “Will this run?” before touching any data. It can be demonstrated with a single command, and nobody can copy it without rebuilding their architecture.

![Validation before execution is your only truly isolated advantage](assets/3/validation-avant-execution%20.svg)

### A CLI built for CI/CD — hdrctl creates, validates, tests, and runs from a terminal or an integration pipeline.

Manifests are versioned and reviewed like code.

![A CLI built for CI/CD — hdrctl creates, validates, tests, and runs from a terminal or an integration pipeline](assets/4/hdrctl-cli-built-for-ci-cd.svg)

### Hydra includes its own scheduler.

DAG workflows provide dependencies, automatic parallel execution of independent branches, delayed retries, cron triggers, conditional guards, and eleven actions including webhook, email, Bash, PowerShell, SSH, and Python.

Chain multiple jobs with dependencies, parallel execution of independent branches, retries, cron triggers, and conditional guards.

![Hydra includes its own scheduler](assets/5/dag-workflows-built-in-scheduler.svg)

### One job, multiple environments.

{{ param: }}, {{ env: }}, ${SECRET:}: the manifest does not change between development, staging, and production — only the parameters change. It is the natural extension of the DevOps argument.

![One job, multiple environments](assets/6/one-job-multiple-environments.svg)

### Hydra exposes a REST API.

FastAPI provides interactive documentation at /docs. Hydra can be controlled from your CI pipeline, your application, or any tool — it is not merely used, it integrates.

Modular installation.

Install only what you use: the engine alone, with the server, with PostgreSQL, or everything.

![Hydra exposes a REST API](assets/7/7.rest-api-modular-installation.svg)

### Two execution engines, selected per operation.

pandas or DuckDB, case by case. The power of analytical SQL without a data warehouse.

In addition: a Rust engine for large files.

Optional native acceleration: CSV reading four times faster on one million rows, byte-for-byte identical results, and automatic fallback to Python whenever the guarantee cannot be maintained.

But here you have something almost nobody else possesses: parity proof. 26,000 CSV files tested with zero differences; one million floats compared against CPython repr(). Anyone can say, “We use Rust.” Almost nobody proves that the result is identical.

![Two execution engines, selected per operation](assets/8/5.multiple-engines-proven-parity.svg)

### A visual Studio is included.

Build the pipeline with the mouse and get YAML out.

![A visual Studio is included](assets/9/hydra-studio-to-yaml.svg)

### VS Code extension — manifest completion and validation directly inside the editor, without installing Hydra.

Discover the DSL before even trying the product.

![VS Code extension — manifest completion and validation directly inside the editor, without installing Hydra](assets/10/vscode-extension-discover-dsl.svg)

---

## Who it is for

- **Data engineers and analysts** who need repeatable file-and-database
  pipelines without standing up infrastructure for them.
- **Teams where the pipeline must stay readable** by someone who does not write
  Python — a YAML manifest reviewed in a pull request, not a script.
- **Developers embedding ETL in a product**, who want a CLI and a REST API over
  the same engine.

---

## A job in four files

A job is a folder. Four manifests describe it, and each one answers a single
question.

**`sources.yaml`** — where the data comes from

```yaml
version: "1.0"
sources:
  src_input:
    type: csv
    extract:
      table: ./input.csv
```

**`transformations.yaml`** — how it is reshaped

```yaml
version: "1.0"
steps:
  - cast:
      mapping:
        amount: float
  - filter:
      expr: "amount > 0"
  - aggregate:
      by: [name]
      agg:
        total: { func: sum, col: amount }
```

A CSV carries no types, so `cast` comes before any numeric comparison.

**`destinations.yaml`** — where it goes

```yaml
version: "1.0"
destinations:
  dest_output:
    type: csv
    load:
      table: ./output.csv
      mode: replace          # append | replace | upsert
```

**`pipeline.yaml`** — which source feeds which destination

```yaml
version: "1.0"
pipeline:
  from: src_input
  to: dest_output
```

Then:

```bash
hdrctl init my_job          # scaffold one of six templates
hdrctl validate my_job      # strict validation, no data touched
hdrctl run my_job           # execute
```

---

## A workflow orders several jobs

```yaml
version: "1.0"
workflow:
  name: daily_etl
  trigger:
    type: schedule
    cron: "0 8 * * *"
  steps:
    - name: extract
      type: job
      job: ./jobs/extract
      depends_on: []

    - name: transform
      type: job
      job: ./jobs/transform
      depends_on: ["extract"]     # always a list — supports fan-in

    - name: notify
      type: action
      action: webhook
      params: { url: "{{ env:WEBHOOK_URL }}" }
      depends_on: ["transform"]
      on_failure: skip
```

```bash
hdrctl workflow validate ./workflow.yaml
hdrctl workflow run      ./workflow.yaml
```

An edge is a **dependency**, not a pipe: it decides *when* a job runs, never
what data reaches it. Steps that share no dependency run in parallel.

---

## Parameters

Values can be declared once and reused, or created while the workflow runs.

```yaml
- filter:
    expr: "region == '{{ param:region }}'"
```

`{{ param:NAME }}` reads a parameter, `{{ env:NAME }}` an environment variable.
The `set_param` and `assign_param` actions create and change parameters
mid-run, so two jobs can share a placeholder and produce different results.

---

## Install what you need

The base install is the engine and the CLI. Everything else is opt-in.

```bash
pip install hydra-etl                  # engine + CLI
pip install "hydra-etl[server]"        # + API + Studio
pip install "hydra-etl[postgres]"      # + PostgreSQL driver
pip install "hydra-etl[all]"           # everything
```

Available extras: `server`, `native`, `duckdb`, `parquet`, `mysql`, `postgres`,
`mongodb`, `http`, `all`.

Requires **Python 3.9+**. Runs on Linux, macOS and Windows.

---

## Native acceleration (optional)

Parts of the engine have a Rust implementation. It is optional and off by
default: without it, Hydra behaves exactly as it always has.

```bash
pip install "hydra-etl[native]"
```

Turn it on per operation, either with an environment variable:

```bash
HYDRA_BACKEND=rust hdrctl run ./jobs/sales
```

or with a `hydra.backends.yaml` file next to the job you run:

```yaml
default: python
overrides:
  csv.read: rust      # currently the only accelerated operation
```

---

## Your AI assistant, connected

Hydra ships an MCP server. Point Claude Desktop, Cursor, VS Code — or any MCP
client — at it, and ask for a pipeline in plain language.

```bash
pip install "hydra-etl[mcp]"
hydra-mcp
```

Your assistant writes the manifests; **Hydra validates them before anything is
written**, and nothing runs until you ask. 

See [docs/MCP.md](docs/MCP.md) for the client configuration snippets.

---

## Serving

```bash
hdrctl serve                 # Studio and API on port 5678
hdrctl serve --open          # and open the browser
hdrctl serve --no-studio     # API only, for a headless server
hdrctl serve --port 8080
```

The server writes projects into the directory you launch it from.

---

## VS Code extension

There is also a VS Code extension providing completion and validation for the
manifests, without installing Hydra.

![](assets\hydravs.png)

---

## Project status

**Beta.** The connectors and steps documented below are implemented and
covered by tests. 

The shape of the YAML DSL is settled; any breaking change to
it will be announced in the release notes before 1.0. Use it on real work,
pin your version.

---

## License

Hydra ETL is released under the **GNU Affero General Public License v3 or
later** — see [LICENSE](LICENSE).

In short: you may use, modify and redistribute it freely, including
commercially. If you modify Hydra and let others use it — even only over a
network — you must make your modified source available under the same terms.

For a licence without that obligation, contact the author.
