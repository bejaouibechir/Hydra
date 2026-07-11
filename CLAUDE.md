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
- 49 tests CLI dans `tests/test_cli_hdrctl.py` doivent toujours passer (Linux + Windows)
- `tests/conftest.py` doit toujours contenir `os.environ.setdefault("HYDRA_LANG", "en")`
- Tests e2e (`tests/e2e/`) nécessitent Docker (MySQL, MongoDB) — ne pas lancer en CI sans infrastructure
- `pyarrow` optionnel — tests Parquet skippés si absent (`pytest.skip`), sans bloquer les autres
- 21 failures pré-existantes dans `test_pandas_engine.py` + `test_transform_parser.py` (dtype `bool` vs `boolean`, `params` dict vs objet) — non bloquantes pour v1

### Python
- Python ≥ 3.9, cross-platform (Linux / macOS / Windows)
- Pydantic v2 pour les modèles de données
- Zéro dépendance externe dans `cli/i18n.py`
- Installation : `pip install -e .` (editable mode — pas besoin de réinstaller après modifications)
- Line endings : LF sur tout le codebase (`.gitattributes` configuré avec `eol=lf`)

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
[✓] Workflow runner (DAG, parallélisme, depends_on) — complet, intégré CLI
[✓] Opération aggregate (groupby + agg functions) — PandasEngine + TransformParser
[✓] Connecteurs JSON + PostgreSQL enregistrés dans le registry
[✓] Scénarios de test S1–S5 (test_scenarios/) — S1/S2/S3 exécutables sans infra
[ ] API FastAPI (/api/workflows, /api/run, /api/logs)
[ ] Studio — canvas éditeur (React Flow, inspiré n8n)
[ ] Documentation hydraetl.com (MkDocs ou Docusaurus, GitHub Pages)
```

---

## Plan d'action actuel (sprint en cours)

| Priorité | Tâche | Durée est. | Statut |
|----------|-------|------------|--------|
| **P0** | Fix `internal/connector/__init__.py` — import pyarrow sans try/except casse les tests CSV en environnement sans pyarrow | 30 min | [✓] |
| **P1** | Tests workflow — zéro couverture sur `workflow/` (parser, runner, CLI) | 1-2 jours | [✓] |
| **P2** | API FastAPI — `POST /api/run`, `GET /api/status/{run_id}`, `GET /api/workflows` ; démarrage via `hdrctl serve` | 3-5 jours | [✓] |
| **P3** | Nettoyage dette technique — clarifier `etl/engine.py`, `web_api_connector v1 vs v2`, supprimer scripts/tests orphelins | 1 jour | [✓] |
| **P4** | Studio — canvas React Flow + FastAPI backend + APScheduler | 2-3 semaines | [✓] |

### Détail P3 (réalisé — Sprint 5)
- `test_cli_hdrctl.py` : corruption lignes 455-505 supprimée (4x `TestErrors` dupliqué) → 49 tests passent
- `tests/` : 6 scripts one-shot déplacés dans `_archive/tests_oneshot/` (fix_corruption.py, inspect_fix.py, test_cli_hdrctl_fix.py, poc_json_flatten.py, json_connector_test.py, postgresql_connector_simple_test.py)
- `sys.path.insert(0, '/home/claude/web_api_connector_mvp')` supprimé des 4 fichiers test_web_api_* → 64 tests passent proprement
- `web_api_connector_v2.py` : statut confirmé (candidat futur, non actif) — commentaire ajouté dans `__init__.py`
- `cli/test_exploration.md` → `docs/manual_test_guide.md`
- `scripts/hdrctl_sim.bat` + `scripts/fix_es_json.py` → `_archive/`

### Détail P0
- **Fichier** : `internal/connector/__init__.py` ligne 11
- **Problème** : `from .parquet_connector import ParquetConnector` importe pyarrow inconditionnellement
- **Fix** : entourer d'un try/except comme dans `registry.py`
- **Impact** : 4 tests `TestRunReal` échouent sur tout env sans pyarrow (Linux sandbox, CI)

---

## Architecture Mosaïque (Vision Long Terme)

Hydra ne sera **pas un bloc monolithique** (cf. MS Fabric). L'architecture cible est une **architecture mosaïque distribuée** : des milliers d'instances Hydra autonomes, bien harmonisées entre elles, sans autorité centrale rigide.

### Principes
- Chaque instance Hydra = un **nœud autonome** capable d'exécuter jobs et workflows, d'exposer son API et de participer au réseau
- Les nœuds se découvrent et se coordonnent sans master/slave — topologie pair-à-pair
- Flexibilité : un step d'un workflow peut s'exécuter sur n'importe quel nœud disponible
- Résilience : pas de point de défaillance unique

---

## Règles Critiques pour Claude (à respecter dans TOUS les chats)

### Règle 0 — Ne jamais détruire une feature existante (PRIORITÉ ABSOLUE)

Avant toute modification d'un fichier frontend ou backend existant :

1. **Backup immédiat** du fichier (Règle 1 ci-dessous)
2. **Lire le fichier entier** (ou au minimum la section concernée + 50 lignes de contexte avant/après)
3. **Identifier toutes les features existantes** dans la zone touchée avant d'écrire quoi que ce soit
4. **N'éditer que ce qui est explicitement demandé** — ne jamais supprimer/déplacer du code non mentionné
5. **Vérifier après chaque edit** que les features identifiées à l'étape 3 sont toujours présentes

Pour les fichiers Studio critiques, exécuter le backup groupé avant toute session de modifications :
```bash
bash /sessions/.../mnt/Hydra/studio/scripts/backup_studio.sh
```
Les backups sont dans `studio/src/_backups/YYYYMMDD_HHMMSS/` — 22 fichiers couverts.

**Fichiers à très haut risque** (> 800 lignes, modifications fréquentes) :
- `studio/src/pages/workflows/WorkflowEditor.tsx` (~1400 lignes) — toujours lire la section complète avant d'éditer
- `cli/hdrctl.py` (~1259 lignes) — modifier via script Python ou Edit avec contexte suffisant

### Règle 1 — Backup avant toute modification

Avant de modifier un fichier quelconque, toujours faire un backup horodaté :

```bash
mkdir -p /sessions/.../mnt/Hydra/_backups
cp <fichier> /sessions/.../mnt/Hydra/_backups/<fichier>.<YYYYMMDD_HHMMSS>.bak
```

Le dossier `_backups/` est dans `.gitignore`. En cas de casse : restaurer depuis le backup, pas reconstruire de mémoire.

### Règle 2 — Écriture sécurisée sur mount Linux→NTFS (OBLIGATOIRE)

**Problème** : écriture d'un gros fichier via `f.write(content)` en une seule fois sur le mount Linux→Windows NTFS = troncature silencieuse au-delà de ~32KB.

**Solution** : utiliser `safe_write()` depuis `/sessions/.../mnt/outputs/safe_write.py` qui :
1. Fait le backup horodaté automatiquement
2. Écrit par chunks de 50 lignes (évite la troncature)
3. Vérifie la taille sur disk après écriture — lève une exception si troncature détectée

```python
import sys
sys.path.insert(0, '/sessions/happy-focused-wright/mnt/outputs')
from safe_write import safe_write

safe_write('/sessions/happy-focused-wright/mnt/Hydra/chemin/vers/fichier.tsx', content)
```

**Ne jamais utiliser** pour les fichiers sur le mount NTFS :
- `open(path, 'w').write(full_content)` sur un fichier > 200 lignes
- L'outil `Edit` pour des remplacements multi-blocs sur gros fichiers (risque de collision)
- `echo` / `cat >>` shell pour écrire du contenu long

**Toujours vérifier après écriture** :
```bash
wc -l fichier  # comparer avec le nombre de lignes attendu
```
