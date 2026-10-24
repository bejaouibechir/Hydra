---
title: "Declarative ETL: Why YAML Pipelines Beat Ad-Hoc Scripts"
published: false
description: "Why YAML ETL pipelines beat ad-hoc scripts: validated before they run, readable to whoever inherits them, and one job file for both dev and prod — including where validation stops helping."
tags: dataengineering, etl, yaml, python
canonical_url: https://hydraetl.com/blog/why-yaml-pipelines-beat-ad-hoc-scripts/
cover_image: https://hydraetl.com/og/hydra-etl-og.png
---

> Originally published on [hydraetl.com](https://hydraetl.com/blog/why-yaml-pipelines-beat-ad-hoc-scripts/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts).
>
> *Disclosure: I am the author and sole maintainer of Hydra ETL, the engine used for the examples. It is beta and AGPL-3.0-or-later.*

A declarative ETL pipeline describes *what* the data movement should be — source, transformations, destination — in a configuration file, and lets an engine decide *how* to run it. An ad-hoc script describes the how, line by line, and mixes it with the what. The practical difference is not elegance: a declarative job can be **structurally checked before a single row is read, and refused before it writes anything**, and it stays readable to the person who inherits it. A script can only be checked by running it.

That word *structurally* carries weight, and this article is specific about it: configuration validation catches malformed shape and broken references, not wrong business logic. Where the boundary falls is the interesting part.

This article explains the distinction, then goes where the comparison actually gets decided: **parameters and secrets** — how one job file runs against dev and prod without an `if` statement, and what the validator does *not* catch. It is explicit about where the declarative approach stops helping.

If you want the hands-on version first — building and timing a pipeline over a million rows — read [Clean a million rows with Hydra ETL](https://hydraetl.com/blog/one-million-rows/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts). This article is the *why*, and the configuration layer that tutorial does not cover.

*All commands and outputs below were executed on 19 October 2026 with Hydra ETL 0.11.4, Python 3.13.16, Linux. Terminal output is trimmed (banner removed), not edited. One exception: Hydra ETL 0.11.4 prints its runtime error messages in French; they are shown here in English, and the translation is landing in a coming release.*

## What "declarative" actually means here

**Hydra ETL** — the open-source declarative ETL engine distributed as the `hydra-etl` Python package with the `hdrctl` CLI — is the tool used for the examples. It is unrelated to the columnar PostgreSQL extension named Hydra and to Meta's Hydra configuration library.

In a declarative pipeline you write configuration, not control flow. There is no `for` loop, no `try/except`, no connection handling. A job is a set of YAML files:

```
jobs/job1/
├── sources.yaml
├── destinations.yaml
├── transformations.yaml
└── pipeline.yaml
```

```yaml
# sources.yaml
sources:
  src_csv:
    type: csv
    extract:
      table: data/input.csv
      batch_size: 50000
```

```yaml
# destinations.yaml
destinations:
  dest_csv:
    type: csv
    load:
      table: data/output.csv
      mode: replace
```

```yaml
# transformations.yaml
steps:
  - select:
      columns: [id, name, value]
  - cast:
      mapping:
        value: float
  - filter:
      expr: "value > 0"
```

```yaml
# pipeline.yaml
pipeline:
  from: src_csv
  to: dest_csv
```

That is the whole job — and it does not grow much with volume: the same four files handle a million rows. Someone who has never seen the codebase can read it in under a minute and say what it does: read a CSV, keep three columns, cast one to float, drop non-positive values, write a CSV. The configuration *is* the documentation, and it cannot drift from the implementation because it is the implementation.

The equivalent Python script is not much longer. The difference appears six months later, when the script has acquired a retry, a date parser, a `try/except` someone added during an incident, and a hardcoded path. The YAML version has none of those places to hide, because none of them are expressible in it.

## The real cost of ad-hoc scripts

The cost is rarely the first version. It is:

- **Nobody can audit it without reading all of it.** A reviewer has to trace control flow to answer "which columns does this write?"
- **Failures are discovered at runtime, often half-way through.** A typo in a column name surfaces after the extract has already run.
- **Every script is a dialect.** Two engineers solve retries and typing in two different ways, so knowledge does not transfer between pipelines.
- **The script and its documentation diverge.** The README describes the pipeline as it was.

Declarative configuration addresses the first three directly and makes the fourth structurally impossible. It does not make the underlying work disappear — it moves it into an engine that is written once.

## Validation before execution

This is the part that is hard to replicate with scripts, and it is worth seeing concretely.

A job that is well-formed passes a strict check:

```
$ hdrctl validate jobs/job1

  🔍 DSL Validation  job1

  ok  pipeline.yaml                        — present
  ok  sources.yaml                         — Pydantic valid
  ok  destinations.yaml                    — Pydantic valid
  ok  transformations.yaml                 — Pydantic valid
  ok  pipeline.from                        — resolved: src_csv
  ok  pipeline.to                          — resolved: dest_csv

  ✅ DSL valid — no errors detected.
```

Now introduce two realistic mistakes: a misspelled key (`colums` instead of `columns`) and a destination name that does not exist.

```
$ hdrctl validate jobs/job_broken

  err   → 1 validation error for TransformConfig
steps.0.columns
  Field required [type=missing, input_value={'colums': ['id', 'name', 'value']}, input_type=dict]
  err pipeline.to='dest_postgres' not found in destinations.yaml

  ❌ error(s) detected.
```

Both are caught statically. The second one — a cross-file reference that does not resolve — is the kind of error a script would only reveal at the point of writing, after the extract and the transforms had already consumed time.

Two properties make this usable rather than merely nice:

**The exit code is honest.** [`hdrctl validate`](https://hydraetl.com/cli/03-validate-the-manifests/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts) returns `0` on a valid job and `1` on an invalid one (verified on 0.11.4), so it drops into CI as a pre-merge gate with no wrapper:

```yaml
- run: hdrctl validate jobs/my_job
```

**Execution refuses to start.** Running the broken job fails before any output is produced — the destination file is never created:

```
$ hdrctl run jobs/job_broken
  ❌ Pipeline FAILED
  Cause:
  ValidationError: 1 validation error for TransformConfig
  steps.0.columns
    Field required
```

A partially-written output file is one of the more expensive failure modes in a data pipeline, because it is silently plausible. Refusing to start is the cheaper behaviour.

For reference, the valid job runs like this:

```
$ hdrctl run jobs/job1
  ✅ Pipeline completed successfully in 1.3s
  Rows read   : 3
  Rows written: 2
```

Three rows in, two out — the filter dropped the negative value. The row counts are the audit trail.

## Parameters and secrets: the same job in dev and in prod

This is where the declarative approach earns its keep, and it is the part most "YAML vs scripts" arguments skip.

A pipeline is never one pipeline. It runs against a dev database and a prod one, with a different threshold, a different output table, and credentials that must not be in the repository. In a script, this becomes an `if env == "prod"` branch, a `os.getenv` scattered through the file, or — most often — two copies of the script that slowly diverge.

In Hydra ETL 0.11.4 there are [two separate substitution mechanisms](https://hydraetl.com/dsl/interpolation/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts), with two distinct grammars. Knowing which is which saves an hour of confusion.

### Parameters: `{{ param:NAME }}`

Parameters are read-only inputs, fixed before execution. Declare them once at the project root:

```yaml
# parameters.yaml
parameters:
  min_value:
    type: float
    default: 0
  out_table:
    type: string
    default: data/out_dev.csv
```

Give them values per environment:

```yaml
# environments/prod.yaml
parameters:
  min_value: 150
  out_table: data/out_prod.csv
```

Then reference them anywhere in the job:

```yaml
# transformations.yaml
steps:
  - filter:
      expr: "value > {{ param:min_value }}"
```

```yaml
# destinations.yaml
destinations:
  dest_csv:
    type: csv
    load:
      table: "{{ param:out_table }}"
      mode: replace
```

One job, two behaviours, no branching:

```
$ hdrctl run jobs/job_param --env dev
  ✅ Pipeline completed successfully
  Rows read   : 3
  Rows written: 2

$ hdrctl run jobs/job_param --env prod
  ✅ Pipeline completed successfully
  Rows read   : 3
  Rows written: 1
```

The row counts differ because the threshold differs — and the difference lives in a four-line environment file, not in the pipeline logic. A single value can be [overridden at the command line](https://hydraetl.com/cli/07-pass-parameters/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts), which is what you want for a backfill or a one-off rerun:

```bash
hdrctl run jobs/job_param --env prod -P min_value=99
```

Precedence runs `--param` > job > workflow > project default, resolved for the active environment. Types are preserved: a string that is *exactly* a placeholder returns the typed value, so `"{{ param:batch_size }}"` yields an integer rather than the string `"50000"`. Embedded placeholders — `"schema_{{ param:tenant }}"` — substitute as strings, as you would expect.

### Secrets: `${ENV:VAR}` and `${SECRET:key}`

Credentials use the other grammar. `${ENV:VAR}` reads an environment variable:

```yaml
# sources.yaml
sources:
  src_db:
    type: postgres
    extract:
      host: ${ENV:PG_HOST}
      user: ${ENV:PG_USER}
      password: ${ENV:PG_PASS}
```

A `.env` file in the job directory is picked up automatically, and [`hdrctl test`](https://hydraetl.com/cli/04-test-the-connections/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts) reports what it found:

```
$ hdrctl test jobs/job_db
  Environment variables
  ok  .env                                 — 3 variable(s): PG_HOST PG_USER PG_PASS

  ✅ All tests pass — ready to execute.
```

`${SECRET:key.name}` reads from an injected secret store, and — useful to know, and not obvious — **falls back to an environment variable derived from the key**, with dots and dashes becoming underscores and the whole name uppercased: `${SECRET:db.password}` resolves from `DB_PASSWORD`. That means the same manifest works against a secret manager in production and a plain `.env` locally, with no edit.

When a value is missing, the failure names both the variable and the file that referenced it:

```
$ hdrctl run jobs/job_db
  ❌ Pipeline FAILED
  Cause: JobExecutor: failed to resolve variables in
  /path/to/jobs/job_db/sources.yaml: Missing environment variable: PG_PASS
```

Note that this fires before any connection is attempted — the credentials are resolved when the manifest is loaded, so a missing secret costs you a second, not a hung connection timeout.

That is a better failure than a script's `None` quietly propagating into a connection string.

### Where the validation boundary actually falls

This is the single most useful thing to understand about declarative ETL, and it is where the marketing version of the pitch breaks down. **Validation checks the shape of your configuration. Execution checks reality.** Three concrete cases, all verified on 0.11.4:

**Placeholder names are resolved at run time.** Neither `validate` nor `test` resolves parameters or secrets, so a typo passes both gates:

```
$ hdrctl validate jobs/job_param      # expr uses {{ param:min_valu }} — typo
  ✅ DSL valid — no errors detected.    # exit 0
$ hdrctl test jobs/job_param
  ✅ All tests pass — ready to execute. # exit 0

$ hdrctl run jobs/job_param --env prod
  ❌ Pipeline FAILED
  Cause: JobExecutor: failed to resolve parameters in
  /path/to/jobs/job_param/transformations.yaml: unresolved parameter: 'min_valu'
```

**Column names are resolved at run time.** Selecting a column that the source does not provide validates cleanly and fails on the first batch:

```
$ hdrctl validate jobs/job_badcol
  ✅ DSL valid — no errors detected.    # exit 0

$ hdrctl run jobs/job_badcol
  ❌ Pipeline FAILED
  Cause: Error at step 1/2: select: unknown columns ['prix'].
  Loaded columns: ['id', 'name']
```

**Connector types are resolved at run time.** The DSL accepts any string for `type:`; the registry is consulted when the job runs:

```
$ hdrctl validate jobs/job_unknown
  ✅ DSL valid — no errors detected.

$ hdrctl run jobs/job_unknown
  ❌ Pipeline FAILED
  Cause: JobExecutor: failed to instantiate source 'src_csv'
  (type='snowflake'). Error: Connector 'src_csv': unknown type 'snowflake'.
  Supported types: csv, json, mariadb, mongodb, mssql, mysql, parquet,
  postgres, postgresql, sqlserver
```

One more gap worth knowing: `hdrctl test` reports the variables your `.env` *contains* without checking them against the variables your manifests *reference*, so a `.env` holding the wrong variable name still shows `✅ All tests pass`.

The practical consequence is a two-stage gate, not a one-stage one. Keep `hdrctl validate` in CI as a pre-merge check — it is fast, needs no credentials, and catches the errors people actually make. Then add a smoke run against a dev environment, because that is the only thing that catches a bad placeholder, a missing column or a wrong connector type before production does.

That is a real limitation, and it is also not specific to Hydra ETL: no configuration validator can know what your source will contain at 3am. What the declarative layer buys you is that the first stage exists at all.

## Where declarative ETL stops helping

Any honest case for this approach has to include its edges.

**Validation is not verification.** As shown above, it checks structure, required fields, types and cross-file references — not business logic, and nothing that requires touching the data. A job whose `filter` expression is semantically wrong validates perfectly. Treat it as a cheap first gate, not a correctness proof.

**The engine's vocabulary is a ceiling.** You get the operations the engine implements — in 0.11.4 that is 18 of them (`select`, `filter`, `cast`, `join`, `aggregate`, `pivot`, `deduplicate`, `script`, and others). A transformation outside that set either needs the `script` escape hatch or does not belong in the declarative layer.

**Connector coverage is finite.** CSV, JSON, Parquet, MySQL/MariaDB, PostgreSQL, SQL Server, MongoDB and Web API are supported in 0.11.4. Cloud warehouses such as BigQuery, Snowflake and S3 are not. If your sources live there, this specific engine is not your answer today.

**Maturity matters.** Hydra ETL is published as beta, AGPL-3.0-or-later, with a single maintainer. That is a real consideration for production adoption, and no amount of design elegance offsets it.

## When a script is still the right answer

Declarative configuration is a poor fit when the logic *is* the point: a one-off migration you will run twice and delete, exploratory work where the shape of the transformation is unknown, or logic with genuine branching and stateful control flow. Forcing those into YAML produces configuration that is harder to read than the script it replaced — the exact failure the approach is meant to prevent.

The useful dividing line is repetition. A transformation that runs on a schedule, that someone else will maintain, and whose correctness matters more than its cleverness, belongs in configuration. Everything else can stay a script.

## Frequently asked questions

### Does declarative ETL mean no code at all?
No. It means the *pipeline definition* is configuration. Engines typically keep an escape hatch for custom logic — Hydra ETL exposes a `script` operation — and the engine itself is code someone maintains.

### Can a YAML pipeline be version-controlled and reviewed?
Yes, and this is a large part of the value. A diff on `transformations.yaml` shows exactly which columns changed. A diff on a 300-line Python script rarely does.

### Is YAML not just a worse programming language?
It is, if you try to program in it. Used as configuration with a validated schema and a fixed vocabulary of operations, the constraint is the feature: there are fewer ways to express the same thing, so pipelines converge on one readable form.

### How do I keep credentials out of my YAML pipeline?
Reference them instead of writing them: in Hydra ETL, `${ENV:PG_PASS}` reads an environment variable and `${SECRET:db.password}` reads an injected secret store, falling back to the matching environment variable (`DB_PASSWORD`). A `.env` file in the job directory is loaded automatically. The manifest stays committable because it contains references, not values.

### Can one YAML job run against both dev and production?
Yes, through parameters. Declare them in `parameters.yaml`, give them per-environment values in `environments/<name>.yaml`, reference them as `{{ param:name }}`, and select the environment at run time with `--env prod`. A single value can be overridden with `-P key=value`. The pipeline logic is identical in both environments.

### Why are there two placeholder syntaxes?
They solve different problems. `{{ param:name }}` is for configuration that is declared, typed and versioned — thresholds, table names, batch sizes. `${ENV:VAR}` and `${SECRET:key}` are for values that must never be committed. Parameters are resolved from files in the repository; secrets are resolved from the environment or a secret store.

### How is this different from dbt or Airflow?
Different layer. [Airflow](https://hydraetl.com/migrate/airflow/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts) orchestrates *when* tasks run; [dbt](https://hydraetl.com/migrate/dbt/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts) transforms data already inside a warehouse with SQL. A declarative ETL engine moves and transforms data *between* systems. They overlap at the edges and are often used together.

### Can the same job be edited visually?
In Hydra ETL, yes — `hdrctl serve` (installed with `pip install hydra-etl[server]`) starts a REST API and a visual studio on `127.0.0.1:5678`, over the same job files, with OpenAPI docs at `/docs`. The YAML remains the source of truth, which is what keeps the CLI and the visual editor from drifting apart.

## Conclusion

The argument for declarative ETL is not that YAML is pleasant. It is that a pipeline expressed as validated configuration can be read by a stranger, diffed by a reviewer, gated in CI, and refused before it corrupts an output — four properties an ad-hoc script gives you only through discipline that does not survive staff turnover.

Parameters and secrets are where that stops being an aesthetic preference. One job file, two environments, no duplicated logic, and credentials that never enter the repository — that is a maintenance property, not a style choice.

The honest scope: it applies to repeated, maintained pipelines, within the vocabulary and connector set your engine supports; validation catches structure rather than meaning; and placeholder substitution happens at run time, so a smoke run still belongs in your pipeline.

To try the example in this article:

```bash
pip install hydra-etl
hdrctl init my_project
cd my_project
hdrctl validate jobs/job1
hdrctl run jobs/job1
```

(`hdrctl init my_project` creates the project in a `my_project/` directory, so the `cd` matters — without it the next command reports `Directory not found: jobs/job1`. Use `hdrctl init .` to scaffold into the current directory instead.)

## Next

- Code, docs and issues: [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)
- Try it in the browser, nothing to install: [hydraetl.com/playground](https://hydraetl.com/playground/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts)
- The hands-on companion piece: [Clean a million rows with Hydra ETL](https://hydraetl.com/blog/one-million-rows/?utm_source=devto&utm_medium=article&utm_campaign=yaml-vs-scripts)

If you run file-and-database pipelines and something here does not match your experience, I want to hear it — the disagreements are more useful to me than the agreements.
