# hdrctl vs hdrctl workflow

`hdrctl` has two command namespaces that look alike — `init`, `validate`, `list`, `run` exist at the root, and the same four verbs exist again under `hdrctl workflow`. They are not aliases of each other: the root commands operate on one job (one source, one destination, one pipeline); the `workflow` commands operate on a `workflow.yaml` that orchestrates several jobs as a DAG.

In this lab you will scaffold one of each side by side, then watch each `list` command find only its own kind — before running the workflow for real.

Hydra ETL installs in the background while you read this.
