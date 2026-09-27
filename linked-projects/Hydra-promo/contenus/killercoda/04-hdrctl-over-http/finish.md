# Done

You now know:

- `hdrctl serve --no-studio` gives you the REST API alone, no UI;
- `/api/health` is unauthenticated and only reports on the server process;
- `/api/jobs/validate`, `/run`, `/test`, `/list`, `/init` (and their `workflow/*` equivalents) are thin wrappers around the same `hdrctl` binary — the JSON `stdout` field is the CLI's real output, `returncode` is its real exit code.

If you already trust `hdrctl`'s output for a job, you can trust this API's output for the same job — it is the same process underneath.

**Next**

- Install it on your machine: `pip install "hydra-etl[server]"`
- Docs and examples: [hydraetl.com](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=hdrctl-over-http)
- Source (AGPL-3.0): [github.com/bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra)

Hydra ETL is a beta, built by one maintainer. If something in this lab felt wrong or unclear, [open an issue](https://github.com/bejaouibechir/Hydra/issues) — that's the most useful thing you can do.
