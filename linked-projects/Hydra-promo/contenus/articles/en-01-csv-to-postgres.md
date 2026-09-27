---
title: "CSV to PostgreSQL in 10 minutes with Hydra ETL"
description: "Load a CSV file into PostgreSQL with a declarative YAML pipeline, validated before it runs. No Airflow, no cluster: pip install and four small files."
canonical: https://hydraetl.com/blog/csv-to-postgres
tags: [etl, postgres, python, dataengineering]
---

<!-- ⚠️ BECHIR : exécuter chaque commande de bas en haut avant publication (Postgres local via Docker). Corriger ce qui diffère. -->

# CSV to PostgreSQL in 10 minutes with Hydra ETL

Every team has one: a Python script that reads a CSV export, fixes a few columns and inserts the rows into PostgreSQL. It works until someone else has to change it.

This tutorial does the same job with **Hydra ETL**, an open-source declarative ETL engine. The pipeline is four short YAML files that you can read in a pull request, and a validator checks them before any data moves.

## What you need

- Python 3.9+
- A PostgreSQL database (a local one with Docker is fine):

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=secret -p 5432:5432 postgres:16
```

- Hydra ETL with the PostgreSQL connector:

```bash
pip install "hydra-etl[postgres]"
```

## 1. Create the job

```bash
hdrctl init orders_to_pg --template postgres
cd orders_to_pg
```

A Hydra job is a folder with four files: `sources.yaml`, `transformations.yaml`, `destinations.yaml` and `pipeline.yaml`. We will read a CSV instead of a table, so replace the source.

## 2. Describe the source

`sources.yaml`

```yaml
sources:
  src_orders:
    type: csv
    connection:
      base_path: data
    extract:
      table: orders.csv
      batch_size: 10000
```

Put an `orders.csv` in `data/` with columns `id, customer_id, price, qty`.

## 3. Describe the transformations

`transformations.yaml`

```yaml
steps:
  - cast:
      mapping:
        id: int
        customer_id: int
        price: float
        qty: int
  - filter:
      expr: "price > 0"
  - calculate:
      column: total
      expr: "price * qty"
```

Three steps, in order: fix the types, drop invalid rows, compute a column. No loops, no DataFrame boilerplate.

## 4. Describe the destination

`destinations.yaml`

```yaml
destinations:
  dest_pg:
    type: postgresql
    connection:
      host: ${ENV:PG_HOST}
      port: 5432
      database: ${ENV:PG_DB}
      user: ${ENV:PG_USER}
      password: ${ENV:PG_PASS}
    load:
      table: orders
      mode: upsert
      key: [id]
```

Credentials come from environment variables, so the same file works in dev, staging and production. `mode: upsert` with `key: [id]` makes the job safe to re-run.

`pipeline.yaml` links both ends:

```yaml
pipeline:
  from: src_orders
  to: dest_pg
```

## 5. Validate before you run

```bash
hdrctl validate .
```

The validator parses every manifest against its schema and checks that the pipeline references existing sources and destinations — **without reading or writing any data**. A typo in a step name or a missing destination fails here, not halfway through a load.

To also check that the database answers with these credentials:

```bash
export PG_HOST=localhost PG_DB=postgres PG_USER=postgres PG_PASS=secret
hdrctl test .
```

## 6. Run it

```bash
hdrctl run .
```

Check the result:

```bash
docker exec -it pg psql -U postgres -c "SELECT count(*), sum(total) FROM orders;"
```

## Prefer a visual editor?

```bash
pip install "hydra-etl[server]"
hdrctl serve --open
```

The Studio opens in your browser and edits **the same YAML files**. Nothing to deploy, and the files stay the source of truth in Git.

## When not to use Hydra ETL

Hydra ETL targets file-and-database pipelines that should stay readable and run without infrastructure. If you need to orchestrate hundreds of heterogeneous tasks across a cluster, Airflow or Dagster are better fits; if all your data already lives in a warehouse, dbt is the natural tool. Hydra ETL is in beta: pin your version.

## Next steps

- Code and docs: [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)
- Try it in the browser: [hydraetl.com](https://hydraetl.com)
