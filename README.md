# Hydra ETL Platform

**Version** 1.2.0 · Declarative, extensible data platform. The ETL Engine is free and open-source; advanced engines are planned on top of it.

Hydra is a three-headed data platform — each head is a distinct engine:

| Engine | Role | Status |
| ------ | ---- | ------ |
| **ETL Engine** | Declarative ETL framework (jobs, workflows, Studio) | Active — v1 |
| **Feature Detection Engine** | Automated feature engineering for ML / prediction | Planned |
| **Execution Intelligence Engine** | HydraLM + MCP connectors + pipeline intelligence | Planned |

Website (planned): [hydraetl.com](https://hydraetl.com)

---

## What ships today — ETL Engine

- **CLI** (`hydra` / `hdrctl`) built on Click, bilingual (English + Spanish)
- **Job runner** — the atomic unit: `1 source -> N transformations -> 1 destination`
- **Workflow runner** — multi-job orchestration as a DAG (`depends_on`, implicit parallelism, actions)
- **Connectors** — CSV, JSON, Parquet, MySQL/MariaDB, PostgreSQL, MongoDB, Web API
- **Transformation engines** — Pandas and DuckDB
- **Extensible plugin system** — auth, cache, retry, pagination, metrics, operations, and more
- **REST API** — FastAPI backend to drive and monitor jobs/workflows (`hydra serve`)
- **Studio** — visual workflow editor (React Flow), n8n-inspired

---

## Installation

Requires Python 3.9+ (cross-platform: Linux / macOS / Windows).

```bash
git clone <repo-url> hydra
cd hydra
pip install -e .          # editable install — no reinstall after edits
```

Optional connector dependencies (install as needed): `mysql-connector-python`,
`psycopg2-binary`, `pymongo`, `pyarrow`. See `requirements.txt`.

---

## Quick start

### 1. Create and run a job

```bash
hydra init my_job                # scaffold a job from a template
hydra validate my_job            # strict DSL validation
hydra run my_job --dry-run       # validate without writing data
hydra run my_job -vv             # execute with metrics
```

A job is a folder holding `sources.yaml`, `destinations.yaml`, `pipeline.yaml`,
and an optional `transformations.yaml` (or a single `pipeline.yaml`).

**sources.yaml**

```yaml
sources:
  src_input:
    type: csv
    extract:
      table: data/input.csv
```

**transformations.yaml**

```yaml
steps:
  - select:
      columns: [id, name, amount]
  - filter:
      expr: "amount > 0"
  - aggregate:
      group_by: [name]
      metrics:
        total: { op: sum, column: amount }
```

**destinations.yaml**

```yaml
destinations:
  dest_output:
    type: csv
    load:
      table: output.csv
      mode: replace          # append | replace | upsert
```

**pipeline.yaml**

```yaml
pipeline:
  from: src_input
  to: dest_output
```

### 2. Orchestrate a workflow

```bash
hydra workflow init my_flow --template parallel
hydra workflow validate my_flow/workflow.yaml
hydra workflow run my_flow/workflow.yaml
```

```yaml
version: "1.0"
workflow:
  name: "daily_etl"
  trigger:
    type: schedule
    cron: "0 8 * * *"
  steps:
    - name: extract
      type: job
      job: "./jobs/extract.yaml"
    - name: transform
      type: job
      job: "./jobs/transform.yaml"
      depends_on: ["extract"]      # always a list (supports fan-in / merge)
    - name: notify
      type: action
      action: webhook
      params: { url: "{{ env.WEBHOOK_URL }}" }
      depends_on: ["transform"]
      on_failure: skip
```

### 3. Start the API + Studio backend

```bash
hydra serve                      # FastAPI on http://localhost:8000
# API docs: http://localhost:8000/docs
```

---

## Architecture

**Job = atomic unit.** One source, N transformations, one destination. Two
transformation categories:

- **Job transformations** operate on columns/rows inside a job:
  `filter, select, rename, cast, aggregate, sort, deduplicate, derive, calculate,
  pivot, unpivot, clean, fill_null, trim, index`.
- **Workflow transformations** operate on execution flow between jobs (canvas nodes):
  `split, merge, multicast, union, join, lookup, condition, loop, parallel`.

Rule of thumb: acts on columns/rows -> job transformation; acts on routing between
jobs -> workflow transformation.

**Workflow = orchestrator.** A DAG of jobs and actions. `depends_on` is always a
list. Steps without a common dependency run in parallel.

**Studio hierarchy:** `Project -> Workflows -> Jobs (canvas nodes)`. Persistence in
v1 is YAML files on disk — no database.

**Long-term vision — mosaic architecture.** Hydra is designed as a distributed
mosaic of autonomous nodes (peer-to-peer, no central authority), not a monolith.

---

## Project layout

```
cli/                CLI (hdrctl.py) + i18n (en/es)
internal/           Core: runner, connectors, engines, parsers, schema, cache
workflow/           Workflow parser + DAG runner
api/                FastAPI app and routers
plugins/            Extensible plugins (auth, cache, retry, pagination, ...)
studio/             React Flow visual editor (Vite + TypeScript)
tests/              Test suite (unit + e2e)
examples/           Sample jobs and workflows
docs/               Project documentation
```

---

## Testing

```bash
pip install pytest
pytest tests/test_cli_hdrctl.py tests/test_workflow.py   # CLI + workflow suite
pytest                                                    # full suite
```

Notes:
- `tests/conftest.py` sets `HYDRA_LANG=en` before imports (required for CLI tests).
- E2E tests (`tests/e2e/`) need Docker (MySQL, MongoDB) and are skipped without it.
- `pyarrow` is optional — Parquet tests skip cleanly if it is absent.

---

## Roadmap (ETL Engine v1)

- [x] CLI + i18n (en/es)
- [x] Job runner (source -> transformations -> destination)
- [x] Connectors (CSV, JSON, Parquet, MySQL, PostgreSQL, MongoDB, Web API)
- [x] Workflow runner (DAG, parallelism, `depends_on`)
- [x] REST API (FastAPI)
- [x] Studio — React Flow canvas editor
- [ ] Documentation site (hydraetl.com, GitHub Pages)

---

## License

Hydra ETL Engine is intended to be free and open-source. See repository for details.
