### Fixed

- **`mode: upsert` now works on PostgreSQL.** Until this release every PostgreSQL destination using
  upsert failed with `KeyError: 0`, whatever the target table, even when a PRIMARY KEY existed on
  exactly the columns listed in `key` — the mode was effectively unusable.

  Two defects in the pre-flight constraint check were at fault. `array_agg` over
  `information_schema.key_column_usage.column_name` (type `sql_identifier`) is returned by
  psycopg2 as the raw text `{col}` rather than a list, so the comparison matched characters instead
  of column names; and the `RealDictCursor` row was unpacked as a tuple, which bound the dict keys
  and made the error branch raise `KeyError: 0`, hiding the real diagnostic. The aggregate is now
  cast to `text` and the row read by key.

  `hdrctl validate` was unaffected and still reported a valid DSL, so the failure only showed at
  run time.

### Changed

- The "driver missing" errors now name the extra to install rather than the underlying package:
  `pip install "hydra-etl[postgres]"`, `[mysql]`, `[mongodb]` — matching what the SQL Server
  connector already did.

### Added

- `tests/test_postgresql_upsert_key_validation.py` — unit coverage for upsert key validation, with
  no database or driver required. The existing end-to-end PostgreSQL tests do cover this path, but
  they are skipped at module level because they need live containers, which is why the regression
  shipped.

**Install:** `pip install hydra-etl==0.11.4`
