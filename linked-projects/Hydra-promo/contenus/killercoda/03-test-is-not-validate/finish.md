# Done

You now know the `test` → fix → `test` loop:

- `hdrctl test` checks sources, destinations and transformations section by section, and points at the broken field;
- once it says "All tests pass", the files are correct;
- it says so itself: the database connection is not tested, and `${ENV:...}` credentials are only resolved by `hdrctl run`.

**Next**

- Install it on your machine: `pip install hydra-etl`
- Docs and examples: [hydraetl.com](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=hdrctl-test)
- Source (AGPL-3.0): [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If something in this lab felt wrong or unclear, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that's the most useful thing you can do.
