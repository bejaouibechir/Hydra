# Scaffold a job and a workflow

A plain job — one source, one destination:

`hdrctl init solojob --template csv`{{exec}}

A full workflow project — a `workflow.yaml` that chains two jobs plus a notify step, each job scaffolded with its own real sample data:

`hdrctl workflow init mypipeline`{{exec}}

`find mypipeline -type f`{{exec}}

`cat mypipeline/workflow.yaml`{{exec}}

`mypipeline/jobs/job_a` and `mypipeline/jobs/job_b` are ordinary jobs underneath — same `sources.yaml`/`destinations.yaml`/`pipeline.yaml`/`data/input.csv` shape as `solojob`. The only new thing is `workflow.yaml`, which says `job_a` runs, then `job_b` (`depends_on: ["job_a"]`), then a `log` action.

When you are done, click **Check** to continue.
