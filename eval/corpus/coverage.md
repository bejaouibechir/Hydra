# Couverture du corpus

> Fichier généré par `eval/corpus/harvest.py`.

- Jobs récoltés : **71**
- Workflows récoltés : **20**
- Exemples négatifs (`ko_*`, invalides par construction) : **11**, dont **8** effectivement rejetés par les parseurs
- Entrées invalides non voulues : **8**
- Jobs au câblage from/to incohérent : **3**

Un `0` signale un élément du DSL qu'**aucun exemple n'illustre** : c'est
exactement là qu'un modèle se trompera, et là qu'il faut écrire un exemple.

### Opérations (18)

| Élément | Occurrences |
|---|---:|
| `filter` | 37 |
| `cast` | 28 |
| `sort` | 24 |
| `select` | 23 |
| `aggregate` | 10 |
| `calculate` | 10 |
| `clean` | 9 |
| `join` | 7 |
| `rename` | 7 |
| `fill_null` | 3 |
| `pivot` | 2 |
| `script` | 2 |
| `transpose` | 2 |
| `unpivot` | 2 |
| `deduplicate` | 1 |
| `merge` | 1 |
| `trim` | 1 |
| `union` | 1 |

### Connecteurs (9)

| Élément | Occurrences |
|---|---:|
| `csv` | 85 |
| `mysql` | 36 |
| `mariadb` | 18 |
| `json` | 1 |
| `mongodb` | 1 |
| `postgresql` | 1 |
| `parquet` | **0 — non couvert** |
| `postgres` | **0 — non couvert** |
| `web_api` | **0 — non couvert** |

### Actions de workflow (11)

| Élément | Occurrences |
|---|---:|
| `log` | 12 |
| `powershell` | 4 |
| `assign_param` | 3 |
| `set_param` | 3 |
| `bash` | 1 |
| `delay` | 1 |
| `python` | 1 |
| `condition` | **0 — non couvert** |
| `email` | **0 — non couvert** |
| `ssh` | **0 — non couvert** |
| `webhook` | **0 — non couvert** |

### Modes de chargement

| Élément | Occurrences |
|---|---:|
| `replace` | 53 |
| `append` | 18 |

### Entrées invalides non voulues

Stubs vides ou incomplets du dépôt. À exclure du few-shot.

- `test_scenarios/containers/jobs/job_fail` — transformations.yaml: 1 validation error for TransformConfig
- `test_scenarios/retail_analytics/jobs/job1` — sources.yaml: 1 validation error for SourcesConfig, destinations.yaml: 1 validation error for DestinationsConfig, transformations.yaml: 1 validation error for TransformConfig
- `test_scenarios/retail_analytics/jobs/join3_mariadb` — destinations.yaml: 1 validation error for DestinationsConfig
- `test_scenarios/retail_analytics/jobs/param_job` — transformations.yaml: 1 validation error for TransformConfig
- `test_scenarios/retail_analytics/jobs/production` — pipeline.yaml: 2 validation errors for PipelineConfig
- `test_scenarios/retail_analytics/jobs/second-job` — transformations.yaml: 2 validation errors for TransformConfig
- `test_scenarios/retail_analytics/jobs/webhook_job` — transformations.yaml: 1 validation error for TransformConfig
- `test_scenarios/retryscope_job` — transformations.yaml: 1 validation error for TransformConfig

### Câblage incohérent (pipeline.from / pipeline.to)

- `test_scenarios/retail_analytics/jobs/production`
- `tests/fixtures/dsl_cases/ko_pipeline_unknown_destination_01`
- `tests/fixtures/dsl_cases/ko_unknown_source_01`
