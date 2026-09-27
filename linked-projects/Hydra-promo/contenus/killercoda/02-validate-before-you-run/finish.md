# Done

You now know the `validate` → fix → `validate` → `run` loop:

- `hdrctl validate` never touches a connector, only your YAML — and it names problems precisely (`pipeline.from='...' not found in sources.yaml`);
- a job it rejects, it will explain, not just refuse;
- once `validate` reports no errors, `run` is the command that actually executes and writes output.

That still leaves one question open: does `validate` (or `test`) ever check that your database credentials actually work? Next lab.

**Next**

- Install it on your machine: `pip install hydra-etl`
- Docs and examples: [hydraetl.com](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=validate-before-you-run)
- Source (AGPL-3.0): [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If something in this lab felt wrong or unclear, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that's the most useful thing you can do.
