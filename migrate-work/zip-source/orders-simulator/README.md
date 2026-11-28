# Orders comparison fixture

This small Hydra ETL job is the runnable companion to the browser simulator on
the Migrate pages. It reads 14 CSV orders, casts `amount`, filters rows above
50, sums by `status`, sorts by total and writes `data/by_status.csv`.

```powershell
hdrctl validate . --strict
hdrctl run .
```

Expected totals: `paid=1284`, `pending=605`, `refunded=378`.

The ZIP contains four Hydra DSL files and the input CSV. The browser simulator
models these operations locally; it does not call `hdrctl`.
