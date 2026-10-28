# Référence du Hydra DSL

> **Fichier généré** par `tools/spec_export.py` depuis les modèles du
> moteur. Ne pas modifier à la main : toute correction se fait dans le
> code, puis on régénère.

Version du produit : **0.15.0**

## Connecteurs (11)

`csv`, `json`, `mariadb`, `mongodb`, `mssql`, `mysql`, `parquet`, `postgres`, `postgresql`, `sqlserver`, `web_api`

> `postgres`/`postgresql` et `mysql`/`mariadb` sont des alias.
> `mongodb`, `parquet` et `web_api` ne s'enregistrent qu'avec leur extra
> installé, mais font partie du DSL dans tous les cas.

## Manifestes

> `transformations.yaml` a **deux schémas** : `transformations.schema.json`
> décrit la forme interne (`op`/`params`) produite par `TransformParser`,
> et `transformations.surface.schema.json` la forme réellement écrite
> (`- filter: {expr: ...}`). Pour contraindre une génération, utiliser la
> forme écrite.

| Manifeste | Modèle source | Clés obligatoires |
|---|---|---|
| `destinations.yaml` | `hydra_etl.internal.parser.destination.DestinationsConfig` | `destinations` |
| `pipeline.yaml` | `hydra_etl.internal.parser.pipeline.PipelineConfig` | `pipeline` |
| `sources.yaml` | `hydra_etl.internal.parser.source.SourcesConfig` | — |
| `thread.yaml` | `hydra_etl.workflow.thread.ThreadDef` | — |
| `transformations.yaml` | `hydra_etl.internal.parser.transform.TransformConfig` | `steps` |
| `workflow.yaml` | `hydra_etl.workflow.models.WorkflowDef` | `name`, `steps` |

## Opérations de transformation (18)

| Opération | Clés obligatoires |
|---|---|
| `aggregate` | `by`, `agg` |
| `calculate` | `column`, `expr` |
| `cast` | `mapping` |
| `clean` | — |
| `deduplicate` | — |
| `fill_null` | — |
| `filter` | `expr` |
| `join` | `right` |
| `merge` | `right`, `key` |
| `pivot` | `index`, `column`, `values` |
| `rename` | `mapping` |
| `script` | `outputs`, `code` |
| `select` | `columns` |
| `sort` | `by` |
| `transpose` | — |
| `trim` | — |
| `union` | `right` |
| `unpivot` | `id_vars` |

## Actions de workflow (11)

`assign_param`, `bash`, `condition`, `delay`, `email`, `log`, `powershell`, `python`, `set_param`, `ssh`, `webhook`

> Toute autre action est refusée : `hdrctl workflow validate` échoue
> et `hdrctl workflow run` ne démarre pas, avec une suggestion en cas
> de faute de frappe.

## Tout ou rien et annulation

- `destinations.yaml` → `load.atomic` : rien n'est visible avant la fin du job,
  un échec laisse la destination intacte. Par défaut : oui pour `replace` et pour
  CSV / Parquet, non pour `append` / `upsert` en base (`atomic: true` pour l'activer).
- `workflow.yaml` → `rollback: true` : si le workflow échoue, les steps déjà faits
  sont défaits, du dernier au premier. Vérifié avant le run.
- Step `type: action` → `undo:` : `none`, ou `{action, params}` (même forme qu'un
  step). Exigé avec `rollback: true` pour : `bash`, `email`, `powershell`, `python`, `ssh`, `webhook`.
- Annulation inachevée : `hdrctl workflow undo <workflow>`.
- `thread.yaml` → `fallback.on_failure: true` : après un échec (ou un `timeout`
  dépassé), le remplaçant ne part que si le workflow n'a rien laissé de publié :
  aucun chargement publié, aucune action externe faite (sauf `undo: none`), ou
  tout défait par `rollback: true`. Sinon le projet s'arrête avec la raison.
  Si le remplaçant échoue à son tour, le suivant de `use` est essayé.
- `thread.yaml` → `timeout` (par workflow) : durée maximale ; arrêt au prochain
  step ou lot (chargement en tout ou rien annulé), compté comme un échec.

| Destination | Modes annulables |
|---|---|
| `csv` | `append`, `replace` |
| `mariadb` | `append`, `replace`, `upsert` |
| `mssql` | `append`, `replace`, `upsert` |
| `mysql` | `append`, `replace`, `upsert` |
| `parquet` | `append`, `replace` |
| `postgres` | `append`, `replace`, `upsert` |
| `postgresql` | `append`, `replace`, `upsert` |
| `sqlserver` | `append`, `replace`, `upsert` |

> En base, `append` annulable exige `load.key` : seules des clés neuves
> sont ajoutées, pour être retirées exactement.
