# What `hdrctl validate` checks

`hdrctl validate JOB` inspects the job manifests without connecting to a source or
destination and without running the pipeline. A successful validation is not a
guarantee that a later run will succeed.

## Checked before a run

- `pipeline.yaml`, `sources.yaml`, and `destinations.yaml` must exist. An absent
  `transformations.yaml` is allowed.
- YAML syntax and the manifest structure supported by Hydra's source,
  destination, and transformation parsers are checked.
- `pipeline.from` must name a configured source, and `pipeline.to` must name a
  configured destination.
- With `--strict`, Hydra performs the additional checks implemented for strict
  validation. This option does not connect to external systems or evaluate
  transformation expressions against data.

For example, validate a job before executing it:

```bash
hdrctl validate my_job && hdrctl run my_job
```

## Only knowable at run time

Validation cannot establish that configured services are reachable, credentials
are valid, or that the remote user has the required permissions. It also cannot
check the actual input data for missing columns, incompatible values, encoding
problems, or database constraints without reading or writing that data. Use
`hdrctl test` to test supported connections; a successful connection test still
does not guarantee that a particular dataset or write will succeed.

If validation passes but execution fails, inspect the run-time error and the
relevant connector or transformation configuration.
