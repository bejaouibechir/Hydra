<!-- Hydra DSL White Paper — Chapter 1: Basics
     DSL format version: 1.0 · Hydra 0.16.0
     Sources: hydra_etl/__init__.py, internal/dsl_version.py, workflow/parser.py,
     workflow/models.py, cli/hdrctl.py (init, run), examples/minimal_csv -->

# Hydra DSL - Introduction

Hydra DSL is the language used to describe data pipelines in Hydra ETL. It is written in **YAML**: no code to compile, only files that describe *what* to move and *how*.

The language has three building blocks:

**Job**:

Reads data from a source, transforms it, writes it to a destination

 ![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\11.png)

A folder of YAML files:

![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\12.png)

![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\13.png)

**Workflow:**

Runs jobs and actions in a given order, with conditions, retries and rollback

![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\15.png)

Workflow are defined in **workflows/.yaml:**

![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\14.png)

**Action:**

Does something outside the workflow

A Hydra workflow supports **11 action types**:

| Action         | Purpose                                                                   |
| -------------- | ------------------------------------------------------------------------- |
| `log`          | Write a message to the execution log.                                     |
| `delay`        | Wait for a specified duration.                                            |
| `condition`    | Evaluate a condition and store its Boolean result in a runtime parameter. |
| `webhook`      | Send an HTTP request.                                                     |
| `email`        | Send an email through SMTP.                                               |
| `bash`         | Run a Bash command on Linux or macOS.                                     |
| `powershell`   | Run a PowerShell command on Windows.                                      |
| `ssh`          | Run a command on a remote machine through SSH.                            |
| `python`       | Run an inline Python script or call a Python file.                        |
| `set_param`    | Create a runtime parameter. Fails if it already exists.                   |
| `assign_param` | Update an existing runtime parameter. Fails if it does not exist.         |

Declare an action using `type: action`, followed by its name in `action:`:

```yaml
- name: announce_start
  type: action
  action: log
  params:
    message: "Workflow started."
```

## How Workflows are structured:

Workflows are grouped in a **project**. The order in which the workflows of a project run is set by a **thread** (`workflows/thread.yaml`).

<img title="" src="file:///C:/Users/DELL/Desktop/Hydra/DSL-whitebook/images/01-basics/16.png" alt="" data-align="center">

**thread.yaml** organises how workflows are called, bellow are thread.yaml example 

![](C:\Users\DELL\AppData\Roaming\marktext\images\2026-10-30-12-32-58-image.png)

## A first look how job do

In this example a job reads a CSV file, keeps the rows with a positive price, computes a total and writes the result into the destination:

```yaml
# sources.yaml
version: "1.0"
sources:
  source_csv:
    type: csv
    connection: {}
    extract:
      table: data/input.csv
```

```yaml
# transformations.yaml
version: "1.0"
transformations:
  steps:
    - filter:
        expr: "price > 0"
    - calculate:
        column: total
        expr: "price * qty"
```

```yaml
# destinations.yaml
version: "1.0"
destinations:
  dest_csv:
    type: csv
    connection: {}
    load:
      table: data/output.csv
      mode: replace
```

```yaml
# pipeline.yaml
version: "1.0"
pipeline:
  from: source_csv
  to: dest_csv
```

Four short files, and the job is complete. The next chapters explain each of them.

---

# Hydra DSL - Basics

## Rules for writing Hydra DSL files

When you write Hydra DSL files, remember the following rules:

- Hydra DSL files are **YAML** files. Use spaces for indentation, never tabs.
- Job files may use the `.yaml` or `.yml` extension.
- Each file starts with `version: "1.0"`. This is the version of the **DSL format**, not the version of Hydra.
- Keys are fixed by the language. In a workflow, an unknown or misspelled key is **rejected**, with a suggestion.
- Names you choose yourself (source ids, destination ids, step names) are free, but must be unique in their file.

## Mistakes are reported, not ignored

A misspelled key is not silently skipped. For example, in a workflow:

```yaml
steps:
  - name: notify
    type: action
    action: webhok          # typo to provoque error
    params:
      url: https://example.com/hook
```

Hydra stops before running anything and reports:

```
Step 'notify': unknown action 'webhok'. Valid actions: assign_param, bash, condition,
delay, email, log, powershell, python, set_param, ssh, webhook — did you mean 'webhook'?
```

To practice that case here is the lab on **killercoda**

**Hands-on lab: [Read Hydra's error messages](https://killercoda.com/hydra-etl/scenario/07-read-hydra-error-messages)**

![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\17.png)

**About the lab:** Practice in your browser with a guided Killercoda lab. Use `hdrctl run . --dry-run` to diagnose and fix an unknown action (`webhok`), a misspelled key (`depend_on`) and a missing required `action` field. Then check why omitting `version` is accepted. No workflow action is executed.

**Duration:** about 12 minutes. **Prerequisite:** basic YAML indentation.

The same applies to a misplaced key such as `depend_on` instead of `depends_on`.

# Hydra DSL - Project Structure

## A job folder

A job is a folder. Hydra recognises a job by its files:

| File                   | Required | Role                                 |
| ---------------------- | -------- | ------------------------------------ |
| `sources.yaml`         | Yes      | Where the data comes from            |
| `destinations.yaml`    | Yes      | Where the data goes                  |
| `pipeline.yaml`        | Yes      | Which source feeds which destination |
| `transformations.yaml` | No       | What happens to the data on the way  |
| `.env`                 | No       | Environment variables for this job   |

## A project folder

`hdrctl init` creates a full project:

In the bellow example a project called **myproject** defines a single job called **job1** 

![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\18.png)

| Path                      | Rule                                                                                         |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| `workflows/thread.yaml`   | Optional. Without it, every `workflows/*.yaml` runs one after another, in alphabetical order |
| `parameters.yaml`         | Values available everywhere as `{{ param:NAME }}`                                            |
| `environments/<env>.yaml` | Overrides the parameters for one environment, selected with `--env`                          |

## Example: a job inside a workflow

```yaml
# workflows/daily.yaml
version: "1.0"
workflow:
  name: daily
  description: Load the orders, then log a message
  trigger:
    type: manual
  steps:
    - name: load_orders # A job
      type: job
      job: ../jobs/job1

    - name: notify # An action
      type: action
      action: log
      params:
        message: "Orders loaded."
      depends_on: [load_orders]
```

- The step `load_orders` runs the job folder `jobs/job1`. The path is relative to the workflow file, which lives in `workflows/`: hence `../jobs/job1`.
- The step `notify` is an action. It runs only after `load_orders`, because of `depends_on`.

**A complete Job example on github:** [**The code**]([bejaouibechir.github.io/codes/01-basics/first_project at main · bejaouibechir/bejaouibechir.github.io · GitHub](https://github.com/bejaouibechir/bejaouibechir.github.io/tree/main/codes/01-basics/first_project))![](C:\Users\DELL\Desktop\Hydra\DSL-whitebook\images\01-basics\19.png)

## Running it

```bash
hdrctl run jobs/job1          # run one job alone
hdrctl run . --dry-run        # validate the whole project, run nothing
hdrctl run .                  # run every workflow, in the order of thread.yaml
hdrctl run . --env prod       # same, with environments/prod.yaml
```

> 

# 
