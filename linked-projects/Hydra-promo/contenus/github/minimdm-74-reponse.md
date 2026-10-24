# Réponse à publier — `planemarlin/minimdm` #74

- **Fil :** <https://github.com/planemarlin/minimdm/issues/74> — ouvert, 3 commentaires
- **Répondre à :** `@lij55` (auteur de l'issue)
- **Statut : ✅ PRÊT À PUBLIER.** Scénario exécuté le 18/10 contre `hydra-etl[postgres]==0.11.4`
  **téléchargée depuis PyPI** dans un environnement neuf, face à un PostgreSQL 16.15 réel.

## Ce qui a été mesuré (et non supposé)

Source `nordkraft.product` : 5 fiches — 2 actives, 1 draft, 1 retired, 1 soft-deleted.
Destination `public.product` : PRIMARY KEY sur `record_id`.

| Passe | Attendu | Observé |
|---|---|---|
| 1 — table vide | seules les 2 fiches golden | `Rows read 2 / written 2` → 2 lignes |
| 2 — même fenêtre, rejouée | aucun doublon | `written 2` → **toujours 2 lignes** |
| 3 — après `UPDATE` en amont | la valeur se propage | `A-1` → `Rotor 40 MkII / 131.00` |

Le filtre `_state = 'active' AND _deleted_at IS NULL` écarte bien draft, retired et soft-deleted.
`hdrctl validate` répond `DSL valid`. `${ENV:LAST_RUN}` est bien substitué **à l'intérieur** de la
chaîne SQL. Le `.env` du dossier du job est chargé automatiquement.

## Changements par rapport au brouillon du 17/10

1. **`pip install "hydra-etl[postgres]"`** et non `pip install hydra-etl` : sans l'extra, le job
   échoue d'emblée sur `driver manquant`.
2. **Colonnes listées explicitement.** `SELECT *` fait échouer le chargement
   (`column "_state" of relation "product" does not exist`) : le connecteur insère les colonnes du
   premier batch telles quelles.
3. **Valeurs littérales plutôt que placeholders.** Seul le mot de passe reste en `${ENV:}` : un
   lecteur voit la forme du job d'un coup d'œil, et la note finale explique `${ENV:}` et
   `${SECRET:}` une fois, à la fin. Les deux formes ont été exécutées contre la 0.11.4 ;
   `${SECRET:mdm.password}` lit bien `MDM_PASSWORD` dans l'environnement.
4. **Chemin du job.** En 0.11.4, `hdrctl init` crée un **projet** (`.hydra/`, `jobs/job1/`,
   `workflows/`), pas un dossier de job. Les manifestes vivent dans `jobs/job1/`. Le commentaire ne
   cite donc pas `hdrctl init` du tout — inutile pour le lecteur, et c'est la partie qui bouge.
5. **Version minimale indiquée** : `>=0.11.4`. En 0.11.3 l'upsert PostgreSQL échoue (`KeyError: 0`).

---

## Texte à copier-coller (en anglais) — VERSION COURTE, c'est celle-ci qu'on publie

---

The webhook answers "when", but the thing that will bite you is "what if it didn't arrive". It's a
single attempt, 5s timeout, no retry — and as @planemarlin noted, bulk imports and the inbound
endpoint don't fire webhooks at all. So the scheduled catch-up isn't a safety net, it's the only
path that sees every record. The webhook just makes it faster.

That turns the problem from triggering into idempotency: if loading the same golden record twice is
a no-op, you stop caring whether a given notification arrived. Upsert on the record id and both
paths run the identical load, only with a different window:

```sql
SELECT record_id, sku, name, price
FROM <schema>.<object>
WHERE _state = 'active' AND _deleted_at IS NULL
  AND _updated_at > :last_run;
```

Two traps there: list the columns rather than `SELECT *`, or the internal `_` columns reach your
warehouse table and the insert fails on the first one that doesn't exist; and store the max
`_updated_at` you actually committed, not the clock time at the start, or you'll skip rows written
during the run.

On "it is another app anyway" — it needn't be one you write. Disclosure: I'm the author of Hydra ETL
(`pip install "hydra-etl[postgres]"`, needs >= 0.11.4). It does only the load step: that query goes
in a `sources.yaml`, and the target side is the whole trick:

```yaml
# destinations.yaml
destinations:
  warehouse:
    type: postgresql
    connection:
      host: warehouse.internal
      database: analytics
      user: loader
      password: ${ENV:PG_PASS}   # from a .env beside the manifests, or the environment
    load:
      table: product
      mode: upsert
      key: [record_id]
```

`hdrctl validate <job>` checks the manifests without touching any data, `hdrctl run <job>` performs
the load. Your webhook receiver becomes a handler that shells out to the same command cron uses. I
ran this against a PostgreSQL 16 source holding active, draft, retired and soft-deleted rows: only
the two golden ones land, a second run changes nothing, an upstream edit propagates.

It's beta and I'm the only maintainer — the upsert path was in fact broken until 0.11.4, hence the
version note. Pin it if this sits on a critical path.

---

> **Variante longue archivée.** Une version détaillée (sources.yaml complet, bloc `.env`, ligne de
> cron, `${SECRET:}`, comportement si une variable manque) a été rédigée puis écartée : trop longue
> pour l'issue d'un tiers, où la quantité se lit comme de l'insistance. Elle reste utile comme base
> pour la **documentation du site** ou un article — les éléments sont dans l'historique de ce
> fichier et dans `suivi/journal.md` (18/10).

---

## Rappels

- Une seule mention d'Hydra ETL, divulgation présente, limites assumées — y compris le bug 0.11.3,
  dit franchement. C'est ce qui rend le reste crédible.
- Aucun dénigrement : le commentaire s'appuie sur les réponses du mainteneur.
- Remplacer `<schema>.<object>` par le schéma et l'objet réels si tu préfères un exemple concret.
