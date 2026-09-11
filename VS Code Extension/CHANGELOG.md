# Changelog

## 0.1.3

- `pipeline.yaml` no longer reports a false error on files written by Hydra
  Studio. Studio adds `name` and `transformations` next to `from` and `to`; the
  engine ignores them, so flagging them was wrong. Both keys are now documented
  as Studio-only.
- `from` and `to` remain required.

## 0.1.2

- Display name corrected to **HYDRA ETL**, matching the wordmark used by the CLI
  banner and the rest of the product.
- Publisher corrected to **Bechir Bejaoui**. The identifier becomes
  `Bechir Bejaoui.hydra-etl`; quote it when passing it to a shell.
- Repository links removed. The homepage remains hydraetl.com.

## 0.1.1

- All user-facing text is now English: marketplace description, schema
  documentation, hover tooltips, completion explanations and snippet labels.
  Version 0.1.0 shipped some of them in French.
- No change to the schemas themselves or to the validation behaviour.

## 0.1.0 — first release

A purely declarative extension: no TypeScript, no build step.

- JSON schemas for the five manifests of the Hydra DSL: `sources.yaml`,
  `destinations.yaml`, `pipeline.yaml`, `transformations.yaml` and
  `workflow.yaml`.
- Context-aware key and value completion, hover documentation, and live
  structural validation.
- Conditional schemas: the `connection` keys offered depend on the value of
  `type`; `upsert` mode requires `key`; `trigger.type: schedule` requires
  `cron`; a `type: job` step requires `job`.
- 32 snippets covering the five manifests and all 18 transformation operations.
- YAML defaults: two-space indentation, suggestions kept active while filling in
  a snippet.

### Known limitations

- Validation is **structural** only. Cross-file consistency — does the `from` of
  `pipeline.yaml` match a declared source, does a step's `job` directory exist —
  is not checked. That is what `hdrctl validate` is for.
- Connector types supplied by plugins are not offered in the completion lists,
  though they are accepted without raising an error.
