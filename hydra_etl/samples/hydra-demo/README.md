# Hydra demo

A ready-to-run Hydra ETL project. Every input file is already in place: open a job
in Hydra Studio and press **Run**, or use the command line.

| Job | Reads | Writes |
|---|---|---|
| `clean-orders` | `Data/orders_raw.csv` | `outputs/orders_clean.csv` |
| `customers-json-to-csv` | `Data/customers.json` | `outputs/active_customers.csv` |
| `revenue-by-product` | `Data/orders_raw.csv` | `outputs/revenue_by_product.csv` |

The `first-pipeline` workflow (in `workflows/`) runs the three jobs, and
`workflows/thread.yaml` lists it, so `hdrctl run .` (or **Run project** in Studio)
runs the whole project.

```bash
hdrctl run .                          # the whole project
hdrctl workflow run first-pipeline    # one workflow
hdrctl run jobs/clean-orders          # one job
```

`orders_raw.csv` is deliberately untidy (padded values, lowercase ids, duplicate
rows, zero or negative quantities) so that the cleaning steps have something to do.
Results are written to `outputs/`; they are recreated on every run.

The file paths in `sources.yaml` and `destinations.yaml` point at this folder. If you
move the project, update them.
