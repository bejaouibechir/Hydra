# Done

You now know:

- root commands (`init`, `validate`, `test`, `run`, `list`) act on one job;
- `workflow` commands (`init`, `validate`, `run`, `list`) act on a `workflow.yaml` DAG of jobs;
- `hdrctl list` looks one level deep for job directories and never recurses into `jobs/`;
- `hdrctl workflow list` recurses for `workflow.yaml` files and ignores plain job directories;
- a workflow step still runs through the same executor a plain `hdrctl run` uses — `depends_on` just sequences the calls.

That closes the CLI-discovery series: install and flags, validate vs. run, test vs. validate, the API, and now jobs vs. workflows.

**Next**

- Install it on your machine: `pip install hydra-etl`
- Docs and examples: [hydraetl.com](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=jobs-vs-workflows)
- Source (AGPL-3.0): [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If something in this lab felt wrong or unclear, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that's the most useful thing you can do.
