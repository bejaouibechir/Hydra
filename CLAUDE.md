# CLAUDE.md — Hydra ETL Platform

Contexte projet complet pour Claude. Lire avant toute intervention sur ce codebase.

---

## Vision Produit

Hydra est une **plateforme data en 3 engines** symbolisés par les 3 têtes de l'hydre :

| Engine | Description | Statut |
|--------|-------------|--------|
| **ETL Engine** | Framework ETL déclaratif (jobs, workflows, Studio) | En cours — v1 cible |
| **Feature Detection Engine** | Feature engineering automatisé pour modèles ML/prédiction | Futur |
| **Execution Intelligence Engine** | HydraLM + connecteurs MCP + intelligence sur les pipelines | Futur |

**Modèle économique** : ETL Engine gratuit/open-source → Feature Engine + Intelligence Engine payants.

**Domaine** : hydraetl.com (acheté, prévu pour documentation style Kubernetes via GitHub Pages).

---

## État Actuel — ETL Engine

### Ce qui est fait
- CLI complet (`hdrctl` / `hydra`) via Click — `cli/hdrctl.py`
- i18n (en + es) — `cli/i18n.py` + `cli/locales/{en,es}.json`
- Job runner : source → transformations → destination (unité atomique)
- Connectors : CSV, JSON, Parquet, MySQL/MariaDB, PostgreSQL, MongoDB, Web API
- Engines de transformation : Pandas, DuckDB
- Système de plugins extensible (`plugins/`)
- Cache, schema validation, secrets, retry policies, circuit breaker
- 48 tests CLI passants (`tests/test_cli_hdrctl.py`)

### Prochaines étapes prioritaires
1. **Workflow runner** — orchestration multi-jobs avec DAG (`workflow.yaml`)
2. **API FastAPI** — endpoints REST pour déclencher/surveiller les workflows
3. **Studio** — éditeur visuel web inspiré de n8n (canvas React Flow)

---

## Architecture

### Structure du Job (unité atomique)
```
1 source → N transformations → 1 destination
```
Un job = un dossier contenant `pipeline.yaml` (ou `sources.yaml` + `transformations.yaml` + `destinations.yaml`).

### Deux types de transformations

**Job Transformations** — manipulent les données (colonnes/lignes), internes au job :
```
filter, select, rename, cast
aggregate, sort, deduplicate
derive, calculate
pivot, unpivot
clean, fill_null, trim
index
```

**Workflow Transformations** — manipulent le flux d'exécution, externes au job (nœuds sur le canvas Studio) :
```
split       — 1 flux → N branches
merge       — N flux → 1 flux (par clé)
multicast   — 1 flux → N copies identiques
union       — N flux → 1 flux (append)
join        — N flux → 1 flux (clé commune)
lookup      — enrichissement depuis un flux externe
condition   — branch if/else
loop        — itération
parallel    — exécution parallèle explicite
```

**Règle** : agit sur colonnes/lignes → Job Transformation. Agit sur le routage entre jobs → Workflow Transformation.

### Structure du Workflow (orchestration)
```yaml
version: "1.0"
workflow:
  name: "nom_du_workflow"
  trigger:
    type: manual          # ou schedule (cron) ou webhook
    cron: "0 8 * * *"    # si type: schedule
  steps:
    - name: "step_a"
      type: job
      job: "./jobs/extract.yaml"
    - name: "step_b"
      type: job
      job: "./jobs/transform.yaml"
      depends_on: ["step_a"]          # liste pour support parallèle/merge
    - name: "step_c"
      type: action
      action: webhook
      params:
        url: "{{ env.WEBHOOK_URL }}"
      depends_on: ["step_b"]
      on_failure: skip
```

**Règles du manifest workflow** :
- `depends_on` est toujours une **liste** (même pour un seul parent) — requis pour les cas merge/fan-in
- Parallélisme implicite : steps sans `depends_on` commun s'exécutent en parallèle
- `type: job` → appelle le job runner existant
- `type: action` → side-effects (webhook, email, slack, etc.)

### Hiérarchie projet (Studio)
```
Project → Workflows → Jobs (nœuds sur le canvas)
```
- Un project = un dossier sur disk
- Un environment (dev/prod) = fichier `.env` associé
- Persistance v1 : fichiers YAML sur disk, pas de base de données

---

## Fichiers Clés

| Fichier | Rôle |
|---------|------|
| `cli/hdrctl.py` | CLI principal (~1259 lignes), commandes Click |
| `cli/i18n.py` | Module i18n, détection langue, `t("key")` API |
| `cli/locales/en.json` | 111 clés — source de vérité |
| `cli/locales/es.json` | 85 clés espagnol |
| `internal/runner/executor.py` | Cœur du job runner |
| `internal/connector/` | Tous les connecteurs (CSV, JSON, MySQL, etc.) |
| `internal/engines/` | Pandas engine, DuckDB engine |
| `internal/parser/` | Parsers source/transform/destination YAML |
| `internal/plugin_loader.py` | Système de plugins |
| `plugins/` | Extensions : auth, cache, retry, pagination, etc. |
| `tests/conftest.py` | `HYDRA_LANG=en` avant imports (critique pour tests CLI) |
| `setup.py` | Entry points : `hydra` et `hdrctl` → `cli.hdrctl:main` |

---

## Conventions de Code

### i18n
- Toutes les chaînes visibles utilisateur passent par `t("key")` — jamais de strings hardcodées
- Ajouter les nouvelles clés dans `en.json` en premier, puis `es.json`
- `_SUPPORTED = frozenset({"en", "es"})` — ne pas ajouter d'autres langues sans décision explicite
- Les fichiers `fr/de/pt/zh/ja.json` existent mais sont ignorés (`_SUPPORTED` les exclut)

### Modification de fichiers larges
- `cli/hdrctl.py` (~1259 lignes) : toujours modifier via **script Python** ou Edit tool avec contexte suffisant — ne jamais réécrire entièrement
- Tester après chaque modification : `pytest tests/test_cli_hdrctl.py -x`

### Tests
- 48 tests CLI dans `tests/test_cli_hdrctl.py` doivent toujours passer
- `tests/conftest.py` doit toujours contenir `os.environ.setdefault("HYDRA_LANG", "en")`
- Tests e2e (`tests/e2e/`) nécessitent Docker (MySQL, MongoDB) — ne pas lancer en CI sans infrastructure
- `pyarrow` non installé dans la sandbox Linux — tests Parquet skippés en sandbox, OK sur Windows

### Python
- Python ≥ 3.9
- Pydantic v2 pour les modèles de données
- Zéro dépendance externe dans `cli/i18n.py`
- Installation : `pip install -e .` (editable mode — pas besoin de réinstaller après modifications)

---

## Décisions Techniques Actées

1. **Job = unité atomique** (1 source → 1 destination). Les transformations split/merge/join opèrent sur des flux internes, pas des sources/destinations indépendantes.
2. **Workflow = orchestrateur** de jobs avec DAG. Nécessaire pour les cas multi-sources/multi-destinations réels.
3. **Pas de base de données en v1** — tout est fichier YAML sur disk.
4. **Logs streaming (WebSocket/SSE) reporté** à post-v1 — polling simple suffit pour v1 Studio.
5. **Auth mono-user en v1** — token statique ou basic auth, pas de multi-user.
6. **Stack Studio** : FastAPI (backend) + React Flow (canvas) + APScheduler (triggers schedulés).
7. **`depends_on` est une liste** dès v1 du manifest — pas de migration schema plus tard.

---

## Ce qu'il ne faut PAS faire

- Ne pas modifier l'architecture job existante pour supporter multi-source/multi-destination — c'est le rôle du Workflow
- Ne pas ajouter de nouvelles langues i18n sans décision explicite
- Ne pas introduire de base de données en v1
- Ne pas casser les 48 tests CLI existants
- Ne pas réinstaller le package après chaque modification (editable install)

---

## Roadmap ETL Engine v1

```
[✓] CLI + i18n (en/es)
[✓] Job runner (source → transformations → destination)
[✓] Connectors (CSV, JSON, Parquet, MySQL, PostgreSQL, MongoDB, WebAPI)
[ ] Workflow runner (DAG, parallélisme, depends_on)
[ ] API FastAPI (/api/workflows, /api/run, /api/logs)
[ ] Studio — canvas éditeur (React Flow, inspiré n8n)
[ ] Documentation hydraetl.com (MkDocs ou Docusaurus, GitHub Pages)
```

---

## Architecture Mosaïque (Vision Long Terme)

Hydra ne sera **pas un bloc monolithique** (cf. MS Fabric). L'architecture cible est une **architecture mosaïque distribuée** : des milliers d'instances Hydra autonomes, bien harmonisées entre elles, sans autorité centrale rigide.

### Principes
- Chaque instance Hydra = un **nœud autonome** capable d'exécuter jobs et workflows, d'exposer son API et de participer au réseau
- Les nœuds se découvrent et se coordonnent sans master/slave — topologie pair-à-pair
- Flexibilité : un step d'un workflow peut s'exécuter sur n'importe quel nœud disponible
- Résilience : pas de point de défaillance unique

### Persistance distribuée
Pas de base de données centrale. L'état distribué (workflows, exécutions, métriques) sera géré par une **base décentralisée** de type Bluzelle ou BigchainDB — des systèmes conçus pour des environnements distribués sans autorité centrale, proches dans l'esprit d'une blockchain.

### Roadmap d'évolution
```
V1 : nœud unique — YAML sur disk, API locale, Studio mono-instance
V2 : multi-nœuds — découverte de nœuds, exécution cross-instances
V3 : persistance distribuée — remplacement YAML par Bluzelle/BigchainDB ou équivalent
```

### Ce que ça ne change pas pour V1
L'architecture actuelle (job atomique, workflow DAG, FastAPI, YAML sur disk) est la **fondation correcte** pour cette vision. On ne sur-architecture pas V1 — on garde les interfaces propres pour que la distribution arrive naturellement en V2.

---

## Contexte Consortium

Hydra est développé en consortium. Grok (xAI) participe aux discussions de design — notamment le manifest workflow initial et la vision Studio. Les décisions finales d'architecture sont prises par Bechir Bejaoui (Andaluz Lab, Bbejaoui@andaluzlab.com).
