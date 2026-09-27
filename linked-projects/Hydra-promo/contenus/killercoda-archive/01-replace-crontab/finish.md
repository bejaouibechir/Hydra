# Done

You replaced four time-guessing cron lines with one declared workflow:

- steps run in dependency order, in parallel when they can;
- a failure stops what depends on it instead of feeding it stale data;
- a transient error is retried by declaration;
- a typo is refused before anything runs.

The same `workflow.yaml` also accepts `python`, `ssh`, `webhook`, `email`, `condition` and data jobs that read and write CSV, Parquet, PostgreSQL, MySQL, SQL Server or MongoDB.

**Next**

- Install it on your machine: `pip install hydra-etl`
- Docs and examples: [hydraetl.com](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=replace-crontab)
- Source (AGPL-3.0): [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If something in this lab felt wrong or unclear, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that is the most useful thing you can do.
