`pip install hydra-etl==0.11.0`

### Added

- Microsoft SQL Server connector, aliases `sqlserver` and `mssql`. Extract with
  a table or a query, load in `append`, `replace` or `upsert` mode, with
  auto-creation of the target table. Install it with
  `pip install "hydra-etl[mssql]"`.

  The driver is `pymssql`, which ships FreeTDS inside its wheels, rather than
  `pyodbc`, which needs the `msodbcsql` system driver installed separately.
  One command, nothing to deploy.

  Upsert runs `UPDATE` then `INSERT ... WHERE NOT EXISTS` inside a
  transaction. `MERGE` is deliberately not used: its concurrency problems are
  documented and many SQL Server teams ban it outright.

  Auto-created tables use `NVARCHAR` rather than `VARCHAR` and `DATETIME2`
  rather than `DATETIME`, so accented text and timestamps behave identically
  whatever the server's collation.

  A named instance is resolved by Hydra itself. `pymssql` embeds FreeTDS,
  which unlike the Microsoft drivers never queries the SQL Browser service, so
  `MACHINE\\SQLEXPRESS` would reach port 1433 and fail — the default setup of
  SQL Express, that is, of the audience this connector targets. Hydra sends
  the SSRP datagram itself over UDP 1434 and connects on the port it gets
  back. An explicit port short-circuits the lookup; a silent SQL Browser falls
  back to an error message that says which of the two to fix.

  Tested end to end against two live servers: SQL Server 2022 on Windows with
  a named instance on a static TCP port, and
  `mcr.microsoft.com/mssql/server:2022-latest` in Docker on Linux. Same major
  version on both, so the operating system was the only variable. 74 unit
  tests need no server; 11 end-to-end tests are skipped unless
  `HYDRA_E2E_MSSQL` is set.

### Known limitation

- Azure AD authentication and Always Encrypted are out of reach with
  `pymssql`. They need `pyodbc` and the `msodbcsql` system driver, which will
  be added as an option the day a user asks for it.

Full history: [CHANGELOG.md](https://github.com/bejaouibechir/Hydra/blob/main/CHANGELOG.md)
