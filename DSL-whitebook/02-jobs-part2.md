<!-- Hydra DSL White Paper — Chapter 2 (part 2): Jobs — Transformations, Engines, Expressions
     DSL format version: 1.0 · Hydra 0.16.0
     Sources: internal/parser/transform.py, internal/engines/{pandas_engine,large_volume,expr_engine}.py,
     internal/runner/executor.py, hydra_etl/_backend.py -->

# Hydra DSL - Transformations

`transformations.yaml` lists the operations applied to the data between the source and the destination, **in order**.

## Syntax

```yaml
version: "1.0"
transformations:
  engine: auto            # optional: auto | pandas | duckdb
  steps:
    - <operation>:
        <parameters>
    - <operation>:
        <parameters>
```

> **[FIGURE fig-02-07 · diagram]** A table flowing through a list of steps, each step drawn as a box that changes the table (columns removed, rows filtered, a column added), from top to bottom.

## Rules for transformations

- `steps` is a list with **at least one** step.
- Each step has **exactly one key**: the name of the operation.
- The parameters of an operation are always a mapping, even when there is only one.
- Steps run from top to bottom. Each step receives the result of the previous one.
- An unknown operation is refused before the job starts.
- A column that does not exist is reported with the list of available columns.

## The 18 operations

| Family      | Operations                                                         |
| ----------- | ------------------------------------------------------------------ |
| Columns     | `select` · `rename` · `cast`                                       |
| Rows        | `filter` · `sort` · `deduplicate` · `fill_null` · `trim` · `clean` |
| Calculation | `calculate` · `script`                                             |
| Aggregation | `aggregate`                                                        |
| Combining   | `join` · `merge` · `union`                                         |
| Reshaping   | `pivot` · `unpivot` · `transpose`                                  |

No other operation exists.

All the examples of this chapter start from this table, `orders`:

| id  | customer_id | country | amount | status    |
| --- | ----------- | ------- | ------ | --------- |
| 1   | 100         | FR      | 120.0  | paid      |
| 2   | 101         | BE      | 80.0   | cancelled |
| 3   | 100         | FR      | 45.5   | paid      |
| 4   | 102         | DE      |        | paid      |

> **[GITHUB gh-02-04 · example]** **transformations_playground** — One job folder per operation of this chapter, all reading the same `orders.csv`, each with its expected output, to run and compare.

---

# Hydra DSL - Column Operations

## select

Keeps only the listed columns, in the given order.

| Parameter | Required | Description             |
| --------- | -------- | ----------------------- |
| `columns` | Yes      | List of columns to keep |

```yaml
- select:
    columns: [id, country, amount]
```

| id  | country | amount |
| --- | ------- | ------ |
| 1   | FR      | 120.0  |
| 2   | BE      | 80.0   |
| …   | …       | …      |

## rename

| Parameter | Required | Description          |
| --------- | -------- | -------------------- |
| `mapping` | Yes      | `old_name: new_name` |

```yaml
- rename:
    mapping:
      customer_id: client_id
      amount: total_eur
```

## cast

Converts the type of columns.

| Parameter | Required | Description    |
| --------- | -------- | -------------- |
| `mapping` | Yes      | `column: type` |

| Type       | Result                           |
| ---------- | -------------------------------- |
| `int`      | Integer. Empty values stay empty |
| `float`    | Decimal number                   |
| `str`      | Text                             |
| `bool`     | True / false                     |
| `datetime` | Date and time                    |

```yaml
- cast:
    mapping:
      id: int
      amount: float
      created_at: datetime
```

> A value that cannot be converted stops the job, with the column, the type and the reason.

<!-- REVIEW (décision I) : le parseur accepte `date`, mais le moteur le refuse
     (« Type non supporté »). `date` non documenté tant que ce n'est pas corrigé.
     Les alias integer/string/boolean sont refusés par le parseur. -->

---

# Hydra DSL - Row Operations

## filter

Keeps the rows for which the expression is true.

| Parameter | Required | Description                     |
| --------- | -------- | ------------------------------- |
| `expr`    | Yes      | A condition (see *Expressions*) |

### Example 1: a simple condition

```yaml
- filter:
    expr: "amount > 50"
```

| id  | customer_id | country | amount | status    |
| --- | ----------- | ------- | ------ | --------- |
| 1   | 100         | FR      | 120.0  | paid      |
| 2   | 101         | BE      | 80.0   | cancelled |

### Example 2: several conditions

```yaml
- filter:
    expr: "status == 'paid' and country in ['FR', 'DE']"
```

| id  | customer_id | country | amount | status |
| --- | ----------- | ------- | ------ | ------ |
| 1   | 100         | FR      | 120.0  | paid   |
| 3   | 100         | FR      | 45.5   | paid   |
| 4   | 102         | DE      |        | paid   |

### Example 3: exclude

```yaml
- filter:
    expr: "not (status == 'cancelled')"
```

## sort

| Parameter   | Default | Description                              |
| ----------- | ------- | ---------------------------------------- |
| `by`        | –       | Columns to sort by. Required             |
| `ascending` | `true`  | `true`, `false`, or one value per column |

```yaml
- sort:
    by: [amount]
    ascending: false
```

```yaml
# country A→Z, then amount from highest to lowest
- sort:
    by: [country, amount]
    ascending: [true, false]
```

Rows with equal values keep their original order.

## deduplicate

| Parameter | Default     | Description                     |
| --------- | ----------- | ------------------------------- |
| `columns` | all columns | Columns that define a duplicate |
| `keep`    | `first`     | `first` or `last` occurrence    |

```yaml
# one row per customer, the last one seen
- deduplicate:
    columns: [customer_id]
    keep: last
```

| id  | customer_id | country | amount | status    |
| --- | ----------- | ------- | ------ | --------- |
| 2   | 101         | BE      | 80.0   | cancelled |
| 3   | 100         | FR      | 45.5   | paid      |
| 4   | 102         | DE      |        | paid      |

## fill_null

Replaces empty values.

| Parameter | Description                                   |
| --------- | --------------------------------------------- |
| `value`   | One value for every column                    |
| `columns` | A different value per column: `column: value` |

One of the two is required.

```yaml
- fill_null:
    value: 0
```

```yaml
- fill_null:
    columns:
      amount: 0
      country: "UNKNOWN"
```

## trim

Removes the spaces at the start and end of text values.

| Parameter | Default          | Description     |
| --------- | ---------------- | --------------- |
| `columns` | all text columns | Columns to trim |

```yaml
- trim:
    columns: [country, status]
```

## clean

Normalises text: removes the spaces at the start and end, replaces repeated spaces with one, and optionally changes the case.

| Parameter | Default          | Description                |
| --------- | ---------------- | -------------------------- |
| `columns` | all text columns | Columns to clean           |
| `case`    | `none`           | `none` · `lower` · `upper` |

```yaml
- clean:
    columns: [status]
    case: upper
```

| Before           | After          |
| ---------------- | -------------- |
| `"  paid "`      | `"PAID"`       |
| `"can   celled"` | `"CAN CELLED"` |

Any other value of `case` is refused.

> **[LAB lab-02-06 · Killercoda]** **Clean a messy file** — Take a CSV with spaces, mixed case, duplicates and empty cells, and make it clean with `trim`, `clean`, `deduplicate` and `fill_null`, checking the file after each step.

---

# Hydra DSL - Calculation

## calculate

Adds a column (or replaces an existing one) computed from an expression.

| Parameter | Required | Description                    |
| --------- | -------- | ------------------------------ |
| `column`  | Yes      | Name of the column to create   |
| `expr`    | Yes      | Expression (see *Expressions*) |

### Example 1: arithmetic

```yaml
- calculate:
    column: amount_ttc
    expr: "amount * 1.2"
```

### Example 2: from several columns

```yaml
- calculate:
    column: total
    expr: "price * qty - discount"
```

### Example 3: a true/false flag

```yaml
- calculate:
    column: is_big
    expr: "amount > 100"
```

| id  | amount | is_big |
| --- | ------ | ------ |
| 1   | 120.0  | True   |
| 2   | 80.0   | False  |

## script

Runs a short piece of Python when an expression is not enough. You declare what the code reads (`inputs`) and what it produces (`outputs`).

| Parameter | Default      | Description                                               |
| --------- | ------------ | --------------------------------------------------------- |
| `inputs`  | `[]`         | Columns given to the code                                 |
| `outputs` | –            | Columns produced, with their type. Required               |
| `code`    | –            | Python code. Required                                     |
| `mode`    | `vectorized` | `vectorized` (whole columns) or `row` (one row at a time) |

Output types: `int` · `float` · `str` · `bool` · `date` · `datetime` · `any`.

### Example 1: `row` mode

Each input is a single value. Each output must be assigned.

```yaml
- script:
    mode: row
    inputs: [amount, country]
    outputs:
      segment: str
    code: |
      if amount is None:
          segment = "unknown"
      elif country == "FR" and amount > 100:
          segment = "premium_fr"
      else:
          segment = "standard"
```

### Example 2: `vectorized` mode

Each input is a whole column. Faster on large data.

```yaml
- script:
    inputs: [price, qty]
    outputs:
      total: float
    code: |
      total = price * qty
```

### Example 3: using a parameter

Job parameters are available, read-only, in `params`:

```yaml
- script:
    mode: row
    inputs: [amount]
    outputs:
      above_threshold: bool
    code: |
      above_threshold = amount > params["min_amount"]
```

## Rules for scripts

- No `import`, no file or network access.
- Only these built-in functions are available: `abs round min max sum len int float str bool list dict tuple set sorted reversed zip range enumerate map filter any all divmod pow isinstance print format repr ord chr hex bin`.
- Every column listed in `outputs` must be assigned by the code.
- `print(...)` output appears in the job log.

> **[LAB lab-02-07 · Killercoda]** **From expression to script** — Compute a customer segment first with `calculate`, then with `script` in `row` mode, then in `vectorized` mode, and compare.

---

# Hydra DSL - Aggregation

## aggregate

Groups the rows and computes one value per group.

| Parameter | Required | Description                            |
| --------- | -------- | -------------------------------------- |
| `by`      | Yes      | Grouping columns                       |
| `agg`     | Yes      | Output columns and how to compute them |

Functions: `sum` · `count` · `mean` · `avg` (same as `mean`) · `min` · `max` · `first` · `last`.

### Example 1: long form

```yaml
- aggregate:
    by: [country]
    agg:
      total_amount: { func: sum, col: amount }
      nb_orders:    { func: count, col: id }
```

| country | total_amount | nb_orders |
| ------- | ------------ | --------- |
| BE      | 80.0         | 1         |
| DE      | 0.0          | 1         |
| FR      | 165.5        | 2         |

### Example 2: short form

When the output column has the same name as the source column:

```yaml
- aggregate:
    by: [country]
    agg:
      amount: sum
```

### Example 3: several grouping columns

```yaml
- aggregate:
    by: [country, status]
    agg:
      avg_amount: { func: avg, col: amount }
      max_amount: { func: max, col: amount }
```

> **[FIGURE fig-02-08 · diagram]** Rows coloured by `country`, gathered into three groups, each group reduced to one row with `sum(amount)` and `count(id)`.

<!-- REVIEW (décision B) : le code transmet `func` à pandas sans contrôle (median,
     std, nunique… fonctionnent). Seules les 8 fonctions annoncées sont documentées. -->

---

# Hydra DSL - Combining Data

`join`, `merge` and `union` combine the main flow with a **second source**, declared in `sources.yaml` and referenced by its id in `right`.

```yaml
# sources.yaml
sources:
  orders:            # main flow (pipeline.from)
    type: csv
    connection: {}
    extract: { table: data/orders.csv }
  customers:         # second source, used by right:
    type: csv
    connection: {}
    extract: { table: data/customers.csv }
```

`customers`:

| customer_id | name  |
| ----------- | ----- |
| 100         | Alice |
| 101         | Bob   |
| 103         | Chloé |

<!-- REVIEW (décision D) : `right` accepte aussi une source inline (dict avec `type`).
     Non documenté tant que ce n'est pas décidé. -->

## join

| Parameter               | Default | Description                                    |
| ----------------------- | ------- | ---------------------------------------------- |
| `right`                 | –       | Id of the second source. Required              |
| `key`                   | –       | Common column, or list of columns              |
| `left_key`, `right_key` | –       | When the key has a different name on each side |
| `how`                   | `inner` | `inner` · `left` · `right` · `outer`           |

`key`, or `left_key` + `right_key`, is required.

> **[FIGURE fig-02-09 · diagram]** The four `how` values as Venn diagrams on `orders` and `customers`, with the resulting rows listed under each.

### Example 1: inner join

```yaml
- join:
    right: customers
    key: customer_id
```

| id  | customer_id | country | amount | status    | name  |
| --- | ----------- | ------- | ------ | --------- | ----- |
| 1   | 100         | FR      | 120.0  | paid      | Alice |
| 2   | 101         | BE      | 80.0   | cancelled | Bob   |
| 3   | 100         | FR      | 45.5   | paid      | Alice |

Order 4 (customer 102) has no match and is dropped.

### Example 2: left join

```yaml
- join:
    right: customers
    key: customer_id
    how: left
```

All the orders are kept; `name` is empty for customer 102.

### Example 3: keys with different names

```yaml
- join:
    right: customers
    left_key: client_id
    right_key: customer_id
```

### Example 4: composite key

```yaml
- join:
    right: prices
    key: [country, product_id]
```

> When both sides have a column with the same name (other than the key), the column from `right` gets the suffix `_r`.

## merge

Applies the rows of the second source **onto** the main flow, by key: rows with a known key are replaced, new keys are added.

| Parameter          | Default | Description                                            |
| ------------------ | ------- | ------------------------------------------------------ |
| `right`            | –       | Id of the second source. Required                      |
| `key`              | –       | Matching column or columns. Required                   |
| `delete_unmatched` | `false` | Also remove rows whose key is not in the second source |

```yaml
- merge:
    right: customer_updates
    key: customer_id
```

| Main flow | Second source    | Result           |
| --------- | ---------------- | ---------------- |
| 100 Alice | 100 Alice Martin | 100 Alice Martin |
| 101 Bob   | –                | 101 Bob          |
| –         | 104 David        | 104 David        |

With `delete_unmatched: true`, row 101 is removed.

## union

Stacks the rows of the second source under the main flow. Columns are matched by name; a missing column is left empty.

| Parameter  | Default | Description                       |
| ---------- | ------- | --------------------------------- |
| `right`    | –       | Id of the second source. Required |
| `distinct` | `false` | `true` removes identical rows     |

```yaml
- union:
    right: orders_2025
    distinct: true
```

> **[LAB lab-02-08 · Killercoda]** **Join, merge, union** — Combine an orders file with a customers file in the three ways, and explain each result row.

---

# Hydra DSL - Reshaping Data

## pivot

Turns the values of one column into columns.

| Parameter | Default | Description                                                                                     |
| --------- | ------- | ----------------------------------------------------------------------------------------------- |
| `index`   | –       | Columns kept as rows. Required                                                                  |
| `column`  | –       | Column whose values become columns. Required                                                    |
| `values`  | –       | Column that fills the cells. Required                                                           |
| `aggfunc` | `first` | How to combine several values for the same cell (`sum`, `mean`, `min`, `max`, `count`, `first`) |

```yaml
- pivot:
    index: [region]
    column: month
    values: sales
    aggfunc: sum
```

| region | month | sales |
| ------ | ----- | ----- |
| North  | Jan   | 10    |
| North  | Feb   | 12    |
| South  | Jan   | 7     |

becomes

| region | Feb | Jan |
| ------ | --- | --- |
| North  | 12  | 10  |
| South  |     | 7   |

## unpivot

The opposite of `pivot`: turns columns into rows.

| Parameter    | Default           | Description                                       |
| ------------ | ----------------- | ------------------------------------------------- |
| `id_vars`    | –                 | Columns kept as they are. Required                |
| `value_vars` | all other columns | Columns turned into rows                          |
| `var_name`   | `variable`        | Name of the column receiving the old column names |
| `value_name` | `value`           | Name of the column receiving the values           |

```yaml
- unpivot:
    id_vars: [region]
    value_vars: [Jan, Feb]
    var_name: month
    value_name: sales
```

| region | Jan | Feb |
| ------ | --- | --- |
| North  | 10  | 12  |

becomes

| region | month | sales |
| ------ | ----- | ----- |
| North  | Jan   | 10    |
| North  | Feb   | 12    |

## transpose

Swaps rows and columns.

| Parameter     | Default  | Description                                       |
| ------------- | -------- | ------------------------------------------------- |
| `index_col`   | –        | Column whose values become the new column names   |
| `header_name` | `column` | Name of the column receiving the old column names |

```yaml
- transpose:
    index_col: metric
    header_name: field
```

| metric  | 2024 | 2025 |
| ------- | ---- | ---- |
| revenue | 100  | 130  |
| cost    | 60   | 70   |

becomes

| field | revenue | cost |
| ----- | ------- | ---- |
| 2024  | 100     | 60   |
| 2025  | 130     | 70   |

> **[FIGURE fig-02-10 · diagram]** The same small table shown three times: pivoted, unpivoted and transposed, with arrows showing where each value moves.

---

# Hydra DSL - Transformation Engines

The **engine** is what executes the steps. Hydra has two:

| Engine   | Strength                                                                                                           | Install                           |
| -------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------- |
| `pandas` | Reference engine, every operation                                                                                  | built in                          |
| `duckdb` | Large volumes: `aggregate`, `sort`, and `join` with `how: right` or `outer`, computed on disk instead of in memory | `pip install "hydra-etl[duckdb]"` |

Both give the **same result**. Only the speed and the memory used change.

## Choosing the engine

```yaml
version: "1.0"
transformations:
  engine: auto
  steps:
    - aggregate:
        by: [country]
        agg:
          amount: sum
```

| `engine`         | What happens                                                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `auto` (default) | `pandas`, unless the job has a global operation **and** the CSV source is estimated above 2 000 000 rows: then `duckdb` |
| `pandas`         | Always pandas                                                                                                           |
| `duckdb`         | DuckDB for the global operations, pandas for the others                                                                 |

> **[FIGURE fig-02-11 · diagram]** Decision tree of `engine: auto`: global operation? → CSV source above the threshold? → duckdb installed? → duckdb, otherwise pandas at each "no".

## Rules for engines

- `engine` is optional. Without it, `auto` is used.
- The variable `HYDRA_ENGINE` **overrides** `engine:` for every job: `HYDRA_ENGINE=pandas hdrctl run .`
- The threshold of `auto` is set by `HYDRA_LARGE_VOLUME_ROWS` (default `2000000`).
- `auto` estimates the size of **CSV** sources only. For a database source, write `engine: duckdb` to use DuckDB.
- `engine: duckdb` without the DuckDB extra stops the job with the install command. `auto` falls back to pandas with a warning.
- Operations other than `aggregate`, `sort` and `join` (`right` / `outer`) always run in pandas, batch by batch.
- If DuckDB cannot translate a global operation, it is handed back to pandas, with a message in the log.

## Example 1: let Hydra decide

```yaml
transformations:
  steps:
    - filter:
        expr: "status == 'paid'"
    - aggregate:
        by: [country]
        agg:
          amount: sum
```

The job log tells which engine was chosen, and why:

```
Job 'sales': engine pandas (auto : ≈ 120 000 lignes estimées (< 2 000 000))
```

## Example 2: force DuckDB on a database source

```yaml
transformations:
  engine: duckdb
  steps:
    - sort:
        by: [created_at]
```

## Example 3: force pandas for one run

```bash
HYDRA_ENGINE=pandas hdrctl run jobs/sales
```

## Under the hood: two automatic accelerations

These need no DSL key. They are listed so that you recognise them in the logs.

| Acceleration                        | Applies to                                        | Controlled by                                                                                   |
| ----------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **numexpr**                         | Large `filter` and `calculate` on numeric columns | `HYDRA_NUMEXPR` (`1` default: only where the result is bit-for-bit identical · `all` · `0` off) |
| **Native CSV reader/writer (Rust)** | Reading and writing CSV                           | `pip install "hydra-etl[native]"`, then `HYDRA_BACKEND=rust` or a `hydra.backends.yaml` file    |

> **[LAB lab-02-09 · Killercoda]** **pandas vs DuckDB** — Run the same aggregation on a 5-million-row CSV with `engine: pandas`, then `engine: auto`, and compare time and memory in the job report.

> **[GITHUB gh-02-05 · example]** **large_volume_engine** — Job with a data generator script for a large CSV, and three variants of `transformations.yaml` (`auto`, `pandas`, `duckdb`).

<!-- REVIEW : la ligne de log de l'exemple 1 est en français dans le code
     (executor.py, large_volume.decide). À traduire côté code (Règle −2) ou à
     retirer de la page. -->

---

# Hydra DSL - Expressions

`filter.expr` and `calculate.expr` use the same small expression language. Column names are written as they are.

## Rules for expressions

- Write the whole expression between quotes in YAML: `expr: "amount > 50"`.
- Text values go between single quotes inside: `"status == 'paid'"`.
- A column name with spaces goes between backticks: ``"`unit price` > 10"``.
- `filter` needs a condition (true/false). `calculate` accepts any value.

## Operators

| Kind       | Operators                     | Example                     |
| ---------- | ----------------------------- | --------------------------- |
| Arithmetic | `+` `-` `*` `/` `//` `%` `**` | `"price * qty"`             |
| Comparison | `==` `!=` `<` `<=` `>` `>=`   | `"amount >= 100"`           |
| Logic      | `and` `or` `not`              | `"paid and not refunded"`   |
| Membership | `in` `not in`                 | `"country in ['FR', 'BE']"` |
| Grouping   | `( )`                         | `"(a + b) * 2"`             |

## Examples, from simple to complex

```yaml
- filter:
    expr: "amount > 0"
```

```yaml
- filter:
    expr: "country == 'FR' or (country == 'BE' and amount > 100)"
```

```yaml
- filter:
    expr: "status not in ['cancelled', 'refunded']"
```

```yaml
- calculate:
    column: margin_pct
    expr: "(price - cost) / price * 100"
```

```yaml
- calculate:
    column: unit_price
    expr: "`total amount` / qty"
```

## When the expression is wrong

```yaml
- filter:
    expr: "amount >> 50"
```

The job stops on this step and shows the expression and the reason.

> **[LAB lab-02-10 · Killercoda]** **Expression drills** — Ten small filtering and calculation exercises on the `orders` table, each checked automatically.

## Where expressions are used

| Place                           | Language                              |
| ------------------------------- | ------------------------------------- |
| `filter.expr`, `calculate.expr` | This page                             |
| `script.code`                   | Restricted Python (see *Calculation*) |
| `when:` of a workflow step      | See *Workflows*                       |
