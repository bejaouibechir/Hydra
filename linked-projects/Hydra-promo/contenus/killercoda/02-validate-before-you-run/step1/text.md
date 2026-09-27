# Create an invalid job

Scaffold a job from the `csv` template — the only built-in template that ships with real sample data, so it can actually run once it is fixed:

`hdrctl init brokenjob --template csv`{{exec}}

`cat brokenjob/pipeline.yaml`{{exec}}

`pipeline.yaml` says which source feeds which destination:

```yaml
pipeline:
  from: src_csv
  to: dest_csv
```

Now break it — a realistic typo, the kind you get from renaming a source and missing one reference:

`sed -i 's/from: src_csv/from: src_csv_typo/' brokenjob/pipeline.yaml`{{exec}}

`cat brokenjob/pipeline.yaml`{{exec}}

`brokenjob` now points `pipeline.from` at a source, `src_csv_typo`, that does not exist in `sources.yaml`.

When you are done, click **Check** to continue.
