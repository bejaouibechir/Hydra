# Validate before you run

`hdrctl validate` never touches a connector, it only cross-checks your YAML against itself — and it names problems precisely. In this lab you will follow the workflow it exists for:

1. Create a job, then break a source reference in it.
2. Run `hdrctl validate` — it tells you the job is not valid, and exactly why.
3. Fix the job.
4. Run `hdrctl validate` again — it tells you the job is valid.
5. Only now run `hdrctl run` — and see it actually execute.

Hydra ETL installs in the background while you read this.
