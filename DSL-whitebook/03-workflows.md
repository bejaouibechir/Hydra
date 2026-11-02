<!-- Hydra DSL White Paper — Chapter 3: Workflows
     DSL format version: 1.0 · Hydra 0.19.0
     Sources: workflow/{models,parser,runner,expr,conditions,rollback,thread,project}.py,
     internal/connector/undo.py, api/scheduler.py, cli/hdrctl.py (workflow run/undo/validate), workflow/subprojects.py (0.19) -->

# Hydra DSL - Workflows

A **workflow** runs **steps** in a given order. A step is a **job**, an **action** or, since Hydra 0.19, another **project**.

```yaml
# workflows/daily_sales.yaml
version: "1.0"
workflow:
  name: daily_sales
  description: Load the sales, then notify the team
  trigger:
    type: schedule
    cron: "0 6 * * *"
  steps:
    - name: load_sales
      type: job
      job: ../jobs/sales

    - name: notify
      type: action
      action: webhook
      params:
        url: https://hooks.example.com/etl
      depends_on: [load_sales]
```

> **[FIGURE fig-03-01 · diagram]** The workflow above drawn as a graph: a trigger (clock icon, 06:00) → `load_sales` (job box) → `notify` (action box).

## Syntax

| Key           | Required | Default  | Description                                       |
| ------------- | -------- | -------- | ------------------------------------------------- |
| `name`        | Yes      | –        | Name of the workflow                              |
| `description` | No       | –        | Free text                                         |
| `trigger`     | No       | `manual` | When the workflow starts                          |
| `rollback`    | No       | `false`  | Undo the steps already done if the workflow fails |
| `steps`       | Yes      | –        | List of steps                                     |

## Rules for workflows

- The file has a top-level `workflow:` key. Only `version` and `workflow` are allowed at the top level.
- Every key is checked: an unknown or misspelled key is refused, with a suggestion.
- Step names must be unique in the workflow.
- The order of the steps in the file **is not** the execution order. The order comes from `depends_on`.
- A workflow lives in `workflows/<name>.yaml`. Paths in it are relative to that folder.

## Running a workflow

```bash
hdrctl workflow validate daily_sales   # check, run nothing
hdrctl workflow run daily_sales        # run this workflow
hdrctl run .                           # run all the workflows of the project (see Thread)
```

---

# Hydra DSL - Trigger

The trigger says **when** a workflow starts.

| `type`             | Starts                        | Extra key         |
| ------------------ | ----------------------------- | ----------------- |
| `manual` (default) | When you run it               | –                 |
| `schedule`         | On a schedule                 | `cron` (required) |
| `webhook`          | When an HTTP call is received | –                 |

```yaml
trigger:
  type: manual
```

```yaml
trigger:
  type: schedule
  cron: "30 2 * * 1-5"     # 02:30, Monday to Friday
```

```yaml
trigger:
  type: webhook
```

## Rules for triggers

- `cron` is a standard 5-field expression: minute, hour, day of month, month, day of week.
- `type: schedule` without `cron` is refused.
- `schedule` and `webhook` are used by the Hydra server (`hdrctl serve`). `hdrctl run` and `hdrctl workflow run` always start the workflow immediately.

| `cron`           | Meaning                         |
| ---------------- | ------------------------------- |
| `"0 * * * *"`    | Every hour, on the hour         |
| `"0 6 * * *"`    | Every day at 06:00              |
| `"*/15 * * * *"` | Every 15 minutes                |
| `"0 8 1 * *"`    | The 1st of every month at 08:00 |

---

# Hydra DSL - Steps

## Syntax

| Key          | Applies to     | Default | Description                                |
| ------------ | -------------- | ------- | ------------------------------------------ |
| `name`       | all            | –       | Unique name. Required                      |
| `type`       | all            | –       | `job`, `action` or `project`. Required     |
| `job`        | `type: job`    | –       | Path to the job folder                     |
| `action`     | `type: action` | –       | Name of the action                         |
| `params`     | `type: action`, `type: project` | – | Parameters of the action, or passed to the called project |
| `project`    | `type: project` | –      | Called project (see *Sub-projects*)        |
| `depends_on` | all            | `[]`    | Steps that must finish first               |
| `on_failure` | all            | `fail`  | `fail` · `skip` · `continue`               |
| `enabled`    | all            | `true`  | `false` skips the step                     |
| `when`       | all            | –       | Run the step only if the condition is true |
| `retry`      | all            | –       | Retry policy                               |
| `undo`       | `type: action` | –       | How to reverse the action (rollback)       |

## Rules for steps

- `type: job` requires `job`; `type: action` requires `action`.
- `type: project` requires `project`.
- `action` and `params` are refused on a job step; `job` is refused on an action step; `job`, `action` and `undo` are refused on a project step; the project keys are refused on job and action steps.
- An unknown action, an unknown parameter, or a missing required parameter is refused before the run.

## A job step

```yaml
- name: load_customers
  type: job
  job: ../jobs/customers
```

Before running, Hydra checks that the job folder exists and that its source and destination are configured.

## An action step

```yaml
- name: wait_for_replica
  type: action
  action: delay
  params:
    seconds: 30
```

The available actions are described in the *Actions* chapter.

## A project step

```yaml
- name: crm_sync
  type: project
  project: ../crm_sync
```

Runs another Hydra project. See *Sub-projects* below.

---

# Hydra DSL - Order and Parallelism

`depends_on` lists the steps that must be finished before a step starts. It is always a list, even with one element.

## Rules for depends_on

- Steps with no `depends_on` start **at the beginning, in parallel**.
- Steps whose dependencies are all finished start **together, in parallel**.
- A name in `depends_on` that does not exist is refused.
- A cycle (`a` depends on `b`, `b` depends on `a`) is refused.

## Example 1: a sequence

```yaml
steps:
  - name: extract
    type: job
    job: ../jobs/extract
  - name: transform
    type: job
    job: ../jobs/transform
    depends_on: [extract]
  - name: publish
    type: job
    job: ../jobs/publish
    depends_on: [transform]
```

`extract` → `transform` → `publish`.

## Example 2: fan-out and fan-in

```yaml
steps:
  - name: load_orders
    type: job
    job: ../jobs/orders
  - name: load_customers
    type: job
    job: ../jobs/customers
  - name: load_products
    type: job
    job: ../jobs/products
  - name: build_report
    type: job
    job: ../jobs/report
    depends_on: [load_orders, load_customers, load_products]
```

The three loads run in parallel. `build_report` starts when all three are finished.

> **[FIGURE fig-03-02 · diagram]** Example 2 as a graph on a time axis: three parallel boxes, then `build_report` starting when the last of them ends.

## Example 3: the classic mistake

```yaml
steps:
  - name: create_table
    type: action
    action: bash
    params: { command: "./scripts/create_table.sh" }
  - name: load
    type: job
    job: ../jobs/load        # no depends_on!
```

Both steps start at the same time. Add `depends_on: [create_table]` to `load`.

> **[LAB lab-03-01 · Killercoda]** **Draw your workflow** — Run a workflow of five steps with different `depends_on`, read the start and end times in the run report, and redraw the graph.

---

# Hydra DSL - Failure Handling

## on_failure

| Value            | The failed step…      | Steps depending on it | The workflow                                                    |
| ---------------- | --------------------- | --------------------- | --------------------------------------------------------------- |
| `fail` (default) | stops the workflow    | are skipped           | stops, **failed**                                               |
| `skip`           | is recorded as failed | are skipped           | goes on with the other branches, ends **completed with errors** |
| `continue`       | is recorded as failed | **still run**         | goes on, ends **completed with errors**                         |

```yaml
- name: notify_slack
  type: action
  action: webhook
  params:
    url: https://hooks.slack.com/services/XXX
  depends_on: [load_sales]
  on_failure: continue      # a notification failure must not block the rest
```

> **[FIGURE fig-03-03 · diagram]** The same 4-step graph shown three times, with step B failing: in `fail` everything after stops; in `skip` only B's descendants are greyed out; in `continue` B is red and its descendants still run.

## enabled

```yaml
- name: heavy_backfill
  type: job
  job: ../jobs/backfill
  enabled: false
```

The step is skipped and reported as `DISABLED`. Steps that depend on it still run.

## retry

| Key       | Default | Description                                           |
| --------- | ------- | ----------------------------------------------------- |
| `max`     | `0`     | Number of retries **after** the first failure         |
| `delay`   | `0`     | Seconds to wait before a retry                        |
| `backoff` | `fixed` | `fixed` (same delay) or `exponential` (delay doubles) |

### Example 1: fixed delay

```yaml
- name: call_api
  type: action
  action: webhook
  params:
    url: https://api.example.com/refresh
  retry:
    max: 3
    delay: 10
```

Up to 4 attempts, 10 s apart.

### Example 2: exponential backoff

```yaml
retry:
  max: 4
  delay: 5
  backoff: exponential
```

| Attempt | Wait before it |
| ------- | -------------- |
| 1       | –              |
| 2       | 5 s            |
| 3       | 10 s           |
| 4       | 20 s           |
| 5       | 40 s           |

`on_failure` applies only after the last attempt.

> **[LAB lab-03-02 · Killercoda]** **When things go wrong** — Make an action fail on purpose, then try `on_failure: fail`, `skip` and `continue`, and add a `retry` with exponential backoff.

---

# Hydra DSL - Conditional Steps

`when` runs a step only if a condition is true.

```yaml
- name: load_prod_only
  type: job
  job: ../jobs/sync
  when: "{{ param:env_name }} == 'prod'"
```

## Rules for when

- Values come from parameters `{{ param:NAME }}` and environment variables `{{ env:NAME }}`.
- Allowed: comparisons (`==` `!=` `<` `<=` `>` `>=`), `in`, `not in`, `and`, `or`, `not`, text, numbers, `True`, `False`, lists.
- Not allowed: function calls, attributes, any other name. The expression is never executed as code.
- Two values that look like numbers are compared as numbers: `"10" > "9"` is true.
- If the condition is **false**, the step is skipped, **and so are the steps that depend on it**.
- If the condition cannot be read, the step fails.

## Examples

```yaml
when: "{{ param:row_count }} > 0"
```

```yaml
when: "{{ param:country }} in ['FR', 'BE', 'LU']"
```

```yaml
when: "{{ env:HYDRA_ENV }} != 'dev' and {{ param:full_load }} == True"
```

## Routing with a condition action

A `condition` action computes a true/false value and stores it as a parameter. Later steps use it in `when`:

```yaml
steps:
  - name: check_volume
    type: action
    action: condition
    params:
      name: is_big
      expr: "{{ param:expected_rows }} > 1000000"

  - name: load_big
    type: job
    job: ../jobs/load_duckdb
    depends_on: [check_volume]
    when: "{{ param:is_big }} == True"

  - name: load_small
    type: job
    job: ../jobs/load_pandas
    depends_on: [check_volume]
    when: "{{ param:is_big }} == False"
```

> **[FIGURE fig-03-04 · diagram]** `check_volume` as a diamond with two branches, `load_big` (taken) and `load_small` (skipped, greyed).

---

# Hydra DSL - Rollback and Undo

With `rollback: true`, a workflow that fails **undoes the steps already done**, from the last to the first.

```yaml
workflow:
  name: monthly_close
  rollback: true
  steps:
    - name: load_invoices
      type: job
      job: ../jobs/invoices
    - name: load_payments
      type: job
      job: ../jobs/payments
      depends_on: [load_invoices]
```

If `load_payments` fails, the load of `load_invoices` is undone.

> **[FIGURE fig-03-05 · diagram]** A stack: steps pushed as they succeed (invoices, payments…), then, on failure, popped from top to bottom with an "undo" arrow on each.

## What can be undone

**Jobs** are undone automatically:

| Destination   | `replace`               | `append`                                                           | `upsert`                                 |
| ------------- | ----------------------- | ------------------------------------------------------------------ | ---------------------------------------- |
| CSV / Parquet | previous file restored  | file cut back to its previous size (CSV) / previous file (Parquet) | –                                        |
| Database      | previous table restored | rows of this run deleted (`load.key` required)                     | previous rows restored, new rows deleted |

**Actions** that act outside Hydra (`webhook`, `email`, `bash`, `powershell`, `ssh`, `python`) must say how to undo them, with `undo:`:

```yaml
- name: open_ticket
  type: action
  action: webhook
  params:
    url: https://tickets.example.com/api/open
  undo:
    action: webhook
    params:
      url: https://tickets.example.com/api/cancel

- name: send_report
  type: action
  action: email
  params:
    to: finance@example.com
  undo: none          # nothing to reverse, accepted
```

`log`, `delay`, `condition`, `set_param` and `assign_param` need no `undo`.

## Rules for rollback

- Everything is checked **before** the run. The run does not start if:
  - an action that acts outside Hydra has no `undo:`;
  - a job appends into a database without `load.key`;
  - a job uses a mode that cannot be undone for its destination.
- `undo:` is allowed on action steps only. Jobs are undone automatically.
- A `type: project` step cannot be undone: `rollback: true` refuses it.
- Before undoing a load, Hydra checks that nobody else wrote to the destination since. If someone did, the undo is refused rather than erasing their work.
- If an undo fails, the rest is kept in `.hydra/undo/<workflow>.json`. Finish it with:

```bash
hdrctl workflow undo monthly_close
```

- While that file exists, the workflow refuses to start.
- When the workflow succeeds, the backups are deleted.

> **[LAB lab-03-03 · Killercoda]** **Rollback in action** — Load two tables, make the third step fail, and check that both tables are back to their previous state; then simulate an interrupted rollback and finish it with `hdrctl workflow undo`.

> **[GITHUB gh-03-01 · example]** **workflow_rollback** — Project with a 3-step workflow in `rollback: true` (two database jobs with `load.key`, one webhook with `undo:`), a `docker-compose.yml` for PostgreSQL and a script that makes the last step fail.

---

# Hydra DSL - Thread

A project usually has several workflows. `workflows/thread.yaml` says in which order `hdrctl run .` runs them.

```yaml
# workflows/thread.yaml
version: "1.0"
thread:
  - mode: sequential
    workflows:
      - name: load_referentials
  - mode: parallel
    delay_after: 5m
    workflows:
      - name: load_sales
      - name: load_stock
  - mode: sequential
    workflows:
      - name: build_reports
```

> **[FIGURE fig-03-06 · diagram]** The thread above as three stages on a time axis: `load_referentials`, then `load_sales` and `load_stock` side by side, a 5-minute pause, then `build_reports`.

## Stages

| Key           | Default      | Description                                                             |
| ------------- | ------------ | ----------------------------------------------------------------------- |
| `mode`        | `sequential` | `sequential`: one workflow after another · `parallel`: at the same time |
| `delay_after` | –            | Pause before the next stage                                             |
| `workflows`   | –            | Workflows of the stage. At least one                                    |

## Workflows in a stage

| Key            | Default | Description                            |
| -------------- | ------- | -------------------------------------- |
| `name`         | –       | Runs `workflows/<name>.yaml`. Required |
| `active`       | `true`  | `false` skips the workflow             |
| `delay_before` | –       | Wait before starting it                |
| `timeout`      | –       | Maximum duration. Exceeded = failure   |
| `fallback`     | –       | A replacement workflow (see below)     |

## Rules for the thread

- Stages run one after another, in the order of the file.
- Durations are a number of seconds, or `500ms`, `30s`, `5m`, `1h`.
- A failed workflow **stops the project**: the next workflows do not start. In a parallel stage, the workflows already started finish.
- `delay_before` counts from the end of the previous workflow (sequential) or from the start of the stage (parallel).
- When `timeout` is exceeded, the workflow stops at the next batch or step; an atomic load is cancelled; an action already started goes to its end.
- Without `thread.yaml`, all `workflows/*.yaml` run one after another, in alphabetical order.

## Loops

Replays a part of the thread several times.

```yaml
loops:
  - from: load_stock        # last workflow of the part
    to: load_sales          # first workflow of the part
    times: 3                # total runs, 1 to 1000
    delay: 10m              # pause before each replay
```

- `to` must come before `from` in the thread, or be the same workflow.
- A loop starting or ending in a parallel stage takes the whole stage.
- Several loops are allowed if they do not overlap.

## Fallback

A replacement workflow, declared on the workflow it replaces:

```yaml
- name: load_crm
  timeout: 30m
  fallback:
    use: [load_crm_from_backup]
    when: "not source_available('crm_db')"
    on_failure: true
    on_probe_error: keep
```

| Key              | Default | Description                                                                      |
| ---------------- | ------- | -------------------------------------------------------------------------------- |
| `use`            | –       | Replacement workflows, tried in order. Required                                  |
| `when`           | –       | Condition checked just before the start                                          |
| `on_failure`     | `false` | `true`: also replace after a failure or a timeout, if nothing was left published |
| `on_probe_error` | `keep`  | If the condition cannot be checked: `keep` the workflow, or `replace` it         |

- Replacements are `workflows/<name>.yaml` files that are **not** in the thread.
- A replacement has no fallback of its own.
- An inactive workflow does not check its fallback.

### The fallback condition language

| Function / value              | Returns                                                        |
| ----------------------------- | -------------------------------------------------------------- |
| `source_available('id')`      | The source answers                                             |
| `destination_available('id')` | The destination answers                                        |
| `file_exists('path')`         | The file exists (path relative to the project)                 |
| `file_size('path')`           | Size, compared with `10KB`, `5MB`, `1GB`                       |
| `file_age('path')`            | Time since last change, compared with `30s`, `5m`, `24h`, `7d` |
| `url_ok('url')`               | HTTP answer 2xx or 3xx                                         |
| `secret_defined('NAME')`      | The secret is set                                              |
| `db.load('id')`               | Active queries on a database                                   |
| `previous.status`             | `success` · `failed` · `skipped` · `inactive` · `none`         |
| `previous.rows`               | Rows written by the previous workflow                          |

```yaml
when: "file_size('Data/in.csv') < 1MB or file_age('Data/in.csv') > 24h"
```

```yaml
when: "previous.status == 'failed' and previous.rows < 100"
```

> **[LAB lab-03-04 · Killercoda]** **Orchestrate a project** — Build a thread of four workflows with a parallel stage, a loop and a fallback triggered by stopping a database container.

> **[GITHUB gh-03-02 · example]** **project_thread** — Project with five workflows, a `thread.yaml` using stages, `delay_after`, `timeout`, a loop and a fallback, and a README explaining each run.

---

# Hydra DSL - Sub-projects

*Hydra 0.19.0+.* A step of `type: project` runs **another Hydra project**: its `thread.yaml`, or only the workflows listed. The calling project is the **master**; the called projects are its sub-projects.

```yaml
# master/workflows/nightly.yaml
workflow:
  name: nightly
  steps:
    - name: crm_sync
      type: project
      project: ../crm_sync          # folder relative to the master's root
      env: inherit                  # inherit | none | <environment>
      params:
        batch_date: "{{ param:run_date }}"
      variables:
        EXPORT_DIR: out/crm
      workflows: [ingest, report]
      outputs: [last_batch]
      timeout: 10m

    - name: report
      type: action
      action: log
      when: "{{ project:crm_sync.status }} == 'success'"
      params:
        message: "{{ project:crm_sync.rows }} rows, batch {{ project:crm_sync.param.last_batch }}"
      depends_on: [crm_sync]
```

> **[FIGURE fig-03-08 · diagram]** A master project with two called projects; arrows labelled with what passes (environment name, params, variables) and a crossed-out padlock for secrets; the results flowing back (`status`, `rows`, `outputs`).

## Syntax

| Key         | Default     | Description |
| ----------- | ----------- | ----------- |
| `project`   | –           | Called project: folder relative to the master's root (`ref: path`) or Studio workspace name (`ref: name`). Required |
| `ref`       | `path`      | `path` (portable with git) · `name` |
| `env`       | `inherit`   | Environment of the called project: `inherit` (same name, its own files) · `none` · a name |
| `params`    | –           | Parameters given to the called project, with the rank of `-P` |
| `variables` | –           | Environment variables lent for this run only |
| `workflows` | thread.yaml | Workflows to run, in this order |
| `outputs`   | –           | Parameters of the called project read back with `{{ project:STEP.param.NAME }}` |
| `isolation` | `inprocess` | `inprocess` (same process, isolated environment) · `subprocess` (separate `hdrctl`) |
| `timeout`   | –           | Maximum duration: `30s`, `5m`, `1h` or seconds |
| `overlap`   | `wait`      | Project already running: `wait` · `skip` · `fail` |

## What passes, what does not

- **Environment**: only its name. The called project applies its own `environments/<env>.yaml`, `~/.hydra/env.<env>` and `.hydra/secrets.<env>`.
- **Parameters**: only those listed in `params`. A `required` parameter of the called project without a value stops the step before anything runs.
- **Variables**: only those listed in `variables`. The master's `.env`, `--env-file`, `--secrets-file` and global variables do not leak.
- **Secrets**: never. `${SECRET:…}` in `params` or `variables` is refused; each project keeps its own `.hydra/secrets`.

## Results

| Placeholder                       | Value |
| --------------------------------- | ----- |
| `{{ project:STEP.status }}`       | `success` · `failed` · `skipped` |
| `{{ project:STEP.rows }}`         | Rows written by the called project |
| `{{ project:STEP.duration }}`     | Duration in seconds |
| `{{ project:STEP.param.NAME }}`   | A parameter listed in `outputs` (`set_param`, `assign_param` or declared). Missing = step failed |

## Rules for sub-projects

- A project cannot call itself, directly or through others (`cycle: master → crm_sync → master`), and calls are limited to **5 levels**. A node of the graph is a project *and* the workflows it runs: a project may call another of its own workflows.
- These checks run in `hdrctl run` (and `--dry-run`), `hdrctl workflow validate` (which prints the tree of called projects), in Hydra Studio when a project is dropped on the canvas, and in the MCP tool `hydra_project_calls`. A `project` computed with `{{ … }}` is checked at run time.
- A project runs **once at a time** (`.hydra/run.lock`, also between processes). `overlap` decides what a second call does.
- Steps that run in parallel always use `isolation: subprocess`.
- `timeout`: in the same process, the called project stops at its next checkpoint; in a separate process, the process is stopped.
- The called project's output (workflows, steps) appears in the log of the step, as a tree.

## Running part of a project

```bash
hdrctl run ../crm_sync -w ingest -w report --env prod
```

`-w` (repeatable) runs only these workflows, in order.

> **[LAB lab-03-05 · Killercoda]** **Master and sub-projects** — A master calls two projects in dev and prod, reads back a published parameter, then a cycle is introduced and refused by `hdrctl workflow validate`.
