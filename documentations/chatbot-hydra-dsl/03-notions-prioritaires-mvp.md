# Dix notions prioritaires du chatbot Hydra DSL

**Étape 3 — Sélection du périmètre MVP**  
**État :** terminé, en attente de validation  
**Dépendances :** inventaire DSL et schémas JSON terminés

## 1. Objectif de la sélection

Le premier corpus du chatbot doit permettre à un débutant de :

1. comprendre la structure d'un projet Hydra ;
2. construire un pipeline exécutable de bout en bout ;
3. réaliser les transformations les plus structurantes ;
4. diagnostiquer les erreurs DSL les plus probables ;
5. passer d'un job simple à un workflow.

Le MVP ne cherche pas encore à documenter les 18 transformations avec la même profondeur.

## 2. Critères utilisés

Chaque notion a été examinée selon quatre critères :

| Critère | Question |
|---|---|
| Fondamental | Est-elle nécessaire pour comprendre ou construire un pipeline ? |
| Fréquence | Est-elle présente dans les exemples, tests et prototypes actuels ? |
| Valeur pédagogique | Introduit-elle un concept réutilisable dans le reste du DSL ? |
| Maturité | Est-elle validée et exécutée par le code actif ? |

La couverture du parcours complet prime sur la simple fréquence textuelle.

## 3. Sélection officielle des dix notions

| Ordre | Identifiant pédagogique | Notion | Objectif principal |
|---:|---|---|---|
| 1 | `dsl.job_pipeline` | Job et pipeline | Comprendre les quatre manifests et les références `from`/`to` |
| 2 | `dsl.source` | Source | Déclarer l'origine des données et son extraction |
| 3 | `dsl.destination` | Destination | Déclarer la sortie et choisir un mode de chargement |
| 4 | `transform.select` | `select` | Choisir les colonnes conservées |
| 5 | `transform.filter` | `filter` | Filtrer les lignes avec une expression booléenne |
| 6 | `transform.calculate` | `calculate` | Créer une colonne à partir d'une expression |
| 7 | `transform.cast` | `cast` | Convertir explicitement les types de colonnes |
| 8 | `transform.aggregate` | `aggregate` | Grouper et résumer des données |
| 9 | `transform.join` | `join` | Combiner deux sources selon une clé |
| 10 | `dsl.workflow` | Workflow | Orchestrer plusieurs jobs avec dépendances et politiques d'exécution |

## 4. Périmètre précis de chaque notion

### 1. Job et pipeline

**À enseigner :**

- rôle de `sources.yaml`, `transformations.yaml`, `destinations.yaml` et `pipeline.yaml` ;
- racine `pipeline` ;
- `from`, `to`, `name` et `transformations` ;
- résolution des identifiants entre les manifests ;
- différence entre job, pipeline et workflow.

**Erreurs prioritaires :**

- racine `pipeline` absente ;
- `from` manquant ou source inconnue ;
- `to` manquant ou destination inconnue ;
- confusion entre nom de connecteur et identifiant de source.

**Limite actuelle :** `pipeline.yaml` ne possède pas encore de modèle Pydantic dédié.

### 2. Source

**À enseigner :**

- racine `sources` et identifiant utilisateur ;
- `type`, `connection` et `extract` ;
- `table`, `query`, `collection`, `limit` et `batch_size` ;
- notion de schéma d'entrée ;
- différence entre configuration et secret.

**Connecteurs MVP :**

- CSV comme support pédagogique principal ;
- JSON en lecture ;
- MySQL/MariaDB et PostgreSQL comme exemples SQL ;
- MongoDB comme exemple documentaire ;
- Parquet comme exemple de fichier colonnaire.

### 3. Destination

**À enseigner :**

- racine `destinations` ;
- `type`, `connection` et `load` ;
- `table`, `batch_size` et `key` ;
- modes `append`, `replace` et `upsert` ;
- obligation de `key` avec `upsert`.

**Limite à expliquer :** JSON n'est pas une destination active dans le MVP actuel.

### 4. `select`

**À enseigner :**

- propriété obligatoire `columns` ;
- conservation de l'ordre demandé ;
- suppression des doublons de la liste par le validateur ;
- effet sur le schéma de sortie.

**Erreurs prioritaires :** liste vide, nom vide et colonne inexistante.

### 5. `filter`

**À enseigner :**

- propriété obligatoire `expr` ;
- comparaison et expression booléenne ;
- combinaison de conditions ;
- distinction entre lignes d'entrée et de sortie ;
- comportement face à une colonne inconnue.

**Erreurs prioritaires :** expression vide, colonne inconnue, type incompatible et syntaxe incorrecte.

### 6. `calculate`

**À enseigner :**

- propriétés `column` et `expr` ;
- création ou remplacement d'une colonne ;
- expressions basées sur plusieurs colonnes ;
- effet sur le schéma de sortie.

**Erreurs prioritaires :** colonne cible vide, expression absente et référence inconnue.

### 7. `cast`

**À enseigner :**

- propriété `mapping` ;
- types exécutables `int`, `float`, `str`, `bool` et `datetime` ;
- conversion explicite avant calcul, jointure ou écriture ;
- différence entre type de donnée et format d'affichage.

**Erreurs prioritaires :** type non supporté, valeur non convertible et colonne inconnue.

**Écart connu :** le schéma Pydantic annonce aussi `date`, mais le moteur actif ne l'exécute pas encore. Le chatbot MVP ne doit donc pas proposer `date` comme type exécutable.

### 8. `aggregate`

**À enseigner :**

- colonnes de groupement `by` ;
- dictionnaire `agg` ;
- colonne source, fonction et colonne produite ;
- fonctions `sum`, `count`, `mean`, `avg`, `min`, `max`, `first`, `last` ;
- changement de granularité du résultat.

**Erreurs prioritaires :** groupe vide, agrégation vide, colonne inconnue et fonction incorrecte.

### 9. `join`

**À enseigner :**

- deuxième source `right` ;
- clé commune `key` ou couple `left_key`/`right_key` ;
- modes `inner`, `left`, `right` et `outer` ;
- différence entre identifiant de source et source inline ;
- impact d'une jointure sur les lignes et colonnes.

**Erreurs prioritaires :** deuxième source absente, clé vide, clés incompatibles et mode inconnu.

### 10. Workflow

**À enseigner :**

- racine `workflow` ;
- déclencheurs `manual`, `schedule` et `webhook` ;
- étapes `job` et `action` ;
- `depends_on`, `enabled`, `when` et `on_failure` ;
- retries avec `fixed` ou `exponential` ;
- détection des références inconnues et des cycles.

**Actions MVP à illustrer :** `log`, `webhook` et `delay`. Les autres actions restent consultables dans le Guide mais ne sont pas nécessaires au parcours initial.

## 5. Ordre pédagogique retenu

```text
Job et pipeline
    ↓
Source → select → filter → calculate → cast → aggregate
    ↓                                      ↓
    └──────────────── join ────────────────┘
                       ↓
                  Destination
                       ↓
                    Workflow
```

La destination est expliquée conceptuellement dès la troisième notion, puis réutilisée à la fin de chaque exercice. Cela permet d'exécuter des pipelines complets avant d'aborder les transformations avancées.

## 6. Notions placées dans la vague suivante

| Priorité suivante | Notion | Motif du report |
|---:|---|---|
| 11 | `sort` | Simple et stable, mais moins structurante que la gestion des types |
| 12 | `rename` | Utile, mais son modèle mental est proche de `select` et `calculate` |
| 13 | `fill_null` | À introduire avec un parcours dédié à la qualité des données |
| 14 | `deduplicate` | Nécessite de bien expliquer les clés et la conservation des lignes |
| 15 | `clean` | Peut être regroupé avec `trim` dans un module de nettoyage |
| 16 | `union` | À aborder après `join` dans un module multi-sources |
| 17 | `pivot` / `unpivot` | Restructuration avancée |
| 18 | `transpose` | Cas plus spécialisé |
| 19 | `merge` | Sémantique avancée de fusion/upsert |
| 20 | `script` | Nécessite un chapitre sécurité et sandbox |

## 7. Ajustement par rapport à la proposition initiale

La première proposition contenait `sort`. Après analyse du dépôt :

- `cast` apparaît dans 23 fichiers pertinents inspectés ;
- `sort` apparaît dans 16 fichiers ;
- les erreurs de type affectent également `calculate`, `aggregate`, `join` et les destinations.

`cast` remplace donc `sort` dans les dix notions du MVP. `sort` devient la première notion de la vague suivante.

## 8. Critère de réussite du MVP

Après ces dix notions, le chatbot doit pouvoir accompagner un utilisateur depuis une question comme :

> Comment lire mes commandes, garder les commandes payées, calculer la TVA, agréger par client et écrire le résultat ?

jusqu'à :

- une structure de job correcte ;
- des propriétés DSL vérifiées ;
- des indices progressifs sur les erreurs ;
- un renvoi vers les bonnes fiches ;
- une explication claire de la transition vers un workflow.

## 9. Décision avant l'étape 4

Cette liste doit être considérée comme figée pour rédiger les quatre exemples de chaque notion à l'étape 4. Toute modification ultérieure changera le volume d'exemples et de tests à produire.
