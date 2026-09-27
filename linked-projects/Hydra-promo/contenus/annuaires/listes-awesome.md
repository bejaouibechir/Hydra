# Listes awesome : propositions d'ajout (PR)

> Préparé le 19/09/2026. Règles lues dans le CONTRIBUTING (ou le README) de chaque liste le jour même.
> **Bechir ouvre les PR** : fork → modifier `README.md` → PR. **Une PR par liste.**

## Comment ça marche (à lire d'abord)

⚠️ **On ne touche PAS au README de Hydra.** Une « liste awesome » est le dépôt GitHub **de quelqu'un d'autre**, qui recense des outils. Les sections citées plus bas (*Data Platforms*, *Workflow*, *ETL*…) sont dans **leur** README. On leur propose d'ajouter **une ligne** qui pointe vers Hydra ETL.

**Procédure 100 % navigateur (sans git), ~10 min par liste :**

1. Ouvrir la liste, ex. `https://github.com/pditommaso/awesome-pipeline`
2. Cliquer sur **README.md**, puis sur l'icône **crayon ✏️** (*Edit this file*). GitHub crée automatiquement une copie (fork) chez toi.
3. `Ctrl + F` → chercher le nom de la section indiquée (ex. `Extract, transform, load`).
4. Placer le curseur à l'endroit indiqué (ex. entre la ligne `Hevo` et la ligne `Kiba ETL`) et **coller la ligne** fournie.
5. En haut à droite : **Commit changes…** → message = le « Titre PR » → **Propose changes**.
6. Page suivante : **Create pull request** → coller le « Corps PR » → **Create pull request**.
7. Noter le lien de la PR dans le tableau de suivi en bas de ce fichier.

## 0. Prérequis (à faire AVANT toute PR)

Vérifié le 19/09 : dépôt à **1 étoile, 0 fork, rubrique « About » vide** (pas de description, de site ni de topics). Un mainteneur qui clique sur le lien voit ça en premier.

- [ ] **About** → Description : `Declarative ETL pipelines in YAML, validated before they run. CLI, REST API, visual Studio, MCP server.`
- [ ] **About** → Website : `https://hydraetl.com`
- [ ] **Topics** : `etl` `data-pipeline` `yaml` `declarative` `data-engineering` `duckdb` `pandas` `python` `mcp` `low-code`
- [ ] **Release** `v0.10.1` publiée (avec le `.vsix`)

## 1. Tableau de décision

| Liste                                | ⭐     | Verdict          | Raison                                                                         |
| ------------------------------------ | ----- | ---------------- | ------------------------------------------------------------------------------ |
| punkpeye/awesome-mcp-servers         | 95 k  | ✅ **Maintenant** | Accepte tout serveur MCP avec dépôt public. Très fort trafic.                  |
| igorbarinov/awesome-data-engineering | 9 k   | ✅ **Maintenant** | Accepte des projets jeunes (ex. *Nika*, concept très proche).                  |
| pditommaso/awesome-pipeline          | 6,6 k | ✅ **Maintenant** | Seule exigence : licence open source.                                          |
| davidgasquez/awesome-duckdb          | 2,5 k | ✅ **Maintenant** | Accepte les outils utilisant DuckDB ; affiliation à déclarer.                  |
| meirwah/awesome-workflow-engines     | 7,9 k | ⏸ Après ~50 ⭐    | Chaque entrée affiche un badge d'étoiles : « 1 ⭐ » dessert.                    |
| pawl/awesome-etl                     | 3,6 k | ⏸ Après pilotes  | Règle : l'auteur doit prouver une « traction tierce réelle », sinon PR fermée. |
| vinta/awesome-python                 | 321 k | ❌ Après v1.0     | Exige « production-ready, pas bêta » + max 3 choix évidents par catégorie.     |

## 2. Textes prêts à coller

### 2.1 awesome-mcp-servers → https://github.com/punkpeye/awesome-mcp-servers — section **📊 Data Platforms**

Ordre alphabétique : insérer **entre** `aywengo/kafka-schema-reg-mcp` **et** `bintocher/mcp-superset`.

```markdown
- [bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra) 🐍 🏠 🍎 🪟 🐧 - MCP server for Hydra ETL, a declarative YAML ETL engine. Lets AI assistants draft pipelines (CSV, Parquet, PostgreSQL, MySQL, MongoDB, web APIs) and validate them with Hydra before any data is touched. Install: `pip install "hydra-etl[mcp]"`. [![hydra-etl MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/bejaouibechir/Hydra/badges/score.svg)](https://glama.ai/mcp/servers/bejaouibechir/Hydra)
```

**Titre PR :** `Add Hydra ETL MCP server (Data Platforms)`
**Corps PR :**

```
Adds Hydra ETL's MCP server to Data Platforms.

- Repo: https://github.com/bejaouibechir/Hydra (MCP docs: docs/MCP.md)
- Python, runs locally, Linux/macOS/Windows
- License: AGPL-3.0

Disclosure: I'm the author.
```

> ✅ **Condition levée le 21/09/2026.** Le mainteneur exigeait une note qualité attribuée sur
> glama.ai (`?` ne suffisait pas). Elle est à **83 %**, avec **A / A / A** sur licence, qualité et
> maintenance. Voir `contenus/annuaires/fiches-annuaires.md` §1 pour la marche à suivre complète.
>
> Le bot de la liste demande : *« Update your PR by adding a **Glama score badge** after the
> server description. »* → c'est le **Score Badge** (petit, `A A A Glama`), pas le Card Badge
> (grand bloc, réservé à un README), et il se place **en fin de ligne**. Le code exact est fourni
> par Glama : fiche → Admin → **GitHub Badge** → « Score Badge ». Il est déjà intégré à la ligne
> ci-dessus. L'ancienne URL `/badge` diffusée par le bot est remplacée par `/badges/score.svg`.
>
> Labels encore posés sur la PR au 21/09 : `has-emoji`, `missing-glama`, `valid-name`.
> `missing-glama` doit tomber une fois le badge en place.

### 2.2 awesome-data-engineering → https://github.com/igorbarinov/awesome-data-engineering — section **Workflow**

Les ajouts récents sont en haut de section (pas d'ordre alphabétique) : insérer **juste après `## Workflow`**.

```markdown
- [Hydra ETL](https://github.com/bejaouibechir/Hydra) - Declarative ETL engine: pipelines are YAML files validated before they run (`hdrctl validate`), executed with pandas, DuckDB or an optional Rust reader. Ships a CLI, a REST API and a visual editor.
```

**Titre PR :** `Add Hydra ETL to Workflow`
**Corps PR :**

```
Adds Hydra ETL, an open-source (AGPL-3.0) declarative ETL engine.
Pipelines are YAML, validated before execution. Installable with `pip install hydra-etl`.

Disclosure: I'm the author.
```

### 2.3 awesome-pipeline → https://github.com/pditommaso/awesome-pipeline — section **Extract, transform, load (ETL)**

Ordre alphabétique : insérer **entre `Hevo` et `Kiba ETL`**. Description courte, point final obligatoire.

```markdown
* [Hydra ETL](https://github.com/bejaouibechir/Hydra) - Declarative ETL engine where pipelines are YAML files validated before they run.
```

**Titre PR :** `Add Hydra ETL`
**Corps PR :**

```
Adds Hydra ETL to the ETL section (alphabetical order kept).
Open source, AGPL-3.0. Disclosure: I'm the author.
```

### 2.4 awesome-duckdb → https://github.com/davidgasquez/awesome-duckdb — section **Tools Powered by DuckDB**

Règle : **ajouter en bas** de la section, dire le lien avec DuckDB, pas de promo, déclarer l'affiliation.

```markdown
- [Hydra ETL](https://github.com/bejaouibechir/Hydra) - Declarative YAML ETL engine that can run transformations on DuckDB instead of pandas.
```

**Titre PR :** `Add Hydra ETL to Tools Powered by DuckDB`
**Corps PR :**

```
Adds Hydra ETL, an open-source declarative ETL engine with a DuckDB execution engine (`pip install "hydra-etl[duckdb]"`).
Appended at the end of the section per CONTRIBUTING. Disclosure: I'm the author.
```

## 3. Calendrier et suivi

- **Semaine 1 (21–27/09)** : prérequis §0, puis les 4 PR (une par soir, 10 min chacune).
- **Ne pas relancer** un mainteneur avant 3 semaines.
- **Mois 4** (après pilotes, benchmark et ~50 ⭐) : awesome-workflow-engines, awesome-etl.
- **Après v1.0** : awesome-python.

| Liste                    | PR ouverte | Lien PR                                                          | Statut                                                                 |
| ------------------------ | ---------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| awesome-mcp-servers      | 19/09      | https://github.com/punkpeye/awesome-mcp-servers/pull/14699       | Ouverte — **verrou levé le 21/09 : note Glama 83 %**. Reste à coller le badge (code dans l'onglet GitHub Badge de l'admin Glama) |
| awesome-data-engineering | 19/09      | https://github.com/igorbarinov/awesome-data-engineering/pull/371 | Ouverte                                                                |
| awesome-pipeline         | 19/09      | https://github.com/pditommaso/awesome-pipeline/pull/246          | Ouverte                                                                |
| awesome-duckdb           | 19/09      | https://github.com/davidgasquez/awesome-duckdb/pull/353          | Ouverte                                                                |
