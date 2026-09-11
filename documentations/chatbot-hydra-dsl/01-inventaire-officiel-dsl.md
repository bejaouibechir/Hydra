# Inventaire officiel du Hydra DSL

**Étape 1 — Périmètre du chatbot d'apprentissage**  
**État :** inventaire établi depuis le code exécutable  
**Version produit observée :** Hydra CLI `1.2.0`  
**Versions de manifests observées :** `1.0` et parseurs DSL `1.1`

## 1. Règle de classement

Un élément est considéré comme **officiel et exécutable** lorsqu'il est :

1. accepté par le parseur ou le modèle Pydantic actif ;
2. pris en charge par le moteur ou le runner actif ;
3. absent des dossiers `backup`, `_archive` et `_backups`.

Le catalogue de l'interface seul n'est pas considéré comme source de vérité.

## 2. Structure canonique d'un job Hydra

Un job Hydra est composé des manifests suivants :

| Manifest | Racine DSL | Rôle | Statut |
|---|---|---|---|
| `sources.yaml` | `sources` | Déclarer les entrées | Officiel |
| `transformations.yaml` | `transformations.steps` ou `steps` | Déclarer les transformations ordonnées | Officiel, facultatif |
| `destinations.yaml` | `destinations` | Déclarer les sorties | Officiel |
| `pipeline.yaml` | `pipeline` | Relier une source à une destination | Officiel |

La structure canonique de `pipeline.yaml` contient au minimum :

```yaml
version: "1.0"
pipeline:
  name: orders_pipeline    # facultatif dans le runner actuel
  from: orders_source      # identifiant déclaré dans sources.yaml
  to: orders_destination   # identifiant déclaré dans destinations.yaml
  transformations: transformations  # facultatif
```

Les clés réellement exigées par l'exécuteur sont `pipeline.from` et `pipeline.to`.

## 3. Transformations officielles

Les 18 transformations ci-dessous sont présentes à la fois dans le registre du parseur et dans le moteur Pandas.

| Transformation | Rôle principal | Modèle Pydantic |
|---|---|---|
| `select` | Conserver certaines colonnes | `SelectOp` |
| `rename` | Renommer des colonnes | `RenameOp` |
| `cast` | Convertir les types | `CastOp` |
| `filter` | Conserver les lignes correspondant à une expression | `FilterOp` |
| `calculate` | Créer ou recalculer une colonne | `CalculateOp` |
| `sort` | Trier les lignes | `SortOp` |
| `deduplicate` | Supprimer les doublons | `DeduplicateOp` |
| `fill_null` | Remplacer les valeurs nulles | `FillNullOp` |
| `trim` | Retirer les espaces des textes | `TrimOp` |
| `aggregate` | Grouper et agréger | `AggregateOp` |
| `join` | Joindre une deuxième source | `JoinOp` |
| `clean` | Nettoyer et normaliser la casse des textes | `CleanOp` |
| `pivot` | Transformer des lignes en colonnes | `PivotOp` |
| `unpivot` | Transformer des colonnes en lignes | `UnpivotOp` |
| `transpose` | Transposer lignes et colonnes | `TransposeOp` |
| `merge` | Fusionner deux jeux de données selon une clé | `MergeOp` |
| `union` | Empiler deux jeux de données | `UnionOp` |
| `script` | Exécuter une transformation Python contrôlée | `ScriptOp` |

### Types de cast confirmés

```text
int · float · str · bool · date · datetime
```

### Jointures confirmées

```text
inner · left · right · outer
```

### Fonctions d'agrégation annoncées par le modèle

```text
sum · count · mean · avg · min · max · first · last
```

### Modes de script confirmés

```text
vectorized · row
```

## 4. Connecteurs officiellement enregistrés

Le registre actif dans l'environnement courant expose :

| Type DSL | Source | Destination | Remarque |
|---|---:|---:|---|
| `csv` | Oui | Oui | Connecteur cœur |
| `json` | Oui | Non | Le chargement JSON lève explicitement `NotImplementedError` |
| `mysql` | Oui | Oui | Connecteur SQL |
| `mariadb` | Oui | Oui | Même implémentation que MySQL |
| `postgresql` | Oui | Oui | Type canonique PostgreSQL |
| `postgres` | Oui | Oui | Alias de `postgresql` |
| `mongodb` | Oui | Oui | Connecteur optionnel, disponible dans l'environnement courant |
| `parquet` | Oui | Oui | Connecteur optionnel, disponible dans l'environnement courant |

### Connecteur à ne pas présenter comme actif

`web_api` apparaît dans le catalogue de l'interface et possède une implémentation, mais il n'est pas enregistré dans le registre actif de l'environnement inspecté. Il reste donc **hors du corpus officiel du chatbot MVP** tant que son instanciation et ses dépendances ne sont pas validées.

## 5. Chargement des destinations

Les modes validés par `LoadConfig` sont :

```text
append · replace · upsert
```

Règle confirmée : `upsert` exige au moins une colonne dans `load.key`.

## 6. Schéma des sources

Une source peut déclarer un bloc `schema` avec les modes :

```text
auto · manual · infer_strict · hybrid
```

Politiques de dérive :

```text
fail · warn · ignore · adapt
```

Politiques de validation :

```text
strict · best_effort · permissive
```

Traitement des tableaux :

```text
keep · flatten · explode · json
```

## 7. Structure canonique d'un workflow Hydra

Le manifest officiel est `workflow.yaml`, avec la racine `workflow`.

```yaml
workflow:
  version: "1.0"
  name: daily_orders
  trigger:
    type: manual
  steps:
    - name: run_orders
      type: job
      job: ./jobs/orders
      depends_on: []
      on_failure: fail
```

### Déclencheurs confirmés

```text
manual · schedule · webhook
```

`schedule` exige la propriété `trigger.cron`.

### Types d'étapes confirmés

```text
job · action
```

### Propriétés d'orchestration confirmées

| Propriété | Valeurs ou rôle |
|---|---|
| `depends_on` | Dépendances entre étapes |
| `on_failure` | `fail`, `skip`, `continue` |
| `enabled` | Active ou ignore l'étape |
| `retry.max` | Nombre de nouvelles tentatives |
| `retry.delay` | Délai entre les tentatives |
| `retry.backoff` | `fixed`, `exponential` |
| `when` | Expression conditionnelle d'exécution |

### Actions réellement exécutées par le runner

```text
webhook
log
delay
condition
bash
powershell
ssh
email
python
set_param
assign_param
```

## 8. Incohérences découvertes

Ces incohérences devront être traitées avant de présenter le catalogue comme une référence publique :

1. L'API `/api/nodes` annonce `derive`, mais le DSL officiel utilise `calculate`.
2. L'API `/api/nodes` annonce `index`, absent du parseur et du moteur.
3. L'API omet plusieurs transformations exécutables : `trim`, `calculate`, `transpose`, `merge`, `union` et `script` notamment.
4. L'API annonce l'action `slack`, mais le runner ne possède aucun handler `slack`.
5. Le runner accepte plusieurs actions absentes du catalogue de l'interface.
6. `web_api` est annoncé dans l'interface, mais n'est pas enregistré dans l'environnement courant.
7. `json` est présenté comme source et destination dans l'interface, alors que son chargement n'est pas implémenté.
8. La version produit (`1.2.0`), la version des manifests (`1.0`) et l'intitulé des parseurs (`DSL v1.1`) ne forment pas encore une politique de version explicite.

## 9. Périmètre officiel retenu pour le chatbot MVP

Le chatbot peut apprendre et expliquer :

- les quatre manifests d'un job ;
- les 18 transformations officielles ;
- les sources et destinations confirmées par le registre actif ;
- les modes `append`, `replace` et `upsert` ;
- les workflows, déclencheurs, dépendances, conditions et retries ;
- les 11 actions réellement dispatchées par le runner ;
- les règles de schéma des sources.

Le chatbot ne doit pas encore présenter comme disponible :

- `derive` ;
- `index` ;
- `slack` ;
- `web_api` ;
- JSON comme destination.

## 10. Sources techniques de cet inventaire

- `internal/parser/transform.py` — registre et modèles des transformations ;
- `internal/engines/pandas_engine.py` — opérations réellement exécutées ;
- `internal/parser/source.py` — DSL des sources et schémas ;
- `internal/parser/destination.py` — DSL des destinations et modes de chargement ;
- `internal/connector/registry.py` — connecteurs enregistrés ;
- `internal/connector/json_connector.py` — limites du connecteur JSON ;
- `internal/runner/executor.py` — résolution du pipeline ;
- `workflow/models.py` — modèle du workflow ;
- `workflow/runner.py` — actions réellement exécutées ;
- `api/routers/nodes.py` — catalogue de l'interface et écarts observés.

## 11. Décision requise avant l'étape 2

Valider cet inventaire comme périmètre officiel provisoire du chatbot. Les incohérences de catalogue pourront ensuite faire l'objet d'une correction séparée ; elles ne doivent pas contaminer les schémas générés à l'étape 2.
