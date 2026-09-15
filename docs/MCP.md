# Hydra MCP server

Connect Hydra to your AI assistant. Ask for a pipeline in plain language — your
assistant writes the manifests, **Hydra validates them**, and nothing runs until
you say so.

```
you → your assistant → Hydra MCP server → hdrctl validate → your job folder
```

The server holds no model and makes no network call. MCP is a protocol: the
tools are here, the intelligence is whichever assistant you already use.

## Install

```bash
pip install "hydra-etl[mcp]"
```

## Connect it

Point your client at `hydra-mcp` and set `HYDRA_MCP_WORKSPACE` to the folder
holding your jobs. The server never reads or writes outside it.

### Claude Desktop

`claude_desktop_config.json` — Settings → Developer → Edit Config.

```json
{
  "mcpServers": {
    "hydra": {
      "command": "hydra-mcp",
      "env": { "HYDRA_MCP_WORKSPACE": "/absolute/path/to/your/jobs" }
    }
  }
}
```

### Cursor

`.cursor/mcp.json` in your project, or the global one in `~/.cursor/`.

```json
{
  "mcpServers": {
    "hydra": {
      "command": "hydra-mcp",
      "env": { "HYDRA_MCP_WORKSPACE": "${workspaceFolder}" }
    }
  }
}
```

### VS Code

`.vscode/mcp.json`.

```json
{
  "servers": {
    "hydra": {
      "type": "stdio",
      "command": "hydra-mcp",
      "env": { "HYDRA_MCP_WORKSPACE": "${workspaceFolder}" }
    }
  }
}
```

### Windows

If `hydra-mcp` is not on your `PATH`, call the module instead:

```json
{
  "mcpServers": {
    "hydra": {
      "command": "py",
      "args": ["-m", "hydra_etl.mcp"],
      "env": { "HYDRA_MCP_WORKSPACE": "C:\\Users\\you\\jobs" }
    }
  }
}
```

### Any other MCP client

Transport `stdio`, command `hydra-mcp`. That is all it needs.

## Tools

| Tool | What it does |
|---|---|
| `hydra_list_operations` | the 18 transformations and their required keys |
| `hydra_describe_operation` | the full JSON schema of one operation |
| `hydra_list_connectors` | the 9 connector types accepted by `type` |
| `hydra_list_actions` | the workflow actions |
| `hydra_list_jobs` | jobs found in the workspace |
| `hydra_read_job` | read a job's manifests |
| `hydra_validate_job` | run the official validator |
| `hydra_write_job` | write a job — **validated first** |
| `hydra_run_job` | execute a job |
| `hydra_explain_error` | turn a validation error into a fix |

The DSL tools read the specification generated from the engine's own code
(`tools/spec_export.py`), so they never drift from what Hydra actually accepts.

## Two guarantees

**Nothing invalid is ever written.** `hydra_write_job` validates in a temporary
folder and writes only on success. A rejected job leaves no trace — not even an
empty directory — and the assistant is handed the exact error so it can fix it:

```
REFUSED — nothing was written. The validator reports:
- pipeline.from='inexistant' not found in sources.yaml
```

**Nothing outside the workspace is ever touched.** Absolute paths, `..`
segments and symlinks leading out are refused, identically on Windows, macOS
and Linux.

Both are covered by tests (`tests/test_mcp_server.py`).

## Try it without an assistant

```bash
npx @modelcontextprotocol/inspector hydra-mcp
```

MCP Inspector lists the tools and calls them by hand — the quickest way to see
what your assistant will see.

## What it does not do

Generating a pipeline is your assistant's job, not the server's. The server
describes the DSL, validates, and executes. That separation is deliberate:
validation is deterministic and can be trusted; generation is not, which is
why it never writes unchecked.
