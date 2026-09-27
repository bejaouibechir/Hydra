# Try Hydra ETL in your browser

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/bejaouibechir/hydra-demo)

One click. No install, no Python setup, no database to configure.

## Start here

Once the editor has opened, type this in the terminal at the bottom:

```bash
./tour
```

It walks you through the whole thing in about five minutes — showing you each
command before running it, so you can see what is happening. You do not have to
write anything.

If you would rather explore on your own, the rest of this page explains what is
in front of you.

## What is in this repository

```
tour                         the guided walkthrough (start here)
data/orders.csv              200 sample orders
db/init.sql                  the table MySQL creates on first start
docker-compose.yml           your dev container and the MySQL one beside it
parameters.yaml              what can vary between environments
environments/dev.yaml        values for dev
environments/prod.yaml       values for prod
jobs/load-orders/            CSV  ->  MySQL
jobs/export-report/          MySQL ->  CSV, filtered and sorted
scripts/summarise.py         a plain Python script, called by the workflow
workflows/nightly-report.yaml  the five steps that tie it all together
```

## Three things to try, in order

### 1. Run the whole workflow

```bash
hdrctl workflow run workflows/nightly-report.yaml
```

Five steps run in dependency order:

| Step | What it is |
|---|---|
| `announce` | a **Bash action** — any shell command, inside the pipeline |
| `load-orders` | a **job**: CSV into MySQL, with a retry policy |
| `export-report` | a **job**: MySQL back out to CSV, filtered by a parameter |
| `summarise` | a **Python action** — your own script, run as a step |
| `list-output` | a Bash action that cannot fail the run (`on_failure: continue`) |

The summary line at the end is computed by `scripts/summarise.py`. Open it: it
is ordinary Python, with no Hydra import. That is the point — actions run your
existing scripts, they do not ask you to rewrite them.

### 2. Open Hydra Studio and look at the same pipeline

```bash
hdrctl serve --port 5678
```

A browser tab opens on the Studio. The jobs you just ran are there as boxes you
can drag, connect and configure — and what you save is the same YAML you have in
this repository. The visual editor and the files are two views of one thing,
not an export.

### 3. Change one value, run again

`environments/dev.yaml` keeps `min_amount: 500`; `environments/prod.yaml` sets
`2000`. Run the report against each:

```bash
hdrctl run jobs/export-report --env dev
hdrctl run jobs/export-report --env prod
```

Two different files in `output/`, from one job you never edited. That is
`{{ param:min_amount }}` doing the work.

## Where the credentials come from

The manifests read `${SECRET:mysql.user}` and `${SECRET:mysql.password}`. Hydra
looks those up in the environment — here the devcontainer sets them for you, and
in production they come from your CI variables or a secret manager. Nothing
sensitive is written in a manifest, so the whole repository is safe to review.

## The two containers

Your Codespace is itself a container, and MySQL runs in a second one beside it.
They share a private network, which is why `parameters.yaml` says the host is
simply `mysql` — the service name from `docker-compose.yml`. Prove it:

```bash
getent hosts mysql
```

An IP comes back: that name only resolves because the two containers are on the
same network. Nothing was installed on your machine, and no port had to be
guessed.

Port **3307** is also forwarded to your browser, so you can point a database
client at it from outside if you want to look at the data yourself.

To talk to your own database instead, change two values in `parameters.yaml` —
or override them for a single run without editing anything:

```bash
hdrctl run jobs/export-report --env dev -P mysql_host=db.example.com -P mysql_port=3306
```

## Running it locally instead

Start just the database, then point the pipeline at it through the forwarded
port:

```bash
docker compose up -d mysql
pip install "hydra-etl[server]>=0.11.3" mysql-connector-python
export MYSQL_USER=hydra MYSQL_PASSWORD=hydra-demo-password
hdrctl workflow run workflows/nightly-report.yaml -P mysql_host=127.0.0.1 -P mysql_port=3307
```

## Next

- Documentation and examples: [hydraetl.com](https://hydraetl.com/?utm_source=github&utm_medium=demo&utm_campaign=codespaces)
- Hands-on labs in the browser: [killercoda.com/hydra-etl](https://killercoda.com/hydra-etl)
- Source, AGPL-3.0: [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If anything here does not work as
described, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that
is the most useful thing you can do.
