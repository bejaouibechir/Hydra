# End to end: a project that runs two other projects

A nightly retail run, built from **three Hydra ETL projects**:

- `sales` cleans the raw orders and computes the revenue per day;
- `customers` cleans the customer reference data;
- `retail`, the **master**, runs both in parallel, then ranks the top 10 customers and writes a report.

It shows every level of a Hydra ETL project in one example: **project → sub-project → workflows → jobs and actions**. Files only, no database: it runs anywhere in a few seconds.

Requires Hydra ETL **0.19.0** or later (sub-projects).

```bash
pip install -U "hydra-etl[parquet]"
cd examples/end-to-end-retail
hdrctl run retail
```

## What is in it

```
end-to-end-retail/
├── data/                         raw input, shared by the projects
│   ├── orders.csv                312 orders: duplicates, cancelled, empty and negative amounts
│   └── customers.csv             40 customers, names with stray spaces
├── sales/                        sub-project
│   ├── parameters.yaml           run_date (required: given by the caller)
│   ├── jobs/clean_orders/        dedupe, cast, keep paid orders with a positive amount  → CSV
│   ├── jobs/revenue_by_day/      revenue and order count per day                        → Parquet
│   └── workflows/ingest.yaml     clean_orders → revenue_by_day → set_param batch_label
├── customers/                    sub-project
│   ├── jobs/clean_customers/     trim and normalise spaces                              → CSV
│   └── workflows/refresh.yaml
└── retail/                       master project
    ├── parameters.yaml           run_date, default 2026-11-04
    ├── jobs/top_customers/       aggregate per customer, join customers, rank with a window, keep the top 10
    ├── scripts/summary.py        writes outputs/summary.md
    └── workflows/nightly.yaml
```

The master workflow, `retail/workflows/nightly.yaml`:

```
start (log)
 ├── sales      (type: project, run_date passed in, reads back batch_label)
 └── customers  (type: project)
        └── top_customers (job, after both)
               └── summary (python) → report (python, reads the sub-projects' results)
```

```yaml
    - name: sales
      type: project
      project: ../sales
      params:
        run_date: "{{ param:run_date }}"
      outputs: [batch_label]
      timeout: 10m
      depends_on: [start]

    - name: customers
      type: project
      project: ../customers
      timeout: 10m
      depends_on: [start]

    - name: top_customers
      type: job
      job: ../jobs/top_customers
      depends_on: [sales, customers]
```

`sales` and `customers` have no dependency between them, so they run **in parallel**, each in its own process. The last step reads what they returned:

```yaml
    - name: report
      type: action
      action: python
      params:
        script: |
          print("Batch {{ project:sales.param.batch_label }}: sales {{ project:sales.status }}, "
                "{{ project:sales.rows }} rows written; customers {{ project:customers.status }}")
      depends_on: [summary]
```

## 1. Check before running

```bash
hdrctl workflow validate nightly --project retail
```

```
  Projects called by this workflow:
     ↳ sales
     ↳ customers

  ✅ Workflow valid — no errors detected.
```

```bash
hdrctl run retail --dry-run
```

```
  Execution plan
  Stage 1/1 — sequential
     •  nightly  (6: start, sales, customers, top_customers, summary, report)

  ✅ Dry run OK: the project is valid. Nothing was executed.
```

## 2. Run

```bash
hdrctl run retail
```

```
  ▶  Workflow  nightly
     ✓  Step 'start' OK (0.0s)
     ✓  Step 'customers' OK (2.1s)
     │   ▶  Project customers — 1 workflow(s) in 1 stage(s)
     │   ▶  Workflow  refresh
     │      ✓  Step 'clean_customers' OK (1.3s)
     │   ✅ Project 'customers' completed in 1.3s — 1/1 workflow(s) OK
     ✓  Step 'sales' OK (2.1s)
     │   ▶  Project sales — 1 workflow(s) in 1 stage(s)
     │   ▶  Workflow  ingest
     │      ✓  Step 'clean_orders' OK (1.3s)
     │      ✓  Step 'revenue_by_day' OK (0.0s)
     │      ✓  Step 'publish_batch' OK (0.0s)
     │   ✅ Project 'sales' completed in 1.4s — 1/1 workflow(s) OK
     ✓  Step 'top_customers' OK (1.1s)
     ✓  Step 'summary' OK (0.0s)
     │ summary.md written: 10 customers
     ✓  Step 'report' OK (0.0s)
     │ Batch sales-2026-11-04: sales success, 227 rows written; customers success
  ✓  Workflow 'nightly' OK (3.3s)

  ✅ Project 'retail' completed in 3.3s — 1/1 workflow(s) OK
```

Each called project prints its own tree under its step. `227 rows` is what `sales` wrote: 223 clean orders and 4 days of revenue.

## 3. The results

| File | Written by |
|---|---|
| `sales/outputs/orders_clean.csv` | `sales` › `clean_orders` (312 rows in, 223 out) |
| `sales/outputs/revenue_by_day.parquet` | `sales` › `revenue_by_day` |
| `customers/outputs/customers_clean.csv` | `customers` › `clean_customers` |
| `retail/outputs/top_customers.csv` | `retail` › `top_customers` |
| `retail/outputs/summary.md` | `retail` › `summary` |

`retail/outputs/summary.md`:

```
# Top customers — 2026-11-04

| Rank | Customer | Country | Orders | Revenue |
|---|---|---|---|---|
| 1 | Gina 7 | Germany | 7 | 13,756.10 |
| 2 | Emma 30 | Germany | 10 | 11,254.30 |
| 3 | Chloé 20 | Spain | 12 | 10,935.20 |
| 4 | Gina 40 | Germany | 6 | 8,997.80 |
...
```

## 4. Things to try

**Another day.** The parameter goes down to `sales`, which uses it in `batch_label`:

```bash
hdrctl run retail -P run_date=2026-11-05
```

**Run a sub-project on its own.** `sales` declares `run_date` as `required`, so it needs the value:

```bash
hdrctl run sales -P run_date=2026-11-04
```

Without `-P run_date=…`, the run stops at its first step with `missing required parameter: 'run_date'`, before any file is written.

**Break the graph on purpose.** Add a step to `sales/workflows/ingest.yaml` that calls the master back:

```yaml
    - name: back_to_retail
      type: project
      project: ../retail
      depends_on: [publish_batch]
```

```bash
hdrctl workflow validate nightly --project retail
```

```
  ❌ Invalid workflow: sales › workflows/ingest.yaml › step 'back_to_retail': cycle: retail → sales → retail
```

The cycle is refused before anything runs. Remove the step afterwards.

## What passes between the projects

- **Parameters**: only those listed in `params` (`run_date` here).
- **Results**: `status`, `rows`, `duration`, and the parameters listed in `outputs` (`batch_label`).
- **Secrets**: never. Each project keeps its own `.hydra/secrets`; `${SECRET:…}` in `params` is refused.
- **Environment**: only its name (`env: inherit` by default). Each project applies its own `environments/<env>.yaml`.

Reference: [Sub-projects](https://github.com/bejaouibechir/Hydra/blob/main/DSL-whitebook/03-workflows.md) in the Hydra DSL white paper.
