# Fiches annuaires — textes prêts à coller

> Préparé le 19/09/2026. Chaque fiche a un texte **différent** (les moteurs et les IA pénalisent les descriptions dupliquées).
> Toujours écrire **Hydra ETL** (jamais « Hydra » seul). Lien du site avec UTM : `https://hydraetl.com/?utm_source=<annuaire>&utm_medium=directory&utm_campaign=annuaires`

**Éléments communs**

| Champ            | Valeur                                                |
| ---------------- | ----------------------------------------------------- |
| Nom              | Hydra ETL                                             |
| Site             | https://hydraetl.com                                  |
| Code             | https://github.com/bejaouibechir/Hydra                |
| Licence          | Open source (AGPL-3.0), gratuit                       |
| Plateformes      | Linux, macOS, Windows (Python 3.9+)                   |
| Logo             | `hydra-site\public\hydra-logo-256.png`                |
| Captures         | `hydra-site\public\studio\`, `hydra-site\public\cli\` |
| Image de partage | `hydra-site\public\og\hydra-etl-og.png`               |

---

## 1. Glama — FAIT, note 83 % au 21/09/2026

**Fiche :** https://glama.ai/mcp/servers/bejaouibechir/Hydra — revendiquée, `Author verified`.

### Où se configure le déploiement

Ce n'est **pas** un fichier à poser dans le dépôt. C'est un formulaire :
fiche → onglet **Admin** (visible seulement connecté) → **Dockerfile**. Glama génère
lui-même le Dockerfile à partir des champs. L'onglet Admin contient aussi : Listing,
Analytics, Boost, Repository, **Releases**, **Score**, **GitHub Badge**.

### Configuration de build validée (build réussi en 14 s)

| Champ | Valeur |
|---|---|
| `Base image` | `debian:trixie-slim` (défaut) |
| `Node.js version` | `24` (défaut — requis par `mcp-proxy`) |
| `Python version` | **`3.12`** |
| `Environment variables JSON schema` | `{"properties": {}, "required": [], "type": "object"}` |
| `Placeholder parameters` | `{}` |

`Build steps` :

```json
[
  "uv venv /opt/hydra",
  "uv pip install --python /opt/hydra/bin/python --no-cache-dir 'hydra-etl[mcp]==0.10.3'"
]
```

`CMD arguments` :

```json
["mcp-proxy", "--", "/opt/hydra/bin/hydra-mcp"]
```

### Pourquoi la configuration par défaut échouait

Les deux builds du 19/09 ont échoué parce que le formulaire propose `uv sync` et Python 3.14 :

1. Il n'y a **pas de `uv.lock`** dans le dépôt Hydra.
2. `uv sync` installe dans `/app/.venv` → `hydra-mcp` **n'est pas dans le PATH**, donc
   `mcp-proxy -- hydra-mcp` échoue avec « command not found ».
3. `uv sync` n'installe **pas l'extra `mcp`**, or `hydra-mcp` a besoin de `mcp>=2.0`.
4. **Python 3.14** : pas de wheels pour pandas/pydantic, et Hydra ETL n'est classifié que
   jusqu'à 3.12. L'extra `mcp` exige de toute façon `python_version >= '3.10'`.

D'où le choix d'installer **le wheel publié sur PyPI** plutôt que de construire les sources :
c'est aussi ce que l'utilisateur final fera, donc c'est ce qu'il faut tester.

⚠️ Ne **jamais** utiliser le `GHCR/Dockerfile` du dépôt : il construit le CLI, l'API et le
Studio, et ne démarre pas le serveur MCP.

### Procédure complète, dans l'ordre

1. `glama.json` à la racine du dépôt (fait, commit `9d872a0`) :
   ```json
   {
     "$schema": "https://glama.ai/mcp/schemas/server.json",
     "maintainers": ["bejaouibechir"]
   }
   ```
2. Onglet **Repository** → bouton **`Sync Server`**. Glama ne relit pas le dépôt tout seul :
   vérifier que « Last known commit » affiche bien le dernier commit poussé.
3. Onglet **Dockerfile** → saisir la configuration ci-dessus → **`Build`** (test seul).
4. Build vert → **`Make Release`** en saisissant le numéro à la main (`0.10.3`).
   `Build & Release` fait les deux d'un coup **mais choisit le numéro lui-même** — c'est
   comme ça que la première release s'est appelée `0.1.0`.

⚠️ **Traduire avant de publier la release.** C'est au moment de la release que Glama fait
lire les descriptions de tools par un LLM pour noter `Tool Definition Quality` et
`Server Coherence`, et le détail est **public**. Le serveur MCP de Hydra ETL était en
français : d'où la 0.10.3 (voir `contenus/mcp/tool-definitions-en.md`).

### Note obtenue : 83 %, 8 critères sur 10

| Critère | État |
|---|---|
| Has a Glama release | ✅ |
| Server Coherence | ✅ **A** |
| Tool Definition Quality | ✅ **A** |
| Maintenance | ✅ A |
| Has a permissive license (AGPL 3.0) | ✅ A |
| Has README | ✅ |
| Has valid glama.json | ✅ |
| Author verified | ✅ |
| No recent usage | 🚫 aucun appel de tool en 30 jours — remède Glama : « Try in Browser » |
| No related servers | 🚫 calculé par Glama à partir de la similarité des tools |

### Badge pour la PR awesome-mcp-servers #14699

Le code exact est donné par l'onglet **GitHub Badge** de l'admin — **le copier depuis là**
plutôt que de le recomposer. Format attendu par le mainteneur de la liste :

`[![MCP](https://glama.ai/mcp/servers/bejaouibechir/Hydra/badge)](https://glama.ai/mcp/servers/bejaouibechir/Hydra)`

### Description de la fiche (champ `Listing`)

> MCP server for Hydra ETL: lets AI assistants write declarative YAML ETL pipelines (CSV,
> Parquet, PostgreSQL, MySQL, MongoDB, APIs) and validate them before any data is read or
> written.

Catégories retenues : `Data Platforms`, `Developer Tools`.

### Deux points de vigilance

- **`Auto-Release`** est activé (onglet Releases) : « Builds and publishes a new version on
  every GitHub release ». Mais `release.yml` se déclenche sur un **tag** `v*`, et un tag
  n'est pas une *GitHub Release*. Sans Release créée dans l'interface GitHub, l'auto-release
  Glama ne part pas.
- **`Responsiveness: Unresponsive`** sur la page Overview : mesuré sur le temps de réponse
  aux issues et PR du dépôt. Indépendant de la note qualité, mais visible publiquement.

---

## 2. AlternativeTo — angle « alternative à… »

**Où :** https://alternativeto.net → *Add application* (compte requis, modération de quelques jours).

- **Nom :** Hydra ETL

- **Description courte :** Declarative ETL: pipelines as YAML files, validated before they run.

- **Description :**
  
  > Hydra ETL is an open-source ETL engine where each pipeline is a small set of YAML files instead of Python code. Before anything runs, `hdrctl validate` checks connections, schemas and steps without touching the data. It reads and writes CSV, JSON, Parquet, PostgreSQL, MySQL/MariaDB, MongoDB and web APIs, runs on pandas or DuckDB, and ships a CLI, a REST API and a visual editor that work on the same files. No scheduler database or broker to deploy: `pip install hydra-etl`.

- **Alternative à :** Apache Airflow, Airbyte, Apache NiFi, Talend Open Studio, Apache Hop, Pentaho Data Integration

- **Tags :** etl, data-pipeline, yaml, data-integration, open-source, python, duckdb

- **Licence :** Open Source · Free

---

## 3. SaaSHub — angle « alternative » + catégorie

**Où :** https://www.saashub.com/submit (compte requis). Lien dofollow.

- **Tagline :** YAML ETL pipelines you can validate before running

- **Description :**
  
  > Hydra ETL turns data pipelines into readable YAML. A pipeline is a few files that can be reviewed in a pull request; `hdrctl validate` catches configuration errors before execution. Connectors cover files (CSV, JSON, Parquet), SQL databases (PostgreSQL, MySQL/MariaDB), MongoDB and HTTP APIs. Run it from the command line, call it through a REST API, or edit the same pipelines in a visual Studio. Open source (AGPL-3.0), beta, single-command install.

- **Catégories :** ETL, Data Integration, Data Pipeline

- **Concurrents à lier :** Apache Airflow, Airbyte, Talend, Apache NiFi, dbt

---

## 4. LibHunt — angle développeur Python

**Où :** https://python.libhunt.com → *Submit a project* (ou via le lien « Add » en haut). Indexe le dépôt GitHub.

- **Dépôt :** https://github.com/bejaouibechir/Hydra

- **Catégorie :** Data Pipelines / ETL

- **Description :**
  
  > Declarative ETL engine for Python: define pipelines in YAML, validate them with `hdrctl validate`, execute with pandas, DuckDB or an optional Rust CSV reader.

- **Tags :** etl, yaml, pandas, duckdb, data-engineering

---

## 5. SourceForge — facile, domaine très fort

**Où :** https://sourceforge.net → *Create* → *Import a GitHub project* (il miroite le dépôt et les releases).

- **Résumé (70 caractères max) :** Declarative YAML ETL pipelines, validated before they run

- **Description :**
  
  > Hydra ETL is an open-source Python ETL engine. Pipelines are YAML manifests checked by a validator before execution, then run on pandas or DuckDB. Includes the hdrctl CLI, a FastAPI REST server, a visual Studio, a VS Code extension and an MCP server for AI assistants.

- **Catégories :** Data Integration / ETL, Database

---

## Suivi

| Annuaire      | Soumis le  | Lien de la fiche                                   | Statut |
| ------------- | ---------- | -------------------------------------------------- | ------ |
| Glama         | 19/09/2026 | https://glama.ai/mcp/servers/bejaouibechir/Hydra   | **note 83 %, release publiée le 21/09** |
| AlternativeTo | 19/09/2026 |                                                    | active |
| SaaSHub       | 19/09/2026 |                                                    | active |
| LibHunt       | 19/09/2026 |                                                    | active |
| SourceForge   | 19/09/2026 | https://sourceforge.net/p/hydra-etl/admin/overview | active |
