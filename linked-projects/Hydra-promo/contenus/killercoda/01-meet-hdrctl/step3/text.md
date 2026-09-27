# Scaffold a full workflow

A workflow is several jobs chained together. `hdrctl workflow init` scaffolds all of it at once — the orchestration file and every job it references, each with real sample data:

`hdrctl workflow init mypipeline`{{exec}}

`find mypipeline -type f`{{exec}}

Two jobs (`job_a`, `job_b`) built exactly like `myjob` in the previous step — sources, destinations, pipeline, transformations, plus a `data/input.csv` this time — and one `workflow.yaml` that runs `job_a`, then `job_b`, then logs a message.

Open `mypipeline/workflow.yaml` in the **Editor** tab on the left and read it end to end before the next step — no command needed, just look.

When you are done, click **Check** to continue.
