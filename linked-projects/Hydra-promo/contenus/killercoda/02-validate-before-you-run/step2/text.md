# hdrctl validate: the job is not valid

`hdrctl validate brokenjob`{{exec}}

```
  ok  sources.yaml                         — Pydantic valid
  ok  destinations.yaml                    — Pydantic valid
  ok  transformations.yaml                 — Pydantic valid
  err pipeline.from='src_csv_typo' not found in sources.yaml
  ok  pipeline.to                          — resolved: dest_csv

  ❌ ... error(s) detected.
```

`validate` names the exact problem: this id, in this file, does not exist. It never executed anything to find that out — it only cross-checked `pipeline.yaml` against `sources.yaml`. Conclusion: `brokenjob` is not valid yet.

When you are done, click **Check** to continue.
