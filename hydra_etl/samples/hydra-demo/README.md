# Hydra demo

A ready-to-run Hydra ETL project. Every input file is already in place: open a job
in Hydra Studio and press **Run**, or use the command line.

| Job | Reads | Writes |
|---|---|---|
| `clean-orders` | `Data/orders_raw.csv` | `output/orders_clean.csv` |
| `customers-json-to-csv` | `Data/customers.json` | `output/active_customers.csv` |
| `revenue-by-product` | `Data/orders_raw.csv` | `output/revenue_by_product.csv` |

The `first-pipeline` workflow (in `workflows/`) runs the three jobs.

```bash
hdrctl workflow run workflows/first-pipeline.yaml
hdrctl run jobs/clean-orders
```

`orders_raw.csv` is deliberately untidy (padded values, lowercase ids, duplicate
rows, zero or negative quantities) so that the cleaning steps have something to do.
Results are written to `output/`; they are recreated on every run.

The file paths in `sources.yaml` and `destinations.yaml` point at this folder. If you
move the project, update them.
