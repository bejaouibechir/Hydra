# Let hdrctl list check your reading

Before running anything, list what hdrctl itself sees in this folder:

`hdrctl list`{{exec}}

Only `myjob` shows up — not `mypipeline`. `hdrctl list` looks for job folders: a `sources.yaml`, `destinations.yaml` and `pipeline.yaml` sitting together. `mypipeline` is a workflow project — its jobs are one level deeper, inside `mypipeline/jobs/`. That distinction, a job versus a workflow, and which commands see which, is exactly what the `hdrctl workflow` lab is about.

List the jobs a workflow actually contains, with `hdrctl workflow list` this time:

`hdrctl workflow list mypipeline`{{exec}}

Compare what it prints to what you read in the Editor — same two jobs, same order.

Click **Check** to finish.
