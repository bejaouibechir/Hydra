C'est la phase la plus importante : la conception du **DSL (Domain-Specific Language)** dans les manifestes YAML. Ce langage sera l'interface utilisateur de votre ETL et la fondation de tout le développement du `Parser` et du `Transformation Engine`.

L'objectif est d'avoir un DSL qui est **déclaratif** (facile à lire) mais qui se traduit **fluidement** en logique **impérative** optimisée (Python/Pandas ou DuckDB/SQL).

## I. Mappage des Transformations Possibles (Pandas vs. DuckDB)

Le secret de l'**adaptabilité Panda/DuckDB** est de distinguer les transformations qui opèrent **par ligne** (idéalement Pandas, ou JIT simple) de celles qui nécessitent l'**ensemble des données** (idéalement DuckDB/SQL).

| **Type de Transformation**               | **Description/Exemple**                                                                                                                               | **Moteur Idéal (Défaut)** | **Justification**                                                                                                                                        |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Transformation Unitaire (Calcul)**  | Création d'une nouvelle colonne basée sur d'autres colonnes de la même ligne. *Ex: `Revenu = Quantité * Prix`*.                                       | **Pandas**                | Opération de vecteur simple. Très rapide en Pandas.                                                                                                      |
| **2. Transformation Simple (Nettoyage)** | Modification de valeur basée sur des conditions simples ou des fonctions de nettoyage. *Ex: `Nettoyage: trim(col), upper(col), if(val > 0, val, 0)`*. | **Pandas**                | Idéal pour l'application de fonctions Python standard.                                                                                                   |
| **3. Mappage de Colonnes**               | Renommage ou sélection des colonnes.                                                                                                                  | **Pandas / DuckDB**       | Neutre. Peut être géré par un `SELECT` SQL ou par `df.rename()`.                                                                                         |
| **4. Jointures (Joins)**                 | Fusion de deux ou plusieurs flux de données (sources). *Ex: `JOIN ventes ON produits.id = ventes.prod_id`*.                                           | **DuckDB**                | Nécessite un moteur SQL optimisé pour la RAM et le disque. Pandas est inefficace ou gourmand en RAM ici.                                                 |
| **5. Agrégations (Aggregations)**        | Calculs de groupe (`GROUP BY`). *Ex: `SUM(Revenu), COUNT(*), AVG(prix) GROUP BY date`*.                                                               | **DuckDB**                | Logique SQL nativement optimisée pour les tables massives.                                                                                               |
| **6. Fenêtrage (Window Functions)**      | Calculs sur des ensembles de lignes connectées. *Ex: `Calcul de la Moyenne Mobile (Lead/Lag)`*.                                                       | **DuckDB**                | Fonctions avancées de SQL analytique. Difficile à coder efficacement en Pandas pur.                                                                      |
| **7. Lookup (Simple Join)**              | Recherche d'une valeur dans une petite table de référence chargée en mémoire. *Ex: `Lookup du nom de produit à partir de l'ID`*.                      | **Pandas**                | Si la table de référence est petite, un simple *dict lookup* ou *Pandas merge* est plus rapide à mettre en place que l'ouverture d'une connexion DuckDB. |

---

## II. Proposition de DSL YAML (Manifestes)

Nous maintenons le **découplage en trois fichiers** (`source`, `destination`, `transform`).

### 1. `source.yaml` (Déclaratif : Où sont les données ?)

Permet de définir des sources nommées, réutilisables dans le fichier `transform.yaml`.

YAML

```
version: "1.0"
sources:
  # Source 1: Base de données MySQL (relationnelle)
  mysql_catalogue:
    type: mysql
    connection:
      # Référence au Secret Manager
      host: "{{ secrets.DB_HOST }}"
      user: "{{ secrets.DB_USER }}"
      password: "{{ secrets.DB_PASS }}"
      database: "reference"
    extract:
      # Extraction par requête SQL
      query: "SELECT product_id, name, unit_price, category FROM products WHERE is_active = 1"

  # Source 2: Fichier CSV (non-relationnelle)
  csv_transactions:
    type: csv
    connection:
      path: "/data/in/transactions_2025.csv"
      delimiter: ";"
      # Exemple de schéma implicite (pour aider le parser)
    schema:
      - name: transaction_date
        type: date
      - name: product_id
        type: integer
      - name: quantity
        type: integer
      - name: status
        type: string
```

### 2. `destination.yaml` (Déclaratif : Où stocker le résultat ?)

Définit comment écrire les données finales.

YAML

```
version: "1.0"
destinations:
  # Destination 1: Table d'entrepôt MariaDB
  mariadb_revenue_report:
    type: mariadb
    connection:
      # Référence au Secret Manager
      host: "{{ secrets.DB_HOST }}"
      user: "{{ secrets.DB_USER }}"
      password: "{{ secrets.DB_PASS }}"
      database: "warehouse"
    load:
      table: "daily_revenue"
      # Stratégie de chargement (cruciale)
      strategy: upsert
      # Clé primaire pour l'UPSERT
      on_conflict: [ report_date, product_id ]
      # Si l'UPSERT n'est pas supporté, une approche TRUNCATE peut être utilisée :
      # strategy: truncate_and_insert
```

### 3. `transform.yaml` (Impératif/Déclaratif : Que faire des données ?)

C'est ici que le DSL doit être le plus précis. Nous utilisons une séquence de `steps` (étapes) pour garantir la fluidité et l'ordre d'exécution (approche séquentielle du MVP).

- Chaque étape (`step`) est nommée et produit un **flux de données** utilisable par l'étape suivante.

- **Contrôle de l'Engine :** Le `transform.yaml` indique au `Query Planner` (l'Engine) quel moteur utiliser (`engine: pandas` ou `engine: duckdb`).

---

## III. Exemples Concrets du DSL

### Exemple 1 : Simple (Mappage minimal)

- **Scénario :** Charger un fichier CSV directement vers MySQL avec seulement un renommage de colonnes.

- **Moteur utilisé :** Principalement Pandas (mappage simple).

YAML

```
version: "1.0"
pipeline:
  name: "csv_simple_load"
  source: "csv_transactions"
  destination: "mariadb_revenue_report"

steps:
  - name: "map_fields"
    engine: pandas # Mappage par ligne simple
    action: map
    # Déclare le flux de sortie de cette étape (qui devient l'entrée de l'étape suivante ou la sortie finale)
    output_schema:
      transaction_date: report_date
      quantity: total_quantity
      product_id: product_id
      status: transaction_status
```

### Exemple 2 : Moyennement Complexe (Transformation simple + Mappage)

- **Scénario :** Calculer un nouveau champ, filtrer des lignes, puis mapper vers la destination.

- **Moteur utilisé :** Pandas (calculs par ligne et filtrage).

YAML

```
version: "1.0"
pipeline:
  name: "calculated_and_filtered"
  source: "csv_transactions"
  destination: "mariadb_revenue_report"

steps:
  # 1. Calcul du revenu (produit de deux colonnes)
  - name: "calculate_revenue"
    engine: pandas
    action: compute
    fields:
      # 'expr' est un DSL simple, interprété par Pandas
      line_revenue: 
        expr: "quantity * unit_price"
        type: float

  # 2. Filtrage des lignes annulées
  - name: "filter_cancelled"
    engine: pandas
    action: filter
    # 'where' est un DSL conditionnel simple interprété par Pandas
    where: "status != 'CANCELLED' AND line_revenue > 0"

  # 3. Mappage et sélection finale vers la destination
  - name: "final_map_and_select"
    engine: pandas
    action: map
    output_schema:
      transaction_date: report_date
      line_revenue: total_revenue
      product_id: product_id
      # 'quantity' et 'status' sont exclus
```

### Exemple 3 : Complexe Hybride (Jointure + Agrégation)

- **Scénario :** Joindre les transactions (CSV) avec le catalogue (MySQL), calculer le revenu, puis agréger le revenu total par date.

- **Moteur utilisé :** **DuckDB** (Jointure et Agrégation).

YAML

```
version: "1.0"
pipeline:
  name: "full_revenue_aggregation"

steps:
  # 1. Joindre les deux sources
  - name: "join_transactions_and_catalogue"
    # L'Engine utilise DuckDB. Les sources sont des "tables" DuckDB temporaires.
    engine: duckdb
    action: sql
    query: |      -- Utilisation du SQL natif de DuckDB      SELECT         t.transaction_date,        t.quantity,        c.unit_price,        c.name AS product_name       FROM         csv_transactions AS t  -- 'csv_transactions' référence la source nommée dans source.yaml      JOIN         mysql_catalogue AS c   -- 'mysql_catalogue' référence la source nommée dans source.yaml      ON         t.product_id = c.product_id

  # 2. Agrégation finale
  - name: "aggregate_daily_revenue"
    engine: duckdb
    action: sql
    # Le 'FROM' fait référence au flux de données produit par l'étape précédente (join_transactions_and_catalogue)
    query: |      SELECT        transaction_date AS report_date,        SUM(quantity * unit_price) AS daily_revenue,        COUNT(*) AS total_transactions      FROM        "{{ last_step_output }}" -- Référence au flux de données de l'étape 1      GROUP BY        report_date      ORDER BY        report_date DESC

  # La sortie de l'étape 2 est le flux de chargement (Load)
```

Ces propositions respectent tous vos critères :

- **Simplicité & Clarté :** Utilisation de YAML lisible avec des `steps` séquentielles.

- **Modularité :** Références aux sources et destinations par nom.

- **Adaptabilité Pandas/DuckDB :** Définie par le champ `engine:`.

- **Fluidité Déclaratif/Impératif :** Le DSL ( `map`, `compute`, `filter`) est déclaratif, mais le `query:` SQL est impératif pour DuckDB, donnant le contrôle quand c'est nécessaire.

- **Découplage :** Trois fichiers clairs.

Quelles sont vos suggestions d'ajustements sur ce DSL minimal pour que nous puissions valider la structure définitive pour vos Parsers ?
