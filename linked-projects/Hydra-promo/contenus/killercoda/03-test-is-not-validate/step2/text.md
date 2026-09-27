# hdrctl test shows the error

`hdrctl test dbjob`{{exec}}

```
  Sources
  ok  sources.yaml          — DSL valid
  ok  src_mysql             — mysql (connection not tested in test mode)

  Destinations
  err destinations.yaml : 1 validation error for DestinationsConfig
destinations.dest_mysql.load.mode
  Input should be 'append', 'replace' or 'upsert' [type=enum, input_value='upsret', ...]

  Transformations
  ok  transformations.yaml  — 2 step(s) valid

  ❌ Errors detected — fix before executing.
```

`test` checks each section on its own and points at the broken one: in `destinations.yaml`, the field `dest_mysql.load.mode` got `'upsret'`, and the only accepted values are `append`, `replace` or `upsert`. Conclusion: `dbjob` is not ready to run.

When you are done, click **Check** to continue.
