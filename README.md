# Hydra ETL

**A declarative ETL engine with a CLI, a REST API and a visual editor — in one `pip install`.**

You describe a pipeline in YAML. Hydra runs it, from the terminal or from a
browser canvas, with the same engine underneath.

```bash
pip install "hydra-etl[server]"
hdrctl serve
```

Open **http://localhost:5678** — that is Hydra Studio. No Node, no build step,
nothing else to start.

---

## What you get

| | |
|---|---|
| **Engine** | Declarative jobs: one source, N transformations, one destination |
| **CLI** | `hdrctl` — scaffold, validate, run, inspect. English and Spanish |
| **API** | FastAPI, with interactive docs at `/docs` |
| **Studio** | Visual editor for jobs and workflows, served by the same process |
| **Workflows** | Multi-job DAG with dependencies, actions, retries and runtime parameters |

Connectors: **CSV, JSON, Parquet, MySQL/MariaDB, PostgreSQL, MongoDB, Web API**.
Transformation engines: **Pandas** and **DuckDB**.

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

What it changes, on a 1-million-row job: reading a CSV is about four times
faster, which makes a filter-and-sort job about 1.5x faster end to end and an
aggregation about 2x. Output files are byte-for-byte identical.

The Python implementation stays in charge whenever the native one cannot
guarantee the same result — a file that is not UTF-8, a byte order mark, a
quoted field left open at the end of the file — and says so with a warning.
Small files (under 64 KB) always use Python, where the native path would be
slower. If the package is not installed, Hydra warns once and runs in Python.

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

## Documentation

Guides, DSL reference and a browser playground: **[hydraetl.com](https://hydraetl.com)**

There is also a VS Code extension providing completion and validation for the
manifests, without installing Hydra.

---

## License

Hydra ETL is released under the **GNU Affero General Public License v3 or
later** — see [LICENSE](LICENSE).

In short: you may use, modify and redistribute it freely, including
commercially. If you modify Hydra and let others use it — even only over a
network — you must make your modified source available under the same terms.

For a licence without that obligation, contact the author.
