# Référence du Hydra DSL

> **Fichier généré** par `tools/spec_export.py` depuis les modèles du
> moteur. Ne pas modifier à la main : toute correction se fait dans le
> code, puis on régénère.

Version du produit : **0.10.0**

## Connecteurs (9)

`csv`, `json`, `mariadb`, `mongodb`, `mysql`, `parquet`, `postgres`, `postgresql`, `web_api`

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

> Attention : une action inconnue est **ignorée silencieusement** à
> l'exécution et le step est compté comme réussi. Une faute de frappe
> ne se voit donc pas.
