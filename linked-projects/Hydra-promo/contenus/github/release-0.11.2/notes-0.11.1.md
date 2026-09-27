`pip install hydra-etl==0.11.1`

### Added

- Hydra Studio offers SQL Server as a source and as a destination. The engine
  had the connector since 0.11.0, but the visual editor gave no way to pick it,
  so a SQL Server pipeline could not be built there at all.

  The form carries `host`, `instance`, `port`, `database`, `schema`, `user` and
  `password`, then table or query as a source, table and mode as a destination.

  The port is deliberately not defaulted to 1433 the way MySQL and PostgreSQL
  default to 3306 and 5432. An explicit port short-circuits the SQL Browser
  lookup, so writing one by default would make named instances unreachable from
  Studio — that is, SQL Express, whose instance is named by construction. The
  field label says so: leave it empty for a named instance.

  Proven end to end: a SQL Server source resolved through SQL Browser, no port
  given, loading into a CSV destination.

Full history: [CHANGELOG.md](https://github.com/bejaouibechir/Hydra/blob/main/CHANGELOG.md)
