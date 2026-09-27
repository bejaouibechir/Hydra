## Hydra ETL 0.11.2 — validation no longer lets mistakes through

`pip install -U hydra-etl`

This release fixes a class of bugs that contradicted the core promise of Hydra ETL: **validate before you run**. Several mistakes in a `workflow.yaml` were silently ignored, and the run could report success for work that never happened.

### Fixed

- **Unknown actions are rejected.** A typo such as `action: powersheII` used to make the step do nothing while the run reported success. `hdrctl workflow validate` now fails and suggests the closest action (`did you mean 'powershell'?`), and `hdrctl workflow run` refuses to start.
- **Unknown keys are rejected at every level.** `depend_on: [fetch]` (instead of `depends_on`) used to validate, and the step ran *without its dependency*. Unknown keys at the top level, under `workflow`, in steps, `trigger` and `retry` are now refused with a suggestion.
- **Action parameters are checked.** Unknown parameters (`mesage:` under `log`) and missing required ones (`command` for `bash`, `url` for `webhook`, `script` or `file_path` for `python`…) are reported by `validate`, not at 2 a.m.
- **`webhook` sends `headers`.** Studio offered the field but the runner ignored it, so an `Authorization` header was never sent. A text `body` is now sent as written.
- **`hdrctl workflow run` output:** no Python traceback on an invalid file, steps that never ran after a failure are listed as skipped, and validation errors are printed one per line.

### Behaviour change

A workflow that relied on a misspelled or misplaced key being ignored now **fails validation**. The error names the key to fix or remove:

```
❌ Invalid workflow:
  - steps.1: Step 'b': unknown key 'depend_on' — did you mean 'depends_on'?
```

Full details: [CHANGELOG.md](https://github.com/bejaouibechir/Hydra/blob/main/CHANGELOG.md#0112--2026-09-26)
