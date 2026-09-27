# Page site — « What `hdrctl validate` checks » (EN)

> Rédigée d'après le code (`hydra_etl/cli/hdrctl.py`, `cmd_validate` et `cmd_test`) au 19/09/2026.
> ⚠️ Publier **après** correction des 2 bugs notés dans `github/good-first-issues.md` (sinon la section « strict » serait inexacte).
> Emplacement proposé : `hydraetl.com/docs/validation` + lien depuis la page d'accueil et le README.

---

# What `hdrctl validate` checks — and what it cannot

Hydra ETL separates three levels of checks. Each one runs without the next.

| Command | Reads your data? | Contacts your systems? | Catches |
|---|---|---|---|
| `hdrctl validate` | No | No | Errors in the pipeline definition |
| `hdrctl test` | No | Yes | Connection and credential errors |
| `hdrctl run --dry-run` | Yes | Yes | Errors that depend on the data *(to confirm)* |

## Checked by `hdrctl validate` (no data, no network)

- **Required files** — `pipeline.yaml`, `sources.yaml`, `destinations.yaml` exist; `transformations.yaml` is optional.
- **YAML syntax** of every manifest.
- **Schema of each manifest** — sources, destinations and transformation steps are parsed by typed models: unknown step names, missing required fields and wrong field types are rejected.
- **References** — `pipeline.from` points to a declared source and `pipeline.to` to a declared destination.
- **Strict mode** (`--strict`) — lists the recognised operations and checks the syntax of `filter` and `calculate` expressions.

Exit code `0` when everything passes, `1` otherwise — ready for CI.

## Checked by `hdrctl test` (contacts your systems)

- The connection to each source and destination opens with the configured credentials.

## Only detectable at run time

- Values that do not fit the declared type (e.g. `"abc"` cast to `int`).
- A column referenced by a step that is missing from the actual file or table.
- File encoding or delimiter issues.
- Database constraints (unique keys, foreign keys, permissions on write).

## Why this matters

Most pipeline failures in scripts appear halfway through a load. With Hydra ETL, definition errors fail in seconds on your laptop or in CI, before anything is read or written.
