# Break it — the API fails exactly like the CLI

Same typo trick as before:

`sed -i 's/from: src_csv/from: src_csv_typo/' apijob/pipeline.yaml`{{exec}}

`curl -s -X POST http://127.0.0.1:5678/api/jobs/validate -H "Content-Type: application/json" -d '{"path": "apijob"}' | /opt/hydra/bin/python -m json.tool`{{exec}}

```json
{
    "returncode": 1,
    "stdout": "...pipeline.from='src_csv_typo' not found in sources.yaml...",
    "success": false
}
```

The HTTP call itself still returns `200 OK` — the failure lives inside the JSON body, exactly like it lives inside the CLI's exit code and stdout. A tool calling this API gets the identical error text a person reading a terminal would get.

When you are done, click **Check** to continue.
