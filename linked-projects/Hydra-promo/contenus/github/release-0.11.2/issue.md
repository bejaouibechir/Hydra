### What happened

Several mistakes in a `workflow.yaml` passed `hdrctl workflow validate` and were silently ignored at run time:

| Mistake | Before 0.11.2 |
|---|---|
| `action: powersheII` | step did nothing, run reported **success** |
| `depend_on: [fetch]` | key ignored, step ran **without its dependency** |
| `mesage:` under a `log` step | parameter dropped |
| `headers:` on a `webhook` step | offered by Studio, never sent |

For a tool whose promise is *validate before you run*, this is the worst kind of bug: a green run that did not do what the file says.

### Reproduce (0.11.1)

```yaml
workflow:
  name: repro
  steps:
    - name: a
      type: action
      action: bash
      params: { command: "exit 1" }
    - name: b
      type: action
      action: powersheII
      depend_on: [a]
```

`hdrctl workflow validate` → `Workflow valid`.

### Fix

Released in **0.11.2**. Validation now refuses unknown actions, unknown keys at every level, unknown action parameters and missing required ones, with a suggestion for the closest valid name. Tests keep the accepted parameters aligned with what the runner reads and what Studio offers.

Commits: c881e63, f71fc17, 796452a, 7c4a53e, 02e5ee6.
