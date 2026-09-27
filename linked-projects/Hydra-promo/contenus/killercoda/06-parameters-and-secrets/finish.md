# Done

One job ran against two databases, on two ports, with two sets of credentials,
and produced two separate files — without a single edit between the runs.

What did the work:

- **`parameters.yaml`** declares what exists — name, type, default, description.
- **`environments/dev.yaml` and `environments/prod.yaml`** give the values per
  environment. Committed, reviewed, boring on purpose.
- **`{{ param:name }}`** reads one of those values, selected by
  `hdrctl run . --env <name>`.
- **`${ENV:NAME}`** reads a real environment variable, which you inject from
  outside — a secret manager, CI variables, or `set -a; . file; set +a` as here.
- **`secrets/` is in `.gitignore`.** That is not a detail, it is the point.

The habit worth keeping: **if a value would be fine in a pull request, make it a
parameter; if it would not, make it an environment variable.** The two syntaxes
look different so that an auditor can tell them apart without reading your mind.

One more thing the parameterised file name bought you: the prod run could not
overwrite the dev output. Parameterising *outputs* is as useful as
parameterising inputs.

**Next**

- Install it on your machine: `pip install hydra-etl`
- Docs and examples: [hydraetl.com](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=parameters-and-secrets)
- Source (AGPL-3.0): [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If something in this lab felt wrong or unclear, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that's the most useful thing you can do.
