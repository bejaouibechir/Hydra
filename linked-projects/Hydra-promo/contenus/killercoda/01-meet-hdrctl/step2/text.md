# Scaffold a job

`hdrctl init` creates a job from a template — sources, destinations, pipeline, and (optionally) transformations, all in YAML:

`hdrctl init myjob`{{exec}}

Look at what it created:

`find myjob -type f`{{exec}}

Notice its own suggestion at the bottom: it tells you to run `hydra test myjob` next, not `validate`. Keep that in mind — the difference between the two is the whole subject of a later lab.

Read one of the files:

`cat myjob/pipeline.yaml`{{exec}}

`pipeline.from: src_input` and `pipeline.to: dest_output` are the two IDs declared in `sources.yaml` and `destinations.yaml` — that's the whole wiring of a job.

When you are done, click **Check** to continue.
