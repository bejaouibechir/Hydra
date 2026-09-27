# One job, two environments

Every ETL job eventually faces the same question: **how do you run the same
pipeline against dev and against prod, without maintaining two copies of it?**

The wrong answers are familiar. Copy the job folder and change the host. Comment
out three lines before deploying. Keep a password in a YAML file and hope nobody
reads the repository.

Hydra splits the problem in two, because the two halves have opposite rules:

| | **Parameters** | **Secrets** |
|---|---|---|
| Examples | host, port, database name, labels | user, password, API key |
| Where they live | `environments/dev.yaml`, `environments/prod.yaml` | environment variables |
| In version control? | **Yes** — they get reviewed in pull requests | **Never** |
| Syntax in YAML | `{{ param:mysql_port }}` | `${ENV:MYSQL_PASSWORD}` |
| Selected by | `hdrctl run . --env dev` | the shell, before the run |

The two syntaxes look different on purpose. When you open a manifest, you can
tell at a glance which values are safe to read in a code review and which ones
are never written down.

## What you will do

Two MySQL databases are starting in the background right now, on two different
ports, with different credentials and different data. You will write **one** job,
run it twice, and get two different output files — changing nothing between the
runs but a single flag.

