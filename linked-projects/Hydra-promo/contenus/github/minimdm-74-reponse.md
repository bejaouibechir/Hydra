# Réponse à publier — `planemarlin/minimdm` #74

- **Fil :** <https://github.com/planemarlin/minimdm/issues/74> — ouvert, 3 commentaires, dernière activité 16/10/2026
- **Répondre à :** `@lij55` (auteur de l'issue)
- **Statut du YAML :** ✅ vérifié le 17/10 avec `hydra-etl` 0.11.3 — `hdrctl init <nom> --template postgres`
  puis `hdrctl validate .` → *DSL valid, no errors detected*. `extract.query` est bien accepté
  (`internal/parser/source.py` : `table` **ou** `query` **ou** `collection`).
- **Commandes vérifiées :** `hdrctl validate [PATH]` et `hdrctl run [PATH]` (défaut : dossier courant).

## Texte à copier-coller (en anglais)

---

The webhook answers "when", but the part that will still bite you is "what if it didn't arrive".
Delivery is a single attempt with a 5s timeout and no retry, and as you noted, bulk imports and the
inbound endpoint don't fire webhooks at all. So the periodic catch-up isn't just a safety net — it's
the only path that ever sees those records. Worth flipping the mental model: the scheduled run is the
correctness guarantee, the webhook is a latency optimisation on top of it.

That makes idempotency the real requirement rather than the trigger. If loading the same golden
record twice is a no-op, you can stop caring whether any individual notification arrived: upsert on
the record id and both paths become the same code, your receiver and your cron job running the
identical load with a different time window.

Two details worth getting right in the watermark:

- store the max `_updated_at` you actually committed, not the clock time at the start of the run, or
  you will silently skip rows written while it was going;
- keep the comparison strictly greater and accept re-reading a couple of boundary rows — it costs
  nothing once the load is an upsert.

```sql
SELECT * FROM <schema>.<object>
WHERE _state = 'active' AND _deleted_at IS NULL
  AND _updated_at > :last_run;
```

On "it is another app anyway" — it doesn't have to be an app you write and maintain. Disclosure: I'm
the author of Hydra ETL (open source, `pip install hydra-etl`), which does only this one step — a
declarative load, no scheduler, no server of its own. For your case the job is two files:

```yaml
# sources.yaml
sources:
  minimdm:
    type: postgresql
    connection:
      host: ${ENV:MDM_HOST}
      port: 5432
      database: ${ENV:MDM_DB}
      user: ${ENV:MDM_USER}      # the read-only role from your comment
      password: ${ENV:MDM_PASS}
    extract:
      query: >
        SELECT * FROM <schema>.<object>
        WHERE _state = 'active' AND _deleted_at IS NULL
          AND _updated_at > '${ENV:LAST_RUN}'
      batch_size: 10000
```

```yaml
# destinations.yaml
destinations:
  warehouse:
    type: postgresql
    connection:
      host: ${ENV:PG_HOST}
      port: 5432
      database: ${ENV:PG_DB}
      user: ${ENV:PG_USER}
      password: ${ENV:PG_PASS}
    load:
      table: product
      mode: upsert
      key: [record_id]
```

plus a two-line `pipeline.yaml` (`from: minimdm`, `to: warehouse`). `hdrctl validate .` checks the
manifests and resolves the source and destination references without touching any data, which is the
part I'd put in CI, and `hdrctl run .` performs the load. Your webhook receiver then becomes a handler
that shells out to the same command the scheduled run uses.

Fair warning so you can size the bet: it's beta and I'm the only maintainer, so pin a version if this
sits on a critical path. For an hourly or nightly sync it's a reasonable amount of machinery not to
write yourself.

---

## Rappels avant de poster

- Une seule mention d'Hydra ETL, divulgation présente, limites assumées (bêta, mainteneur unique).
- Aucun dénigrement : le commentaire s'appuie sur les réponses du mainteneur au lieu de les contredire.
- Remplacer `<schema>.<object>` par le schéma/objet réels si tu préfères un exemple concret.
