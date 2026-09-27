# hdrctl list only sees the job

`hdrctl list`{{exec}}

Only `solojob` shows up. `hdrctl list` looks one level deep for folders that directly contain `sources.yaml` + `destinations.yaml` + `pipeline.yaml` — it does not recurse. `mypipeline/` fails that check (it holds `workflow.yaml`, not a pipeline of its own), and `mypipeline/jobs/job_a` and `job_b` — which *would* pass the check — are never looked at, because `hdrctl list` never opens `mypipeline/jobs/` in the first place.

When you are done, click **Check** to continue.
