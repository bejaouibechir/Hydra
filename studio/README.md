# Hydra Studio

Éditeur visuel pour **Hydra DSL** — un IDE web qui conçoit des jobs ETL et orchestre des workflows sur un canvas, tout en gardant le **DSL YAML comme source de vérité exécutable**.

Le canvas n'invente aucun format propriétaire : il lit et écrit de vrais fichiers Hydra (`sources.yaml`, `transformations.yaml`, `destinations.yaml`, `pipeline.yaml`, `workflow.yaml`). La conversion est bidirectionnelle et sans perte :

```
DSL écrit à la main  ↔  Hydra Studio  ↔  moteur Hydra (CLI / API)
```

---

## Prérequis

- **Node.js ≥ 18** et npm (front-end)
- **Python ≥ 3.9** avec le paquet Hydra installé (`pip install -e .` à la racine du dépôt) pour l'API
- L'API dépend notamment de `fastapi`, `uvicorn`, `APScheduler` (voir `requirements.txt` racine)

---

## Installation

```bash
# À la racine du dépôt : dépendances Python (API + moteur)
pip install -r requirements.txt
pip install -e .

# Front-end Studio
cd studio
npm install
```

---

## Démarrage

Studio a besoin de **deux processus** : l'API (backend) et le serveur de dev Vite (front).

**1. L'API** (port `5678` par défaut) — depuis la racine du dépôt :

```bash
hdrctl serve
# options : --host 0.0.0.0  --port 5678  --reload  --workspace <dossier>
# équivalent direct : uvicorn api.main:app --reload --port 5678
```

**2. Le Studio** (port `5173`) — depuis `studio/` :

```bash
npm run dev
```

Ouvre ensuite **http://localhost:5173**. Le serveur Vite proxifie automatiquement `/api` vers `http://127.0.0.1:5678` (voir `vite.config.ts`), donc aucune configuration CORS n'est nécessaire en développement.

---

## Variables d'environnement

| Variable | Portée | Rôle | Défaut |
|----------|--------|------|--------|
| `VITE_API_URL` | Front | Base des appels API. En dev, laisser vide pour passer par le proxy Vite. | `/api` |
| `HYDRA_WORKSPACE` | API | Dossier racine des projets Studio. | `~/hydra-workspace` |
| `HYDRA_LANG` | Moteur/CLI | Langue de la CLI (`en` / `es`). | auto |

---

## Scripts npm

| Script | Effet |
|--------|-------|
| `npm run dev` | Serveur de dev Vite + HMR (port 5173) |
| `npm run build` | Vérification de types (`tsc -b`) puis build de production |
| `npm run preview` | Sert le build de production localement |
| `npm run lint` | ESLint |
| `npm run test` | Tests unitaires (Vitest, une passe) |
| `npm run test:watch` | Vitest en mode watch |

---

## Architecture

| Brique | Choix |
|--------|-------|
| UI | React 18 + TypeScript strict |
| Canvas | React Flow (`@xyflow/react` v12) |
| État serveur | React Query (`@tanstack/react-query`) |
| Édition YAML / Python | CodeMirror |
| Build / dev | Vite 6 |
| Tests | Vitest |
| Styles | Tailwind CSS |

Points de repère dans `src/` :

- `lib/api.ts` — client API **typé** ; unique point de contact avec le backend.
- `lib/workflowSerializer.ts` — conversion `React Flow ↔ workflow.yaml` (sérialisation via `js-yaml`, typée et sans perte).
- `lib/hdrSerializer.ts` — conversion `React Flow ↔ 4 fichiers YAML d'un job`.
- `lib/nodeRegistry.ts` — catalogue des types de nœuds (sources, transformations, destinations, actions, control flow).
- `lib/nodeValidation.ts` — validité d'un nœud (badge) et validité d'une connexion (`validateConnection`).
- `lib/dag.ts` — tri topologique + validation du graphe (cycles).
- `pages/workflows/WorkflowEditor.tsx` — l'éditeur (deux scènes : **workflow** = orchestration de jobs, **job** = source → transformations → destination).
- `contexts/NotificationContext.tsx` — notifications in-app.

### Deux scènes

- **Workflow configuration** : orchestration de jobs + actions (log, webhook, shell, SSH, delay, condition…), politiques d'erreur/retry, conteneurs (Sequence / Error-scope / Retry-scope), triggers.
- **Job configuration** (double-clic sur un nœud Job) : un pipeline atomique `1 source → N transformations → 1 destination`, matérialisé sur disque en 4 fichiers YAML.

---

## Formats DSL pris en charge

- **Workflow** : `workflow.yaml` (`trigger` manual / schedule / webhook, `steps` avec `depends_on`, `on_failure`, `retry`, `when`, `enabled`).
- **Job** : `sources.yaml`, `transformations.yaml`, `destinations.yaml`, `pipeline.yaml` — ou un `.hdr` unique équivalent.

Import/export : le Studio ouvre un projet existant construit à la CLI ou à la main, et tout job créé au canvas reste exécutable par `hdrctl`.

---

## Tests

```bash
cd studio
npm run test
```

Couverture actuelle centrée sur les **sérialiseurs** (partie critique) :

- `lib/workflowSerializer.test.ts` — round-trip `workflow.yaml`, fidélité des types, round-trip `flow → workflow`, exclusion des conteneurs, héritage Error-scope.
- `lib/hdrSerializer.test.ts` — round-trip des 4 fichiers YAML d'un job, sources/destinations multiples, fidélité des types, génération du canvas.
- `lib/dag.test.ts` — tri topologique et détection de cycles.

---

## Limites connues (v1)

- **Logs de run non temps réel** : le suivi se fait par polling ; les logs d'un run apparaissent au fil des groupes de steps, pas en streaming ligne à ligne.
- **Auth mono-utilisateur** : pas d'authentification ni de multi-utilisateur en v1.
- **Persistance fichiers** : tout est stocké en YAML sur disque (pas de base de données).
- **Secrets** : ne saisis jamais un mot de passe en clair dans un nœud. Utilise une **référence** `${ENV:NOM}` ; la valeur réelle se définit dans **Environnements** (fichiers `.env.<env>`, hors Git) et le moteur la résout à l'exécution. Les champs mot de passe du Studio affichent un rappel et signalent toute valeur en clair.
- **Routage multi-destinations au niveau workflow** : la fusion/jointure multi-sources existe au niveau **job** (`merge` / `join` / `union`) ; le routage vers plusieurs destinations au niveau orchestration reste à venir.
