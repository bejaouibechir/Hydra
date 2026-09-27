`pip install hydra-etl==0.10.3`

### Changed

- The MCP server now speaks English. The instructions of the server and the
  descriptions and annotation titles of its 17 tools were in French; they are
  what an AI client reads to decide which tool to call, and what MCP
  registries publish.
- `serverInfo` reported an empty version. It now carries the package version,
  and adds a title and the website URL when the installed MCP SDK accepts
  them. The server name is `hydra-etl`, matching the package.
- `hydra-mcp --help` is in English.

Full history: [CHANGELOG.md](https://github.com/bejaouibechir/Hydra/blob/main/CHANGELOG.md)
