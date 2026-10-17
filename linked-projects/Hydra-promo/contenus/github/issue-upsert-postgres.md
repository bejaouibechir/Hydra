# Issue à ouvrir sur `bejaouibechir/Hydra`

**Titre :** `upsert mode on PostgreSQL always fails with KeyError: 0`

**Labels suggérés :** `bug`, `connector:postgresql`, `priority:high`

---

## Corps de l'issue (EN — à copier-coller)

### What happens

Every PostgreSQL destination using `mode: upsert` fails, regardless of the target table, even when a
PRIMARY KEY exists on exactly the columns listed in `key`:

```
ValueError: PostgreSQLConnector [warehouse]: échec chargement.
  Table : public.product
  Mode  : upsert
  Erreur : KeyError: 0
```

`hdrctl validate .` reports `DSL valid — no errors detected`, so the failure only appears at run
time. `mode: append` and `mode: replace` are unaffected.

### Reproducing

```sql
CREATE TABLE product (record_id uuid PRIMARY KEY, sku text, name text, price numeric(10,2));
```

```yaml
# destinations.yaml
destinations:
  warehouse:
    type: postgresql
    connection: { host: ..., port: 5432, database: ..., user: ..., password: ... }
    load:
      table: product
      mode: upsert
      key: [record_id]
```

`hdrctl run .` → `KeyError: 0`. Verified on PostgreSQL 16.15, hydra-etl 0.11.3 from PyPI, Python 3.13.

### Cause

Both defects are in `_validate_upsert_key()`, `hydra_etl/internal/connector/postgresql_connector.py`.

**1. `array_agg` over a `sql_identifier` column comes back as text, not a list.**
`information_schema.key_column_usage.column_name` is of type `sql_identifier`; psycopg2 has no array
decoder for it and falls back to the raw representation:

```python
{'constraint_name': 'product_pkey', 'constraint_cols': '{record_id}'}   # a str, not ['record_id']
```

`set(constraint_cols)` is therefore a set of *characters* and can never equal `{'record_id'}`, so a
valid constraint is never recognised.

**2. A `RealDictCursor` row is unpacked as if it were a tuple.**
The cursor is created with `cursor_factory=psycopg2.extras.RealDictCursor` (line 149), so each row is
a dict:

```python
constraint_name, constraint_cols = constraint   # binds the KEYS, not the values
```

The error branch then does `c[0]` on that dict, which raises `KeyError: 0` and hides the real
diagnostic — which is why users see `KeyError: 0` rather than a message about constraints.

### Why CI is green

`tests/test_e2e_postgresql.py` does cover this path (`test_load_upsert_simple_key`,
`test_load_upsert_composite_key`), but the module is disabled wholesale:

```python
pytestmark = pytest.mark.skip(reason="E2E: requires live PostgreSQL containers")
```

So the only tests exercising PostgreSQL upsert never run. They also swallow failures into
`print(...)` plus `sys.exit(1)` instead of asserting, which makes them hard to read in CI output.

### Fix

Three lines — cast the aggregate to `text`, and read the row by key:

```python
array_agg(kcu.column_name::text ORDER BY kcu.ordinal_position) as constraint_cols
```

```python
constraint_name = constraint["constraint_name"]
constraint_cols = constraint["constraint_cols"]
```

```python
f"{c['constraint_name']}({', '.join(c['constraint_cols'])})" for c in constraints
```

Plus a unit test that needs no database, so the path is covered in CI:
`tests/test_postgresql_upsert_key_validation.py` (fake `RealDictCursor` reproducing both psycopg2
behaviours; 5 cases: simple PK, composite key in any order, UNIQUE constraint, no constraint, and
non-matching key).

### Verified after the fix

Source table with 5 records (2 active, 1 draft, 1 retired, 1 soft-deleted), destination with a PK on
`record_id`:

| Pass | Expected | Observed |
|---|---|---|
| 1 — empty table | 2 rows loaded | read 2 / written 2 → 2 rows |
| 2 — same window, replayed | no duplicates | written 2 → still 2 rows (idempotent) |
| 3 — after an upstream `UPDATE` | new value propagates | `A-1` → `Rotor 40 MkII / 131.00` |

Against the unpatched `HEAD` the new unit test fails with `KeyError: 0`, so it does catch the
regression.

### Separate question, not changed here

`_validate_upsert_key()` demands an exact set match between `key` and a PRIMARY KEY/UNIQUE
constraint. A composite PK that is a superset, or a partial unique index, is refused even where
PostgreSQL's `ON CONFLICT` would accept it. Left as is — worth its own discussion.

---

## Message de commit suggéré

```
fix(postgresql): upsert key validation fails on every table

_validate_upsert_key() could never recognise a valid constraint:

- array_agg over information_schema.key_column_usage.column_name (type
  sql_identifier) is returned by psycopg2 as the raw text '{col}' rather
  than a list, so the set comparison compared characters;
- the RealDictCursor row was unpacked as a tuple, binding the dict KEYS,
  and the error branch indexed it as c[0], raising KeyError: 0 and
  hiding the real diagnostic.

Cast the aggregate to text and read the row by key. Add a unit test that
needs no live database, since the existing E2E coverage for this path is
skipped at module level and never runs in CI.
```

## Note sur les tests existants

Ne pas se contenter du correctif : lever le `pytestmark = pytest.mark.skip` de
`tests/test_e2e_postgresql.py` dans un job CI avec services PostgreSQL, ou au moins remplacer les
`except Exception: print(...); sys.exit(1)` par de vraies assertions. En l'état, ces tests ne
protègent rien même s'ils sont un jour réactivés.
