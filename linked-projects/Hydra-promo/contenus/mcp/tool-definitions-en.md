# Hydra ETL MCP server — English tool definitions (v0.10.3 candidate)

Captured live from the running server on 2026-09-21.

## serverInfo

```json
{
  "name": "hydra-etl",
  "title": "Hydra ETL",
  "version": "0.10.2",
  "websiteUrl": "https://hydraetl.com"
}
```

## Server instructions

> Hydra ETL is a declarative ETL engine. A job is a folder holding four YAML manifests: sources.yaml, transformations.yaml (optional), destinations.yaml and pipeline.yaml.

> Recommended method: call hydra_list_operations and hydra_list_connectors first to learn the exact vocabulary, then write the job with hydra_write_job — it validates before writing and hands back the errors if anything is wrong. Never run a job unless the user asked for it.

> Never invent a connector, an operation or an action: if it is not in the lists, it does not exist.

## Tools (17)

### `hydra_list_operations`  —  *Read-only*

List the 18 transformation operations of Hydra ETL with their required parameters. Call this BEFORE writing a transformations.yaml: any operation missing from this list does not exist and will be rejected.

### `hydra_describe_operation`  —  *Read-only*

Return the full JSON schema of one transformation operation: every parameter, its type and its default value. Call this when hydra_list_operations is not enough.

### `hydra_list_connectors`  —  *Read-only*

List the connector types accepted by the 'type' key of a source or a destination. Any other type fails at run time: S3, BigQuery and Snowflake are not supported.

### `hydra_list_actions`  —  *Read-only*

List the actions usable in a workflow step of type 'action'. Careful: an unknown action is silently ignored at run time and the step is still counted as successful, so check the name before writing it.

### `hydra_list_jobs`  —  *Read-only*

List the Hydra ETL jobs present in the workspace. A job is a folder holding a pipeline.yaml. Returns relative paths, usable as they are in the other tools.

### `hydra_read_job`  —  *Read-only*

Read the manifests of an existing job. Call this before modifying a job, so you start from its real content instead of rewriting it from memory.

### `hydra_validate_job`  —  *Read-only*

Validate a job with the official Hydra ETL validator: the structure of the four manifests, and the resolution of pipeline.from to a declared source and of pipeline.to to a declared destination. This is the ground truth — if this tool refuses, the job will not run.

### `hydra_write_job`  —  *Writes files, after validation*

Write the manifests of a job, AFTER validation. Each manifest is passed as YAML text. If validation fails, nothing is written and the errors are returned: fix them and call the tool again. Writing does not run the job.

### `hydra_run_job`  —  *Runs the pipeline — writes real data*

Run a Hydra ETL job and return the execution log. Only call this tool if the user explicitly asked for the run: it writes real data to the destination.

### `hydra_explain_error`  —  *Read-only*

Explain a Hydra ETL validation error in plain language and propose the fix. Use this when hydra_validate_job or hydra_write_job returns a message you cannot interpret.

### `hydra_list_workflows`  —  *Read-only*

List the workflows in the workspace. A workflow orchestrates several jobs: dependencies, parallel execution, retries, cron triggering. Use this as soon as the request chains several jobs.

### `hydra_read_workflow`  —  *Read-only*

Read an existing workflow.yaml file and return its raw YAML. Call this before modifying a workflow, so you start from its real content instead of rewriting it from memory.

### `hydra_write_workflow`  —  *Writes files, after validation*

Write a workflow, AFTER validation. A step is either type='job' with the path of a job folder, or type='action'. `depends_on` is ALWAYS a list: steps with no dependency in common run in parallel. If validation fails, nothing is written.

### `hydra_run_workflow`  —  *Runs the pipeline — writes real data*

Run a workflow and return the trace, step by step. Only call this tool if the user asked for the run: the jobs it contains write real data to their destinations.

### `hydra_preview_data`  —  *Read-only*

Show the columns and the first rows of a data file (CSV, JSON, Parquet). Call this BEFORE writing a job, to learn the real column names instead of guessing them — and AFTER a run, to check the result.

### `hydra_check_job`  —  *Read-only*

Check that a job does what the user actually asked for. This completes hydra_validate_job: that one says whether the YAML is correct, this one whether the job answers the request. Twelve deterministic rules: operation requested but missing, numeric comparison without a `cast`, load mode contradicted, inconsistent file extension, plaintext secret, unsupported technology. Call this AFTER writing a job, before presenting it.

### `hydra_find_example`  —  *Read-only*

Find, among real Hydra ETL jobs, the ones closest to the request, and return their manifests. Call this BEFORE writing an unusual job: an example that runs beats a reconstruction from memory.
