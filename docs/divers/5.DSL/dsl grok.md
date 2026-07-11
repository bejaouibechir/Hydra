**DSL ETL – Version finale, pragmatique et évolutive (2025-ready)**  
Objectifs respectés à 100 % : simple, clair, modulaire, adapté pandas + DuckDB, passage déclaratif → impératif fluide, découplage total sources / transforms / destinations.

### 1. Transformations possibles + mapping moteur (tableau de décision interne)

| Catégorie         | Opération DSL                  | Moteur choisi    | Pourquoi                                                       |
| ----------------- | ------------------------------ | ---------------- | -------------------------------------------------------------- |
| Chargement        | `load`                         | Connecteur       | Charge une source dans un flux nommé                           |
| Filtre            | `filter`                       | pandas ou DuckDB | pandas si petit, DuckDB sinon                                  |
| Mapping colonnes  | `select` / `drop` / `rename`   | pandas           | Ultra rapide en pandas                                         |
| Calculs simples   | `calculate`                    | pandas           | Vectorisé, expressions Python-like                             |
| Nettoyage         | `clean`, `replace`, `coalesce` | pandas           | Regex, trim, fillna, etc.                                      |
| Split / branching | `split` → plusieurs outputs    | pandas / DuckDB  | Branching explicite                                            |
| Jointures         | `join`, `lookup`               | DuckDB           | Toujours, même si petites tables (DuckDB gère tout en mémoire) |
| Agrégations       | `aggregate`                    | DuckDB           | GROUP BY, window functions                                     |
| Union             | `union` / `union_all`          | DuckDB           |                                                                |
| Déduplication     | `distinct`                     | DuckDB           |                                                                |
| Fenêtres          | `window`                       | DuckDB           | row_number, rank, moving average…                              |
| Custom Python     | `python`                       | pandas           | Code impératif si déclaratif insuffisant                       |
| Écriture          | `write`                        | Connecteur       | Envoie un flux nommé vers une destination                      |

### 2. Structure définitive des fichiers (découplage conservé)

```
job/
├── sources.yaml          ← toutes les sources du job
├── destinations.yaml     ← toutes les destinations du job  
└── pipeline.yaml         ← séquence complète des étapes (le vrai DSL)
```

### 3. Le DSL final – pipeline.yaml

Syntaxe ultra-lisible, tout en restant puissante.

```yaml
# pipeline.yaml

# 1. Chargement des sources (création de flux nommés)
stages:
  - load: customers
    from: src_customers          # réf vers sources.yaml
    into: cust                    # nom du flux interne

  - load: orders
    from: src_orders
    into: ord

# 2. Transformations pandas (simples & rapides)
  - calculate:
      input: ord
      columns:
        total_ht:   "quantity * unit_price"
        tax:       "total_ht * 0.20"
        total_ttc:  "total_ht + tax"
      output: ord_enriched

  - clean:
      input: ord_enriched
      rules:
        - column: email
          trim: true
          lower: true
          replace:
            "null": null
            "": null
      output: ord_clean

# 3. Transformations DuckDB (ensemblistes)
  - join:
      left: cust
      right: ord_clean
      on: customer_id
      how: inner
      output: sales_full

  - aggregate:
      input: sales_full
      by: [country, year_month]
      metrics:
        revenue: "SUM(total_ttc)"
        orders:  "COUNT(*)"
        avg_basket: "AVG(total_ttc)"
      output: monthly_kpi

  - window:
      input: sales_full
      partition_by: customer_id
      order_by: order_date
      functions:
        rank: "ROW_NUMBER()"
        moving_avg_3: "AVG(total_ttc) OVER (PARTITION BY customer_id ORDER BY order_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)"
      output: sales_with_rank

# 4. Split & routing
  - split:
      # exemple branchement
      input: sales_full
      branches:
        france:
          filter: "country = 'FR'"
          output: sales_fr
        export:
          filter: "country != 'FR'"
          output: sales_export

# 5. Custom Python impératif (quand tu as besoin)
  - python:
      input: sales_fr
      code: |
        df['segment'] = df['total_ttc'].apply(lambda x: 'VIP' if x > 5000 else 'Standard')
      output: sales_fr_segmented

# 6. Écriture vers destinations
  - write: sales_fr_segmented
    to: dest_analytics_fr
    mode: upsert
    key: [order_id]

  - write: sales_export
    to: dest_warehouse
    mode: truncate_then_load

  - write: monthly_kpi
    to: dest_reporting
    mode: replace
```

### 4. Exemples demandés

#### Exemple 1 – Ultra simple (mapping colonnes)

```yaml
# pipeline.yaml
stages:
  - load: legacy_users → into: users
  - select:
      input: users
      columns:
        id: user_id
        name: full_name
        email: email_address
      drop_others: true
      output: clean_users
  - write: clean_users → to: mysql_users (mode: upsert, key: id)
```

#### Exemple 2 – Moyen (pandas + plusieurs destinations)

```yaml
stages:
  - load: transactions → into: tx
  - calculate:
      input: tx
      columns:
        amount_eur: "amount_usd * 0.92"
        fee: "amount_eur * 0.01"
      output: tx_fee
  - clean:
      input: tx_fee
      rules:
        - column: status
          replace: { "P": "paid", "R": "refunded" }
      output: tx_final
  - write: tx_final → to: dwh_transactions (upsert)
  - write: tx_final → to: realtime_kafka (mode: append)
```

#### Exemple 3 – Complexe pandas (split + multi-dest)

```yaml
stages:
  - load: all_events → into: events
  - split:
      input: events
      branches:
        login:   { filter: "event_type = 'login'" }
        purchase:{ filter: "event_type = 'purchase'" }
        other:   { filter: "true" }   # default
      outputs: [logins, purchases, others]
  - write: logins    → to: analytics_logins
  - write: purchases → to: finance_purchases
  - write: others    → to: debug_sink
```

#### Exemple 4 – Complexe DuckDB (joins + fenêtre + multi-dest)

```yaml
stages:
  - load: orders    → into: o
  - load: customers → into: c
  - load: products  → into: p

  - join:  [o, c] on customer_id → temp1
  - join:  [temp1, p] on product_id → sales_full

  - window:
      input: sales_full
      partition_by: customer_id
      order_by: order_date
      functions:
        customer_rank: "ROW_NUMBER()"
        ltv_90d: "SUM(amount) OVER (PARTITION BY customer_id ORDER BY order_date RANGE BETWEEN INTERVAL 90 DAYS PRECEDING AND CURRENT ROW)"
      output: sales_ranked

  - aggregate:
      input: sales_ranked
      by: [country]
      metrics:
        revenue: SUM(amount)
        top_customers: COUNT(DISTINCT CASE WHEN customer_rank <= 10 THEN customer_id END)
      output: country_report

  - write: sales_ranked  → to: dwh_sales (upsert key=order_id)
  - write: country_report → to: bi_dashboard (replace)
```

### 5. Suggestions finales (les 3 règles d’or à graver)

1. Un seul fichier pipeline.yaml qui orchestre tout (mais références sources.yaml / destinations.yaml)
2. Tous les flux sont nommés (into / output) → traçabilité parfaite
3. Moteur choisi automatiquement :
   - si étape contient join / aggregate / window / union → DuckDB
   - sinon → pandas

Voici les **sources.yaml** et **destinations.yaml** complets et cohérents pour les **4 exemples** du DSL qu’on vient de valider.

Tu n’as plus qu’à créer le dossier `job_mon_preprod/` et y mettre ces 3 fichiers + le `pipeline.yaml` correspondant → tout fonctionne immédiatement.

### Fichiers communs à tous les exemples (réutilisables)

```yaml
# sources.yaml
sources:
  # ──────── Bases de données ────────
  src_legacy:
    type: mysql
    host: ${ENV:LEGACY_DB_HOST}
    port: 3306
    database: legacy_app
    user: ${ENV:LEGACY_DB_USER}
    password: ${SECRET:LEGACY_DB_PASSWORD}
    schema: public

  src_sales_db:
    type: mysql
    host: ${ENV:SALES_DB_HOST}
    port: 3306
    database: sales
    user: ${ENV:SALES_DB_USER}
    password: ${SECRET:SALES_DB_PASSWORD}

  src_analytics:
    type: mariadb
    host: ${ENV:ANALYTICS_DB_HOST}
    port: 3306
    database: analytics_warehouse
    user: ${ENV:ANALYTICS_DB_USER}
    password: ${SECRET:ANALYTICS_DB_PASSWORD}

  # ──────── Fichiers plats ────────
  src_transactions_csv:
    type: csv
    path: /data/in/transactions_{{ execution_date | strftime("%Y%m%d") }}.csv
    delimiter: ","
    has_header: true
    encoding: utf-8

  src_events_json:
    type: json
    path: /data/in/events/stream_{{ execution_date }}.jsonl
    format: jsonlines

  src_customers:
    type: mysql
    host: ${ENV:SALES_DB_HOST}
    database: sales
    table: customers

  src_orders:
    type: mysql
    host: ${ENV:SALES_DB_HOST}
    database: sales
    table: orders

  src_products:
    type: mysql
    host: ${ENV:SALES_DB_HOST}
    database: sales
    table: products
```

```yaml
# destinations.yaml
destinations:
  # ──────── Bases cibles ────────
  mysql_users:
    type: mysql
    host: ${ENV:ANALYTICS_DB_HOST}
    database: analytics_warehouse
    table: dim_users
    batch_size: 10000

  dwh_transactions:
    type: mariadb
    host: ${ENV:ANALYTICS_DB_HOST}
    database: analytics_warehouse
    table: fact_transactions
    batch_size: 15000

  realtime_kafka:
    type: kafka
    bootstrap_servers: ${ENV:KAFKA_BROKERS}
    topic: transactions_enriched
    serialization: json

  analytics_logins:
    type: mariadb
    table: audit_logins
    batch_size: 5000

  finance_purchases:
    type: mariadb
    table: finance_purchases
    batch_size: 8000

  debug_sink:
    type: csv
    path: /data/debug/others_{{ execution_date }}.csv
    mode: overwrite

  dwh_sales:
    type: mariadb
    table: fact_sales_enriched
    batch_size: 20000

  bi_dashboard:
    type: mariadb
    table: rpt_country_monthly
    mode: replace

  dest_analytics_fr:
    type: mariadb
    table: fact_sales_fr
    batch_size: 10000

  dest_warehouse:
    type: mariadb
    table: fact_sales_export
    batch_size: 15000

  dest_reporting:
    type: mariadb
    table: rpt_monthly_kpi
    mode: replace
```

### Exemple 1 – Ultra simple

```yaml
# pipeline.yaml – mapping colonnes uniquement
stages:
  - load: legacy_users
    from: src_legacy
    query: SELECT user_id, full_name, email_address FROM users
    into: users_raw

  - select:
      input: users_raw
      columns:
        id: user_id
        name: full_name
        email: email_address
      drop_others: true
      output: clean_users

  - write: clean_users
    to: mysql_users
    mode: upsert
    key: [id]
```

### Exemple 2 – Moyen (pandas + multi-dest)

```yaml
# pipeline.yaml
stages:
  - load: transactions
    from: src_transactions_csv
    into: tx

  - calculate:
      input: tx
      columns:
        amount_eur: "amount_usd * 0.92"
        fee: "amount_eur * 0.01"
      output: tx_fee

  - clean:
      input: tx_fee
      rules:
        - column: status
          replace: { "P": "paid", "R": "refunded", "": null }
      output: tx_final

  - write: tx_final
    to: dwh_transactions
    mode: upsert
    key: [transaction_id]

  - write: tx_final
    to: realtime_kafka
    mode: append
```

### Exemple 3 – Complexe pandas (split + multi-dest)

```yaml
# pipeline.yaml
stages:
  - load: all_events
    from: src_events_json
    into: events

  - split:
      input: events
      branches:
        login:
          filter: "event_type == 'login'"
          output: logins
        purchase:
          filter: "event_type == 'purchase'"
          output: purchases
        other:
          filter: "True"
          output: others

  - write: logins
    to: analytics_logins
    mode: append

  - write: purchases
    to: finance_purchases
    mode: upsert
    key: [event_id]

  - write: others
    to: debug_sink
```

### Exemple 4 – Complexe DuckDB (joins + window + multi-dest)

```yaml
# pipeline.yaml
stages:
  - load: customers   from: src_customers   into: c
  - load: orders      from: src_orders      into: o
  - load: products    from: src_products    into: p

  - join:
      left: o
      right: c
      on: customer_id
      how: inner
      output: o_c

  - join:
      left: o_c
      right: p
      on: product_id
      how: left
      output: sales_full

  - calculate:
      input: sales_full
      columns:
        total_ttc: "quantity * unit_price * 1.20"
      output: sales_calc

  - window:
      input: sales_calc
      partition_by: customer_id
      order_by: order_date
      functions:
        rank: "ROW_NUMBER()"
        ltv_90d: "SUM(total_ttc) OVER (PARTITION BY customer_id ORDER BY order_date RANGE BETWEEN INTERVAL 90 DAYS PRECEDING AND CURRENT ROW)"
      output: sales_ranked

  - aggregate:
      input: sales_ranked
      by: [country, DATE_TRUNC('month', order_date) AS month]
      metrics:
        revenue: SUM(total_ttc)
        customers: COUNT(DISTINCT customer_id)
      output: monthly_kpi

  - write: sales_ranked
    to: dwh_sales
    mode: upsert
    key: [order_id]

  - write: monthly_kpi
    to: dest_reporting
    mode: replace
```

Tu as maintenant **tout le trio complet** (sources + destinations + pipeline) pour chaque niveau de complexité.  C'est la phase la plus importante : la conception du **DSL (Domain-Specific Language)** dans les manifestes YAML. Ce langage sera l'interface utilisateur de votre ETL et la fondation de tout le développement du `Parser` et du `Transformation Engine`.

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
