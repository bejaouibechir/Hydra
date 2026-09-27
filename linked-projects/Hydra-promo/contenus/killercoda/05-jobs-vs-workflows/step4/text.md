# Validate and run the workflow

First, check the manifest:

`hdrctl workflow validate mypipeline/workflow.yaml`{{exec}}

```
✅ Workflow valid — no errors detected.
```

The scaffolded jobs come with a placeholder filter (`expr: "1 == 1"   # Remplacer par votre logique`) that you are meant to replace with real logic:

`cat mypipeline/jobs/job_a/transformations.yaml`{{exec}}

Give both jobs a real transformation — cast `value` to a number, keep rows above 6:

```
for j in job_a job_b; do cat > mypipeline/jobs/$j/transformations.yaml << 'YAML'
version: "1.0"
transformations:
  steps:
    - cast:
        mapping:
          value: float
    - filter:
        expr: "value > 6"
YAML
done
```{{exec}}

Now run the whole workflow:

`hdrctl workflow run mypipeline/workflow.yaml`{{exec}}

```
  ✓  Step 'job_a' OK (0.2s)
  ✓  Step 'job_b' OK (0.0s)
  ✓  Step 'notify' OK (0.0s)
  ✅ Workflow 'mypipeline' completed in 0.2s — 3/3 steps OK
```

Each step ran through the same executor a plain `hdrctl run` uses — `job_b` only started because `job_a` succeeded first (`depends_on: ["job_a"]`). Check the results:

`cat mypipeline/jobs/job_a/data/output.csv`{{exec}}

`cat mypipeline/jobs/job_b/data/output.csv`{{exec}}

`item_c` (value `5.75`) was filtered out of both.

When you are done, click **Check** to finish.
