# hydra

Hydra ETL project created with `hdrctl init`.

## Structure

| Path | Purpose |
|---|---|
| `.hydra/` | Project marker, Hydra Studio data, and `secrets` (git-ignored, see below) |
| `Data/` | Input data shared by the jobs |
| `environments/` | Parameter values per environment (`dev.yaml`, `prod.yaml`, ...) |
| `jobs/` | One folder per job: `sources.yaml`, `destinations.yaml`, `pipeline.yaml`, `transformations.yaml` |
| `outputs/` | Files produced by the jobs |
| `parameters.yaml` | Project parameters, used as `{{ param:NAME }}` |
| `scripts/` | Scripts called by workflow actions (python, bash, powershell) |
| `workflows/` | Workflows (`<name>.yaml`) and their execution order (`thread.yaml`) |

## Secrets

Put passwords and tokens in `.hydra/secrets`, one `name=value` per line, and use them as
`${SECRET:name}` in jobs and workflows. The file is listed in `.gitignore`. An environment variable
wins over it (`${SECRET:db.password}` first reads `DB_PASSWORD`), so CI or a vault can provide the
values without the file. To keep the file elsewhere: `HYDRA_SECRETS_FILE=<path>` or
`hdrctl run . --secrets-file <path>`.

## Commands

Run them from this folder.

```bash
hdrctl run . --dry-run        # validate the whole project, run nothing
hdrctl run .                  # run every workflow, in the order of workflows/thread.yaml
hdrctl run . --env prod       # same, with environments/prod.yaml
hdrctl run jobs/job1          # run one job alone
hdrctl workflow list          # workflows in thread order
hdrctl workflow add <name>    # new workflow, added at the end of workflows/thread.yaml
hdrctl workflow remove <name> # delete a workflow (its jobs are kept)
hdrctl job add <job> <workflow>       # new job, appended to a workflow
hdrctl job attach <job> <workflow> -p 1  # existing job, as the first step
hdrctl job detach <job> [<workflow>]  # take a job out of one workflow, or of all
hdrctl job list               # jobs, and the workflows that use them
```
