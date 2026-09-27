# Ask the API how it is doing

`curl -s http://127.0.0.1:5678/api/health | /opt/hydra/bin/python -m json.tool`{{exec}}

```json
{
    "message": "Hydra ETL API is running",
    "status": "ok",
    "version": "0.11.2",
    "dsl_version": "...",
    "studio": "disabled"
}
```

`"studio": "disabled"` is there because of `--no-studio` — the same field would say `"bundled"` or `"missing"` otherwise. No auth, no job path needed: this endpoint only reports on the server itself.

When you are done, click **Check** to continue.
