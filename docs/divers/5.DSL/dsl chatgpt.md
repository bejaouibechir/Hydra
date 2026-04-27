Très bien, on attaque le DSL proprement.

Je vais faire en deux temps :

1. **Catalogue des transformations** avec **équivalent Pandas / DuckDB**

2. **4 exemples YAML complets** (source / destination / transform)
   
   - simple
   
   - moyen
   
   - “+ complexe” orienté **Pandas**
   
   - “+ complexe” orienté **DuckDB**

---

## 1. Catalogue des transformations + mapping Pandas / DuckDB

Je pars des transformations les plus utiles et fréquentes.  
L’idée : chaque type de transformation deviendra un `op:` dans le DSL.

### 1.1. Projection / sélection de colonnes

- **Concept** : garder uniquement certaines colonnes.

- **Pandas**
  
  ```python
  df = df[["id", "order_date", "amount"]]
  ```

- **DuckDB**
  
  ```sql
  SELECT id, order_date, amount FROM t;
  ```

---

### 1.2. Renommage de colonnes

- **Concept** : changer les noms pour coller au schéma destination.

- **Pandas**
  
  ```python
  df = df.rename(columns={"old_name": "new_name"})
  ```

- **DuckDB**
  
  ```sql
  SELECT old_name AS new_name FROM t;
  ```

---

### 1.3. Cast / changement de type

- **Concept** : convertir types (string → int, string → date, etc.).

- **Pandas**
  
  ```python
  df["amount"] = df["amount"].astype("float")
  df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
  ```

- **DuckDB**
  
  ```sql
  SELECT CAST(amount AS DOUBLE), CAST(date AS DATE) FROM t;
  ```

---

### 1.4. Filtre / WHERE

- **Concept** : garder uniquement les lignes qui respectent une condition.

- **Pandas**
  
  ```python
  df = df[df["status"] == "completed"]
  ```

- **DuckDB**
  
  ```sql
  SELECT * FROM t WHERE status = 'completed';
  ```

---

### 1.5. Colonne calculée (expression)

- **Concept** : créer une nouvelle colonne à partir d’autres.

- **Pandas**
  
  ```python
  df["total"] = df["quantity"] * df["unit_price"]
  ```

- **DuckDB**
  
  ```sql
  SELECT quantity * unit_price AS total FROM t;
  ```

---

### 1.6. Nettoyage simple (trim, lower, replace)

- **Pandas**
  
  ```python
  df["code"] = df["code"].str.strip().str.lower()
  df["code"] = df["code"].str.replace("852c", "852", regex=False)
  ```

- **DuckDB**
  
  ```sql
  SELECT
    lower(trim(code)) AS code_clean,
    replace(code, '852c', '852') AS code_repl
  FROM t;
  ```

---

### 1.7. Remplacement de valeurs / mapping

- **Pandas**
  
  ```python
  df["status"] = df["status"].replace({"C": "completed", "P": "pending"})
  ```

- **DuckDB**
  
  ```sql
  SELECT
    CASE status
      WHEN 'C' THEN 'completed'
      WHEN 'P' THEN 'pending'
      ELSE status
    END AS status
  FROM t;
  ```

---

### 1.8. Gestion des NULL / valeurs manquantes

- **Pandas**
  
  ```python
  df["amount"] = df["amount"].fillna(0)
  df = df.dropna(subset=["id"])
  ```

- **DuckDB**
  
  ```sql
  SELECT COALESCE(amount, 0) AS amount FROM t;
  -- ou
  SELECT * FROM t WHERE id IS NOT NULL;
  ```

---

### 1.9. Jointure (JOIN)

- **Concept** : joindre plusieurs sources sur une clé.

- **Pandas**
  
  ```python
  df = df_orders.merge(df_customers, on="customer_id", how="left")
  ```

- **DuckDB**
  
  ```sql
  SELECT *
  FROM orders o
  LEFT JOIN customers c ON o.customer_id = c.customer_id;
  ```

---

### 1.10. Agrégation / group by

- **Pandas**
  
  ```python
  agg = (
    df.groupby("customer_id")
      .agg(total=("amount", "sum"), avg=("amount", "mean"))
      .reset_index()
  )
  ```

- **DuckDB**
  
  ```sql
  SELECT customer_id,
         SUM(amount) AS total,
         AVG(amount) AS avg
  FROM t
  GROUP BY customer_id;
  ```

---

### 1.11. Union / concat

- **Pandas**
  
  ```python
  df = pd.concat([df1, df2], ignore_index=True)
  ```

- **DuckDB**
  
  ```sql
  SELECT * FROM t1
  UNION ALL
  SELECT * FROM t2;
  ```

---

### 1.12. Tri (sort)

- **Pandas**
  
  ```python
  df = df.sort_values(by=["order_date", "customer_id"])
  ```

- **DuckDB**
  
  ```sql
  SELECT * FROM t ORDER BY order_date, customer_id;
  ```

---

### 1.13. Fonctions fenêtre (plutôt DuckDB)

- **Pandas** (via `rolling` ou `expanding`, plus verbeux)

- **DuckDB** (très naturel)
  
  ```sql
  SELECT
    customer_id,
    order_date,
    amount,
    AVG(amount) OVER (
      PARTITION BY customer_id
      ORDER BY order_date
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3
  FROM t;
  ```

---

### 1.14. Split / branches de pipeline

- Concept DSL :
  
  - `split` = produire plusieurs “vues” à partir d’une même source/pipeline.
  
  - En pratique :
    
    - Pandas → plusieurs DataFrames
    
    - DuckDB → plusieurs tables temporaires / CTE.

---

Avec ce catalogue, on a de quoi définir un **DSL simple** avec des `steps` comme :

- `select_columns`

- `rename_columns`

- `cast_columns`

- `filter`

- `compute_column`

- `clean_column`

- `replace_values`

- `join`

- `aggregate`

- `union`

- `sort`

- `split`

Et chaque step pourra être exécutée en **Pandas ou DuckDB** selon un `backend` (`pandas`, `duckdb`, `auto`).

---

## 2. Exemples DSL en YAML (source / destination / transform)

Je propose une forme simple :

- `sources.yaml`

- `destinations.yaml`

- `transform.yaml`

Avec un style :

```yaml
pipeline:
  name: ...
  backend: auto | pandas | duckdb
  steps:
    - op: ...
      ...
```

Je commente dans le YAML pour que ce soit clair.

---

### 2.1. Exemple simple

**Source → Destination, mapping minimal**

#### `sources.yaml`

```yaml
version: "1.0"

sources:
  - name: "sales_csv"
    type: "csv"
    options:
      path: "./data/sales.csv"      # chemin du fichier source
      delimiter: ","               # séparateur CSV
      header: true                 # première ligne = noms de colonnes
    schema:
      columns:
        - name: "id"
          type: "int"
        - name: "date_cmd"
          type: "string"
        - name: "client"
          type: "string"
        - name: "montant_ht"
          type: "string"           # sera casté plus tard
```

#### `destinations.yaml`

```yaml
version: "1.0"

destinations:
  - name: "sales_clean_db"
    type: "mariadb"
    options:
      connection: "${SECRETS.MARIADB_DSN}"   # DSN dans les secrets
    target:
      schema: "etl_demo"
      table: "sales_clean"
      columns:
        - name: "id"
          type: "int"
        - name: "order_date"
          type: "date"
        - name: "customer_name"
          type: "string"
        - name: "amount_ht"
          type: "decimal(10,2)"
```

#### `transform.yaml` (simple mapping)

```yaml
version: "1.0"

pipeline:
  name: "sales_simple_mapping"
  backend: "auto"        # moteur choisi automatiquement

  source: "sales_csv"    # nom défini dans sources.yaml
  destination: "sales_clean_db"

  steps:
    - op: "select_columns"
      columns: ["id", "date_cmd", "client", "montant_ht"]

    - op: "rename_columns"
      mapping:
        date_cmd: "order_date"
        client: "customer_name"
        montant_ht: "amount_ht"

    - op: "cast_columns"
      columns:
        amount_ht:
          type: "decimal"
          precision: 10
          scale: 2
        order_date:
          type: "date"
          format: "%Y-%m-%d"

    - op: "map_to_destination"   # étape logique : aligner sur le schéma cible
      destination: "sales_clean_db"
```

---

### 2.2. Exemple moyennement complexe

**Source → plusieurs petites transformations → mapping vers destination**

#### `sources.yaml`

On réutilise `sales_csv`.

#### `destinations.yaml`

```yaml
version: "1.0"

destinations:
  - name: "sales_clean_db"
    type: "mariadb"
    options:
      connection: "${SECRETS.MARIADB_DSN}"
    target:
      schema: "etl_demo"
      table: "sales_clean"
      columns:
        - name: "id"
        - name: "order_date"
        - name: "customer_name"
        - name: "amount_ht"
        - name: "status"
```

#### `transform.yaml`

Objectifs :

- filtrer sur `status = 'completed'`

- nettoyer codes (trim/lower)

- calcul simple + mapping

```yaml
version: "1.0"

pipeline:
  name: "sales_medium_pipeline"
  backend: "auto"

  source: "sales_csv"
  destination: "sales_clean_db"

  steps:
    - op: "select_columns"
      columns: ["id", "date_cmd", "client", "montant_ht", "status_raw"]

    - op: "clean_column"
      column: "status_raw"
      actions:
        - "strip"
        - "lower"
      as: "status"

    - op: "filter"
      condition: "status == 'completed'"
      backend_hint: "pandas"       # filtre simple → pandas ou auto

    - op: "rename_columns"
      mapping:
        date_cmd: "order_date"
        client: "customer_name"
        montant_ht: "amount_ht"

    - op: "cast_columns"
      columns:
        amount_ht:
          type: "decimal"
          precision: 10
          scale: 2
        order_date:
          type: "date"
          format: "%Y-%m-%d"

    - op: "map_to_destination"
      destination: "sales_clean_db"
```

---

### 2.3. Exemple “+ complexe” orienté **Pandas**

**Sources → split → plusieurs destinations**  
Cas typique :

- une source de transactions,

- split en deux jeux : commandes récentes / anciennes.

#### `sources.yaml`

```yaml
version: "1.0"

sources:
  - name: "orders_csv"
    type: "csv"
    options:
      path: "./data/orders.csv"
      delimiter: ";"
      header: true
    schema:
      columns:
        - name: "order_id"
        - name: "order_date"
        - name: "customer_id"
        - name: "amount"
```

#### `destinations.yaml`

```yaml
version: "1.0"

destinations:
  - name: "recent_orders"
    type: "mariadb"
    options:
      connection: "${SECRETS.MARIADB_DSN}"
    target:
      schema: "etl_demo"
      table: "recent_orders"

  - name: "old_orders"
    type: "mariadb"
    options:
      connection: "${SECRETS.MARIADB_DSN}"
    target:
      schema: "etl_demo"
      table: "old_orders"
```

#### `transform.yaml`

On force **Pandas** parce qu’on va utiliser une logique basée sur dates et splits en mémoire.

```yaml
version: "1.0"

pipeline:
  name: "orders_split_pandas"
  backend: "pandas"          # force le moteur pandas

  source: "orders_csv"

  steps:
    - op: "cast_columns"
      columns:
        order_date:
          type: "date"
          format: "%Y-%m-%d"
        amount:
          type: "float"

    - op: "compute_column"
      # Ex : flag pour repérer les commandes récentes (30 derniers jours)
      column: "is_recent"
      expression: "order_date >= today() - timedelta(days=30)"
      backend_hint: "pandas"

    - op: "split"            # crée deux branches logiques
      branches:
        - name: "recent"
          filter: "is_recent == True"
        - name: "old"
          filter: "is_recent == False"

    # branche "recent"
    - op: "branch"
      name: "recent"
      steps:
        - op: "select_columns"
          columns: ["order_id", "order_date", "customer_id", "amount"]
        - op: "map_to_destination"
          destination: "recent_orders"

    # branche "old"
    - op: "branch"
      name: "old"
      steps:
        - op: "select_columns"
          columns: ["order_id", "order_date", "customer_id", "amount"]
        - op: "map_to_destination"
          destination: "old_orders"
```

Ici la logique est très naturelle à implémenter en Pandas (split en deux DataFrames).

---

### 2.4. Exemple “+ complexe” orienté **DuckDB**

**Multi-sources → joins + agrégations → multi-destinations**

Cas :

- `orders` (CSV ou MySQL)

- `customers` (MySQL)

- on produit :
  
  - une table “detail joined”
  
  - une table “monthly summary par client”

#### `sources.yaml`

```yaml
version: "1.0"

sources:
  - name: "orders_db"
    type: "mysql"
    options:
      connection: "${SECRETS.MYSQL_ORDERS}"
    schema:
      table: "orders"

  - name: "customers_db"
    type: "mysql"
    options:
      connection: "${SECRETS.MYSQL_CUSTOMERS}"
    schema:
      table: "customers"
```

#### `destinations.yaml`

```yaml
version: "1.0"

destinations:
  - name: "orders_enriched"
    type: "mariadb"
    options:
      connection: "${SECRETS.MARIADB_DW}"
    target:
      schema: "dw"
      table: "orders_enriched"

  - name: "monthly_sales"
    type: "mariadb"
    options:
      connection: "${SECRETS.MARIADB_DW}"
    target:
      schema: "dw"
      table: "monthly_sales"
```

#### `transform.yaml`

On force **DuckDB** pour bénéficier des joins + agrégations SQL.

```yaml
version: "1.0"

pipeline:
  name: "orders_customers_duckdb"
  backend: "duckdb"        # on veut explicitement passer par DuckDB

  sources:
    - "orders_db"
    - "customers_db"

  steps:
    - op: "register_source"
      name: "orders"
      from: "orders_db"        # alias interne dans DuckDB

    - op: "register_source"
      name: "customers"
      from: "customers_db"

    - op: "compute_column"
      # calcul total = quantity * unit_price
      column: "total_amount"
      expression: "quantity * unit_price"
      from: "orders"
      backend_hint: "duckdb"

    - op: "join"
      left: "orders"
      right: "customers"
      on:
        - left_key: "customer_id"
          right_key: "id"
      how: "left"
      as: "orders_joined"

    - op: "select_columns"
      from: "orders_joined"
      columns:
        - "order_id"
        - "order_date"
        - "customer_id"
        - "customers.name AS customer_name"
        - "total_amount"
      as: "orders_enriched_view"

    - op: "aggregate"
      from: "orders_enriched_view"
      as: "monthly_sales_view"
      group_by:
        - "customer_id"
        - "DATE_TRUNC('month', order_date) AS month"
      metrics:
        total_sales: "SUM(total_amount)"
        avg_order: "AVG(total_amount)"

    # mapping vers les destinations

    - op: "map_to_destination"
      from: "orders_enriched_view"
      destination: "orders_enriched"

    - op: "map_to_destination"
      from: "monthly_sales_view"
      destination: "monthly_sales"
```

Ici, tout est très naturel pour DuckDB : `register_source` crée des tables temporaires, puis le moteur traduit ces steps en SQL complet avec CTE.

---

## Conclusion / suggestions (très bref)

- Le DSL peut rester **simple** : une liste de `steps`, chacune avec un `op`, des paramètres clairs, et un `backend_hint` optionnel.

- La **modularité** est gérée via `split` + `branch` + `register_source` + `as:` (vues intermédiaires).

- L’**adaptabilité Pandas / DuckDB** est gérée par :
  
  - `pipeline.backend` (`auto`, `pandas`, `duckdb`)
  
  - `backend_hint` par step si besoin de forcer.

- Le **découplage source / transform / destination** est respecté avec 3 fichiers YAML distincts.

Si tu veux, on peut maintenant **figer la grammaire exacte** (schéma YAML / JSON Schema) du DSL pour chaque `op` (`select_columns`, `filter`, `join`, etc.) et en faire une première spécification formelle.
