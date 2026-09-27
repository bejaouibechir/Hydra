# Write the order down

Here is the same job as a Hydra ETL workflow. The scripts do not change; only the order is now **declared** instead of guessed:

```
cat > workflow.yaml <<'YAML'
workflow:
  name: nightly-orders
  steps:
    - name: fetch
      type: action
      action: bash
      params:
        command: /root/nightly/scripts/fetch.sh

    - name: clean
      type: action
      action: bash
      depends_on: [fetch]
      params:
        command: /root/nightly/scripts/clean.sh

    - name: backup
      type: action
      action: bash
      depends_on: [fetch]
      params:
        command: /root/nightly/scripts/backup.sh

    - name: report
      type: action
      action: bash
      depends_on: [clean]
      params:
        command: /root/nightly/scripts/report.sh
YAML
```{{exec}}

`clean` and `backup` both depend on `fetch` and nothing else, so they run **in parallel**. `report` waits for `clean`.

Check the file without running anything:

`hdrctl workflow validate workflow.yaml`{{exec}}

Now run it. The file is still missing, like last night:

`hdrctl workflow run workflow.yaml; echo "exit code: $?"`{{exec}}

`fetch` fails, the three steps that depend on it are **skipped**, and the exit code is `1`. Nothing ran on stale data.

Now the delivery arrives. Run again:

`cp samples/orders.csv incoming/ && hdrctl workflow run workflow.yaml`{{exec}}

Four green steps, and the report counts **5** orders: the 7 delivered, minus 2 with no amount.
