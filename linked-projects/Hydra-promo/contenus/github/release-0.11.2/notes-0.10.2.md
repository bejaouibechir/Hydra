`pip install hydra-etl==0.10.2`

### Fixed

- `hdrctl validate --strict` now recognises the steps of a `transformations.yaml`
  written as `transformations: steps:`; it previously reported "none" on the
  manifests shipped in `examples/`.
- `hdrctl validate --strict` checks the syntax of `filter` and `calculate`
  expressions with pandas' own parser, without evaluating them. An invalid
  expression now fails validation (exit code 1) instead of failing at run time.

### Added

- `hdrctl workflow run` prints what a `python`, `bash` or `powershell` action
  wrote on stdout/stderr, under the corresponding step (capped at 20 lines).
  `StepResult` carries it in a new `output` field.

Full history: [CHANGELOG.md](https://github.com/bejaouibechir/Hydra/blob/main/CHANGELOG.md)
