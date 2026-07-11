# Hydra ETL — Handoff Document
> État au 16 juin 2026 (mis à jour après session architecture Studio). À lire avant toute intervention sur ce codebase.

---

## 1. Vision Produit

**Hydra** est une plateforme data en 3 moteurs (les 3 têtes de l'hydre) :

| Engine | Statut | Description |
|---|---|---|
| **ETL Engine** | ✅ v1 en cours de finalisation | Framework ETL déclaratif + Studio visuel |
| **Feature Detection Engine** | 🔮 Futur | Feature engineering automatisé pour ML |
| **Execution Intelligence Engine** | 🔮 Futur | HydraLM + connecteurs MCP + intelligence pipeline |

**Modèle économique** : ETL Engine gratuit/open-source → engines supérieurs payants.  
**Domaine** : hydraetl.com (acheté, prévu pour documentation style Kubernetes via GitHub Pages).

---

## 2. Architecture Globale

```
Hydra/
├── cli/                    # CLI hdrctl / hydra (Click, Python)
│   ├── hdrctl.py           # ~1259 lignes — point d'entrée CLI
│   ├── i18n.py             # Internationalisation (en/es)
│   └── locales/            # en.json (111 clés), es.json (85 clés)
├── internal/               # Moteur Python
│   ├── connector/          # CSV, JSON, Parquet, MySQL, PostgreSQL, MongoDB, WebAPI
│   ├── engines/            # PandasEngine, DuckDBEngine
│   ├── parser/             # Parsers YAML source/transform/destination
│   ├── runner/executor.py  # Cœur du job runner
│   └── workflow/           # WorkflowParser + WorkflowRunner (DAG)
├── api/                    # FastAPI backend Studio
│   ├── main.py             # App FastAPI, CORS, routers
│   ├── store.py            # Persistence fichiers YAML (pas de DB)
│   └── routers/            # projects, workflows, runs, system, fs, export, terminal...
├── studio/                 # Frontend React + Vite
│   └── src/
│       ├── pages/workflows/WorkflowEditor.tsx   # Canvas principal (1577 lignes)
│       ├── components/canvas/                   # Nodes, Palette, Config dialogs...
│       └── lib/                                 # hdrSerializer, workflowSerializer, api, dag...
├── tests/                  # 49 tests CLI passants
├── plugins/                # Extensions (auth, cache, retry, pagination...)
└── docs/                   # Documentation (ce fichier + manual_test_guide.md)
```

### Principe fondamental : Job vs Workflow

- **Job** = unité atomique : `1 source → N transformations → 1 destination`
  - Fichiers : `sources.yaml` + `transformations.yaml` + `destinations.yaml` + `pipeline.yaml`
  - Exécuté en inline (HDR content) ou depuis un dossier disk

- **Workflow** = orchestrateur de jobs avec DAG
  - Fichier : `workflow.yaml` avec `steps` + `depends_on`
  - Supporte parallélisme implicite, webhooks, schedule (cron)

---

## 3. Ce qui est fait — Fonctionnalités complètes

### Backend Python
- ✅ CLI `hdrctl` / `hydra` — toutes commandes (run, validate, serve, workflow, list...)
- ✅ Job runner : CSV, JSON, Parquet, MySQL, PostgreSQL, MongoDB, WebAPI
- ✅ Engines : Pandas + DuckDB avec toutes transformations (filter, select, rename, cast, aggregate, sort, dedupe, derive, join...)
- ✅ Workflow runner : DAG + parallélisme + `depends_on` liste + actions (webhook, email, slack)
- ✅ Plugins : auth, cache, retry, circuit breaker, pagination, schema validation, secrets
- ✅ 49 tests CLI passants (`tests/test_cli_hdrctl.py`)

### API FastAPI (`hdrctl serve`)
- ✅ `GET/POST /api/projects` — gestion projets
- ✅ `GET/POST/PUT/DELETE /api/workflows` — CRUD workflows
- ✅ `POST /api/runs` — lancer un workflow depuis son path
- ✅ `POST /api/runs/inline` — lancer un job depuis HDR content (sans fichier disk)
- ✅ `POST /api/runs/inline/action` — exécuter un nœud action (bash/powershell/python/ssh/webhook)
- ✅ `GET /api/runs/{id}` — polling statut + logs + output_sample
- ✅ `GET /api/system/browse` — sélecteur fichiers/dossiers natif OS (Windows/macOS/Linux)
- ✅ `GET /api/fs/find-job-folder` — résolution chemin absolu d'un dossier job
- ✅ `POST /api/export/save` — save-as natif CSV/TXT
- ✅ `GET /api/nodes` — liste des types de nœuds disponibles
- ✅ `GET/POST /api/environments` — gestion variables d'env
- ✅ WebSocket terminal (`/api/terminal/ws`) — bash/powershell intégré

### Studio React (canvas)
- ✅ Canvas React Flow — drag & drop nœuds depuis palette
- ✅ Nœuds : 7 sources + 9 transformations + 6 destinations + 8 actions
- ✅ **Canvas deux niveaux** (implémenté session courante) :
  - Tab bar bas : `Workflow | Job1 | Job2 | +`
  - Breadcrumb contextuel : `← WorkflowName` / `← WorkflowName / JobName`
  - `viewMode` state : `'workflow' | { type: 'job'; jobId; jobName }`
  - `jobCanvasRef` (Map) : canvas par job, persistent en mémoire
  - `wfSnapshot` : snapshot du canvas workflow quand on entre dans un job
  - Save : préserve `job_canvases` dans le layout JSON
- ✅ **Sélecteur fichiers natif** dans NodeConfigDialog (tous les champs path)
  - Via `api/routers/system.py` — PowerShell sur Windows, osascript macOS, zenity Linux
- ✅ Undo/Redo (useUndoRedo hook)
- ✅ Import depuis dossier job (4 fichiers YAML) ou package .hdr
- ✅ Panel Output (données tabulaires, export CSV/TXT save-as natif)
- ✅ Panel Logs (polling 1.5s, durée, rows_in/out)
- ✅ Terminal intégré (bash/powershell)
- ✅ YAML/HDR code panel avec apply
- ✅ PropertiesPanel (side panel config nœud)
- ✅ NodeConfigDialog (config détaillée + browse boutons)
- ✅ Auto-save configurable (délai dans Settings)
- ✅ Validation DAG temps réel
- ✅ Multi-sélection + delete + preview transformation
- ✅ Run flottant (bouton bas canvas)
- ✅ Thèmes (dark/light) + minimap

---

## 4. Prochaines étapes prioritaires

### ⚠️ DÉCISION ARCHITECTURE STUDIO — 16 juin 2026

La navigation deux niveaux actuelle (double-clic drill-down via `viewMode`) est **remplacée** par une architecture à deux scènes explicites avec onglets. Voir section 11 pour le détail complet. Les items 4.1–4.7 ci-dessous restent valides comme base de code, mais le refactoring P1 va les réorganiser.

---

### P1 — Refactoring Studio : architecture Scene 1 / Scene 2

**Fichiers concernés** : `WorkflowEditor.tsx`, `NodePalette.tsx`, `nodeRegistry.ts`

**Ce qui change :**

1. **Deux onglets en haut** : `Jobs configuration` | `Workflow configuration`
2. **Tab bar bas** : en Scene 1 → jobs du workflow (job1, job2, +) | en Scene 2 → rien
3. **Breadcrumb** :
   - Scene 1 : `← wf1 < jobX  X nodes · Y edges` (← wf1 = retour projet)
   - Scene 2 : `← wf1` (← wf1 = retour projet)
4. **Clic nœud job dans Scene 2** → bascule vers Scene 1, onglet de ce job sélectionné
5. **Palette Scene 1** : Sources, Transformations, Destinations, Actions (pas de Control Flow)
6. **Palette Scene 2** : Actions | Control Flow | Jobs (liste des jobs définis) | Join | Split | Merge | Union
7. **Supprimer** la tab bar workflow du bas (actuelle `wfListQuery` → remplacée par breadcrumb)

**À implémenter :**
- [ ] Remplacer `viewMode` par `sceneMode: 'jobs' | 'workflow'` + `activeJobId: string | null`
- [ ] Deux onglets top-level (Scene switcher)
- [ ] Tab bar bas conditionnelle (jobs en Scene 1, vide en Scene 2)
- [ ] Breadcrumb mis à jour (← wf1 → `navigate(/projects/${projectId})`)
- [ ] Palette Scene 1 filtrée : source + transformation + destination + action
- [ ] Palette Scene 2 : action + control_flow + jobs (dynamic) + join/split/merge/union
- [ ] Section "Jobs" dans palette Scene 2 = nœuds draggables générés depuis la liste des jobs définis
- [ ] onClick sur nœud job en Scene 2 → `setSceneMode('jobs'); setActiveJobId(jobId)`

### P2 — Sérialisation workflow + jobs vers disk (bloqué par P1)

#### ✅ 4.1 NodePalette filtrée selon viewMode — FAIT
- `viewMode?: 'workflow' | 'job'` ajouté à la prop interface de `NodePalette.tsx`
- `visibleCategories` filtré : workflow → `action + control_flow` | job → `source + transformation + destination`
- `Package` importé dans lucide + ajouté au mapping LUCIDE

#### ✅ 4.2 Nœud `job` dans le registry — FAIT
Ajouté dans `studio/src/lib/nodeRegistry.ts` :
```typescript
{ type: 'job', label: 'Job', category: 'action', color: '#8b5cf6', icon: 'Package',
  description: 'Sous-pipeline ETL (source → transform → dest)', maxInputs: -1, maxOutputs: -1 }
```

#### ✅ 4.3 Double-clic nœud `job` → ouvre le canvas job — FAIT
`onNodeDoubleClick` dans `WorkflowEditor.tsx` mis à jour :
```typescript
if ((node.data as FlowNodeData).nodeType === 'job') {
  switchToJob(node.id, (node.data as FlowNodeData).label ?? node.id)
  return
}
```

#### ✅ 4.4 Menu contextuel sur les onglets job — FAIT
Bouton `⋯` (MoreHorizontal) sur chaque onglet job, ouvre un popup fixe avec :
- **Renommer** → déclenche l'inline input (identique au double-clic)
- **Supprimer** → désactivé si dernier job ; sinon `deleteJob()` bascule vers le job adjacent

State ajouté : `tabMenu: { jobId, x, y } | null`  
Fonction `deleteJob(jobId)` : protège contre suppression du dernier job, nettoie `jobCanvasRef`.  
Overlay transparent ferme le menu au clic extérieur. TypeScript : zéro erreur.

#### ✅ 4.5 Scène Workflow + nœuds Control Flow — FAIT
Clic sur le nom du workflow dans le breadcrumb → `switchToWorkflow()` (déjà câblé).

Palette en mode workflow : **Actions** + **Control Flow** seulement (plus aucun nœud source/transform/dest).

6 nœuds `control_flow` ajoutés dans `nodeRegistry.ts` (couleur orange `#f97316`) :

| Type | Label | Icône | Description |
|---|---|---|---|
| `cf_condition` | Condition | GitBranch | if / else selon condition |
| `cf_parallel` | Parallel | LayoutGrid | Lance N branches en parallèle |
| `cf_delay` | Delay | Clock | Pause temporelle |
| `cf_split` | Split | Scissors | 1 flux → N branches |
| `cf_merge` | Merge | GitMerge | N branches → 1 (attend toutes les fins) |
| `cf_join` | Join | Link2 | N flux → 1 sur clé commune |

`NodeCategory` étendu : `'source' | 'transformation' | 'destination' | 'action' | 'control_flow'`  
`NodeConfigDialog.tsx` + `NodePalette.tsx` : icônes ajoutées au mapping LUCIDE.

#### ✅ 4.6 jobId dans l'URL — FAIT
Navigation job → URL enrichie : `?projectId=xxx&jobId=yyy` (replace history, pas push).  
Retour workflow → `jobId` supprimé de l'URL. Deep-link : rechargement restaure le bon job.  
`setSp` ajouté dans `switchToJob`, `switchToWorkflow`, `addJob`.

#### ✅ 4.7 Icônes MySQL + PostgreSQL personnalisées — FAIT
Fichier : `studio/src/components/icons/DatabaseIcons.tsx`  
`MySQLIcon` (dauphin) + `PostgreSQLIcon` (éléphant) en style Lucide (stroke currentColor, strokeWidth 2).  
Référencés dans `nodeRegistry.ts` via `icon: 'MySQL'` / `icon: 'PostgreSQL'`.  
Ajoutés au mapping LUCIDE dans `NodePalette.tsx` et `NodeConfigDialog.tsx`.

#### ❌ 4.8 Sérialisation complète workflow avec jobs inline — EN ATTENTE (bloqué par P1)
**Fichier** : `studio/src/lib/workflowSerializer.ts`

Actuellement `flowToWorkflow()` génère un workflow avec `job: "./jobs/xxx.yaml"` (path externe).  
Pour les jobs créés inline dans Studio, il faut sauvegarder les jobs comme fichiers disk séparés.

**Décision actée** : fichiers séparés dans `{workflowDir}/jobs/{jobId}.yaml`.

**À implémenter** :
1. Dans `saveMut` (WorkflowEditor.tsx) : pour chaque jobId dans `jobCanvasRef`, appeler `flowToHdr(jobNodes, jobEdges, jobName)` et POST vers un endpoint `/api/workflows/{id}/jobs` qui écrit le fichier sur disk
2. Dans `api/routers/workflows.py` : ajouter `PUT /api/workflows/{id}/jobs/{jobId}` → écrit `{workflowDir}/jobs/{jobId}.yaml`
3. Dans `flowToWorkflow()` : référencer `./jobs/{jobId}.yaml` au lieu d'un path vide

### P2 — Documentation hydraetl.com
- MkDocs ou Docusaurus sur GitHub Pages
- Guide démarrage rapide (pip install, premier job)
- Référence YAML complète
- Guide Studio

### P3 — Tests Studio
- Tests unitaires `hdrSerializer.ts` (flowToHdr, parseHdr)
- Tests unitaires `workflowSerializer.ts`
- Tests e2e Studio (Playwright)

### P4 — Nœuds Control Flow restants
Dans le registry (✅ fait) mais pas encore implémentés dans `workflowSerializer.ts` :
- `union` — N flux → 1 (append rows)
- `loop` — itération sur une liste

---

## 5. Fichiers clés — État et taille actuelle

| Fichier | Lignes | Rôle | Notes |
|---|---|---|---|
| `studio/src/pages/workflows/WorkflowEditor.tsx` | ~1583 | Canvas principal | ⚠️ Très grand, modifier via script Python + safe_write |
| `studio/src/components/canvas/NodeConfigDialog.tsx` | 653 | Config nœud + browse | Browse natif OK sur Windows |
| `studio/src/lib/hdrSerializer.ts` | 454 | Sérialise job ↔ canvas | `flowToHdr`, `parseHdr`, `isJobBuilderCanvas` |
| `studio/src/lib/workflowSerializer.ts` | 369 | Sérialise workflow ↔ canvas | `flowToWorkflow`, `workflowToYAMLString` |
| `studio/src/lib/nodeRegistry.ts` | 86 | Définitions nœuds | ✅ Type `job` ajouté |
| `studio/src/components/canvas/NodePalette.tsx` | ~340 | Palette drag & drop | ✅ Prop `viewMode` ajoutée, filtrage actif |
| `api/routers/runs.py` | 578 | Endpoints run | inline, action, polling |
| `api/routers/system.py` | 212 | Browse natif OS | PowerShell/osascript/zenity |
| `api/routers/workflows.py` | 68 | CRUD workflows | layout JSON inclut `job_canvases` |
| `cli/hdrctl.py` | ~1259 | CLI complet | Modifier via script Python |

---

## 6. Contraintes techniques critiques

### Règle NTFS — Écriture gros fichiers (OBLIGATOIRE)
Écrire un fichier > ~32 KB depuis Linux→Windows NTFS via mount **tronque silencieusement** le fichier.

**Solution** : toujours utiliser `safe_write.py` :
```python
import sys
sys.path.insert(0, '/sessions/<session-id>/mnt/outputs')
from safe_write import safe_write
safe_write('/sessions/<session-id>/mnt/Hydra/chemin/fichier.tsx', content)
```
`safe_write` fait : backup horodaté + écriture par chunks de 50 lignes + fsync + vérification taille.

**Ne jamais** :
- `open(path, 'w').write(full_content)` sur fichier > 200 lignes
- `Edit` pour multi-blocs sur gros fichiers (risque collision)

**Lire les fichiers** : toujours via le tool `Read` (Windows-side), jamais `cat` bash (Linux voit des lignes tronquées par cache NTFS).

### Sessions Codex
Dans Codex, les paths mnt varient. Le schéma est :
```
C:\Users\DELL\Desktop\Hydra  →  /sessions/<session-id>/mnt/Hydra/
outputs dir                  →  /sessions/<session-id>/mnt/outputs/
```
Vérifier le session-id via `ls /sessions/` en début de session.

### Tests
```bash
# Tests CLI (doivent toujours passer — ne pas casser)
cd C:\Users\DELL\Desktop\Hydra
pytest tests/test_cli_hdrctl.py -x

# TypeScript Studio
cd studio
npx tsc --noEmit   # doit retourner sans output
```

### Installation
```bash
pip install -e .   # editable — pas besoin de réinstaller après modifs Python
```

---

## 7. Commandes de démarrage

```bash
# Lancer l'API + Studio
cd C:\Users\DELL\Desktop\Hydra
hdrctl serve          # démarre FastAPI sur :8000

cd studio
npm run dev           # démarre Vite sur :5173 (proxy /api → :8000)

# Ou directement
uvicorn api.main:app --reload --port 8000
```

---

## 8. Architecture du canvas deux niveaux (implémenté)

### State dans WorkflowEditor.tsx

```typescript
type ViewMode = 'workflow' | { type: 'job'; jobId: string; jobName: string }
const [viewMode, setViewMode] = useState<ViewMode>('workflow')
const jobCanvasRef = useRef(new Map<string, { nodes: Node[]; edges: Edge[] }>())
const [wfSnapshot, setWfSnapshot] = useState<{ nodes: Node[]; edges: Edge[] } | null>(null)
const isJobBuilder = viewMode !== 'workflow'
```

### Navigation
```typescript
// Retour workflow : sauvegarde job courant → restaure wfSnapshot
switchToWorkflow()

// Entrer dans un job : sauvegarde canvas courant → charge canvas du job
switchToJob(jobId: string, jobName: string)
```

### Nœuds "job" dans la tab bar
```typescript
// workflowJobNodes : nœuds de type 'job' du canvas workflow
// Source : nodes (si viewMode==='workflow') ou wfSnapshot.nodes (si mode job)
const workflowJobNodes = useMemo(() => {
  const source = viewMode === 'workflow' ? nodes : (wfSnapshot?.nodes ?? [])
  return source.filter(n => n.data.nodeType === 'job')
}, [viewMode, nodes, wfSnapshot])
```

### Persistance layout
Le layout sauvegardé en DB/YAML inclut :
```typescript
{
  nodes: Node[],          // canvas workflow
  edges: Edge[],          // edges workflow
  job_canvases: {         // un canvas par job
    [jobId]: { nodes: Node[], edges: Edge[] }
  }
}
```

---

## 9. API endpoints — Référence rapide

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Statut API |
| GET | `/api/projects` | Liste projets |
| POST | `/api/projects` | Créer projet |
| GET | `/api/workflows?project_id=...` | Liste workflows |
| GET | `/api/workflows/{id}?project_id=...` | Workflow + layout |
| PUT | `/api/workflows/{id}?project_id=...` | Update (layout + yaml_content) |
| POST | `/api/runs` | `{ workflow_path }` → Run |
| POST | `/api/runs/inline` | `{ hdr_content, job_name, work_dir }` → Run |
| POST | `/api/runs/inline/action` | `{ node_type, command, ... }` → Run |
| GET | `/api/runs/{id}` | Statut + steps + output_sample |
| GET | `/api/system/browse?type=file\|directory\|save_file&ext=.csv` | Sélecteur natif |
| GET | `/api/fs/find-job-folder?name=...` | Résolution path absolu |
| POST | `/api/export/save` | `{ content, suggested_name, fmt }` → Save-as |
| GET | `/api/nodes?category=source` | Types de nœuds |

---

## 10. Décisions techniques actées (ne pas remettre en question)

1. **Job = unité atomique** (1 source → 1 destination). Pas de multi-source dans un job.
2. **Workflow = orchestrateur** de jobs. Multi-source/multi-dest via workflow uniquement.
3. **Pas de base de données en v1** — tout est fichier YAML sur disk + layout JSON dans fichier workflow.
4. **`depends_on` est toujours une liste** dans workflow.yaml.
5. **Stack Studio** : FastAPI (backend) + React Flow (canvas) + APScheduler (triggers).
6. **Auth mono-user en v1** — pas de multi-user.
7. **Logs streaming** (WebSocket/SSE) reporté post-v1 — polling 1.5s suffit.
8. **Two-level canvas** : un seul état `nodes/edges` swappé à chaque changement de niveau (pas deux instances ReactFlow).
9. **Studio : deux scènes explicites** (Session 16 juin 2026) — voir section 11.

---

## 11. Architecture Studio — Deux scènes (décision 16 juin 2026)

### Vue d'ensemble

```
Projet → Workflow → [Scene 1: Jobs configuration | Scene 2: Workflow configuration]
```

Navigation par deux onglets en haut de l'éditeur. Le breadcrumb `← wf1` retourne toujours au projet.

### Scene 1 — Jobs configuration

| Élément | Contenu |
|---|---|
| Breadcrumb | `← wf1 < jobX  X nodes · Y edges` |
| Tab bar bas | job1, job2, job3, + (add / rename / delete) |
| Canvas | Pipeline du job sélectionné (source → transform → dest) |
| Palette | Sources · Transformations · Destinations · Actions |

- Clic sur un onglet job → canvas de ce job
- `← wf1` → `navigate(/projects/${projectId})`

### Scene 2 — Workflow configuration

| Élément | Contenu |
|---|---|
| Breadcrumb | `← wf1` |
| Tab bar bas | aucune |
| Canvas | DAG d'orchestration (jobs + control flow + actions) |
| Palette | Actions · Control Flow · Jobs · Join · Split · Merge · Union |

- Section **Jobs** dans la palette = liste dynamique des jobs définis en Scene 1 → draggables sur le canvas
- Clic sur un nœud job dans le canvas → bascule vers Scene 1, onglet de ce job
- Nœuds possibles : job, action_*, cf_condition, cf_parallel, cf_delay, cf_foreach (futur), cf_split, cf_merge, cf_join, cf_union

### State à refactoriser dans WorkflowEditor.tsx

```typescript
// AVANT (à remplacer)
type ViewMode = 'workflow' | { type: 'job'; jobId: string; jobName: string }
const [viewMode, setViewMode] = useState<ViewMode>('workflow')

// APRÈS
type SceneMode = 'jobs' | 'workflow'
const [sceneMode, setSceneMode] = useState<SceneMode>('jobs')
const [activeJobId, setActiveJobId] = useState<string | null>(null)
// jobCanvasRef et wfSnapshot : conserver tels quels
```

### Palette Scene 2 — sections

```
Actions       → action_webhook, action_email, action_bash, action_powershell, action_python, action_ssh
Control Flow  → cf_condition, cf_parallel, cf_delay (+ cf_foreach futur)
Jobs          → [dynamique] un nœud draggable par job défini en Scene 1
Join          → cf_join  (jointure sur clé entre flux de deux jobs)
Split         → cf_split (1 flux → 2 branches sur condition)
Merge         → cf_merge (N branches → 1, attend toutes les fins)
Union         → cf_union (N flux → 1 par append) — à ajouter dans nodeRegistry
```

### Ce qui disparaît

- Tab bar bas affichant les **workflows** du projet (`wfListQuery`) → supprimée
- Navigation entre workflows = breadcrumb `← wf1` → projet → sélection d'un autre workflow
- `viewMode` state → remplacé par `sceneMode` + `activeJobId`
