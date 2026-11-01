# Amélioration — 3 transformations à ajouter (décision du 29/10/2026)

Origine : comparatif Hydra ETL / Flowfile. Ce sont les besoins ETL courants que Flowfile couvre et pas Hydra ETL 0.16.0 : `window_functions`, `cross_join`, `text_to_rows`.

Règles communes (comme `native` et `duckdb`) : validation stricte avant le run, mêmes résultats en `pandas` et en `duckdb` (tests de parité), jamais de repli silencieux, entrée dans la palette Studio, schéma VS Code, doc DSL, outils MCP.

## 1. `cross_join` — option du Join existant

Effort : **faible**.

```yaml
- join: {right: calendar, how: cross}
```

| Point | Règle |
|---|---|
| Clés | `how: cross` **interdit** `key`, `left_key` et `right_key` (erreur de validation sinon) |
| Colonnes en double | même suffixe que les autres jointures |
| Garde-fou | `max_rows` (défaut 10 000 000) : la taille estimée `gauche × droite` est vérifiée avant le run ; au-delà → erreur claire, forçable par `max_rows` |
| pandas | `merge(how="cross")` |
| duckdb | `CROSS JOIN` |

Tests : 0 ligne d'un côté, clés interdites, dépassement de `max_rows`, parité.

## 2. `text_to_rows` — une ligne par valeur

Effort : **faible à moyen**.

```yaml
- text_to_rows:
    column: tags          # "a;b;c" → 3 lignes
    sep: ";"
    trim: true            # défaut true
    keep_empty: false     # défaut false : valeurs vides ignorées
    index_column: tag_pos # optionnel : position 1, 2, 3…
```

| Point | Règle |
|---|---|
| Valeur nulle | une ligne, valeur nulle conservée |
| Autres colonnes | recopiées sur chaque ligne |
| `sep` | texte simple ; `regex: true` pour une expression régulière |
| pandas | `str.split` + `explode` |
| duckdb | `unnest(string_split(...))` |

Tests : séparateur absent, nulls, vides, espaces, regex, `index_column`, parité.

## 3. `window` — fonctions de fenêtre

Effort : **moyen**. La plus utile des trois (déduplication « dernière version », rangs, cumuls, écarts avec la ligne précédente).

```yaml
- window:
    partition_by: [customer_id]
    order_by: [{col: order_date, desc: false}]
    columns:
      order_rank:  {func: row_number}
      prev_amount: {func: lag, col: amount, offset: 1, default: 0}
      running_sum: {func: cumsum, col: amount}
      cust_total:  {func: sum, col: amount}     # total de la partition, sans réduire les lignes
```

| Famille | Fonctions |
|---|---|
| Rang | `row_number`, `rank`, `dense_rank` |
| Décalage | `lag`, `lead` (`offset`, `default`) |
| Cumul | `cumsum`, `cumcount`, `cummin`, `cummax` |
| Partition entière | `sum`, `mean`, `min`, `max`, `count`, `first`, `last` |

| Point | Règle |
|---|---|
| `order_by` | **obligatoire** pour rang, décalage et cumul (validation) ; égalités départagées par l'ordre d'origine (résultat déterministe) |
| `partition_by` | optionnel : sans lui, toute la table |
| Nulls | triés en dernier, comme `sort` |
| pandas | `groupby(...).rank / shift / cumsum / transform` |
| duckdb | `OVER (PARTITION BY … ORDER BY …)` — opération globale, éligible au moteur gros volumes |
| Hors périmètre v1 | cadres glissants (`rows between`), moyennes mobiles → v2 |

Tests : égalités, nulls, partitions vides, `lag` en début de partition, parité sur 1 M lignes.

## Étapes (une étape = code + tests + doc + commit, accord de Bechir entre chaque)

1. `cross_join` (option du Join, garde-fou `max_rows`).
2. `text_to_rows`.
3. `window` : rang et décalage.
4. `window` : cumuls et agrégats de partition.
5. Studio (palette : 18 → 20 transformations, icônes), schéma VS Code, doc DSL, MCP.
6. Rejouer `montee-en-volume` avec une étape `window` pour vérifier pandas et duckdb à 20 M lignes.

Version visée : **0.17.0**.
