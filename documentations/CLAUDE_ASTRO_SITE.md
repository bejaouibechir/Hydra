# CLAUDE.md — hydraetl.com Site

Instructions pour tout travail sur le site Astro. À lire en premier.

---

## Vue d'ensemble

**hydraetl.com** est une **documentation interactive** du produit Hydra ETL. Pas de app, pas de serveur — du HTML statique servi depuis GitHub Pages, avec du JavaScript client pour les interactifs.

**Trois principes structurants :**

1. **Montrer avant d'argumenter** — chaque page commence par un geste, pas un paragraphe
2. **Zéro serveur** — tout côté client, tout statique, pas une ligne de backend
3. **Honnêteté** — un cas non supporté est affiché en rouge, jamais omis

---

## Architecture

### Stack

- **Astro 5** — compilateur HTML/CSS/JS, sortie statique
- **React pour les îlots uniquement** — traducteurs, playground, générateur de DSL
- **Zéro dépendances externes** dans les îlots — pas Tailwind, pas MaterialUI
- **Shiki** — coloration des blocs de code (exécutée à la compilation)
- **Pagefind** — recherche côté client, index statique
- **GitHub Pages** — hébergement + CI/CD
- **Lighthouse CI** — budgets de performance bloquants

### Séparation : Pages vs Îlots

| Type | Tech | Exemple | Rechargement |
|---|---|---|---|
| Page statique | Astro + CSS | `/guide`, `/learn`, `/reference` | À la main |
| Avec interactif | Astro + React | `/migrate/airflow`, `/playground` | Au clic (client:visible) |
| Au chargement | Astro + React | Bientôt : `/install` | Immédiat (client:load) |

---

## Charte du site — version courte

**Lire intégralement** : `documentations/CHARTE_SITE.md`

### Les 10 règles en 5 minutes

1. **Montrer avant d'argumenter** — contrôle interactif dans les 5 premières secondes
2. **≤ 250 mots de prose** par page, hors code et diagrammes
3. **Jamais de silence** — cas non supporté = affiché en couleur d'erreur
4. **Statique par défaut** — zéro appel réseau au chargement, budgets Lighthouse bloquants
5. **Pas de dépendance sans raison** — justifier chaque `npm install`
6. **Accessibilité non négociable** — clavier, contraste AA, 44px tactiles
7. **Pas de secrets en clair** — afficher `${SECRET.X}`, jamais une valeur
8. **Anglais, ton factuel** — pas de superlatif, pas d'emoji, pas de « révolutionnaire »
9. **Gabarits cohérents** — même structure pour toutes les fiches de référence
10. **Tout vérifiable** — links checker, linter, tests Playwright

### Avant merge : checklist

- [ ] Première interaction en < 5 sec
- [ ] ≤ 250 mots de prose visible
- [ ] Cas non supportés affichés
- [ ] Budgets Lighthouse OK
- [ ] Aucun appel réseau au load
- [ ] Clavier complet
- [ ] Aucun secret, aucun formulaire d'identifiants
- [ ] Tous les liens résolvent
- [ ] Interactions testées par script

---

## Conversion des maquettes en pages

### Deux catégories

**Statique** → `.astro` pur, pas de JavaScript interactif
```astro
---
import BaseLayout from '../../layouts/BaseLayout.astro';
---
<BaseLayout title="Guide">
  <h1>Le job, unité atomique</h1>
  <p>Un job combine une source, des opérations et une destination.</p>
</BaseLayout>
```

**Interactif** → `.astro` + composant React en îlot
```astro
---
import HydraCore from '../../components/HydraCore.jsx';
---
<BaseLayout title="Migrate from Airflow">
  <HydraCore client:visible tool="airflow" initialState={{...}} />
</BaseLayout>
```

### Ordre de portage

1. **`/migrate/airflow`** en premier — valide la chaîne complète
2. Puis les 5 autres tunnels — 400 lignes par outil
3. Pages statiques — guide, learn, reference
4. Fiches de référence — générées depuis le code

---

## Le noyau des tunnels — HydraCore.jsx

**Partagé entre les 6 traducteurs.**

```javascript
// Ce qui est unique par outil (400 lignes)
airflow.patterns.js        // @dag, BranchPythonOperator, XCom, etc.
dagster.patterns.js        // @asset, IO managers, partitions, etc.
prefect.patterns.js        // @flow, @task, .serve(), etc.
dbt.patterns.js            // sources.yml, Python models, etc.
databricks.patterns.js     // Notebooks, bundles, Quartz cron, etc.
airbyte.patterns.js        // Connections, streams, low-code, etc.

// Ce qui est partagé (1500+ lignes)
hydra-core-lib.js          // Tokenizer, lint, menus contextuels, icônes
HydraCore.jsx              // Composant React enveloppe
```

**À ne jamais dupliquer.** Une correction du tokenizer = une seule ligne à changer, pas six.

---

## Budgets strictes (règle 4)

| Métrique | Seuil | Vérification |
|---|---|---|
| JavaScript total | 50 ko | `pnpm test:lighthouse` |
| LCP (4G lent) | 1,5 s | Lighthouse CI |
| CLS (stabilité) | 0,1 | Lighthouse CI |
| Images | AVIF + lazy load | `astro:assets` |
| Polices | Système uniquement | `grep webfont` → 0 hits |
| Appels réseau au load | 0 | Dev tools → Network |

Un seul appel réseau au chargement → **page rejetée en CI.**

---

## Fichiers critiques

| Fichier | Rôle | Erreur commune |
|---|---|---|
| `public/.nojekyll` | Dit à GitHub Pages de skip Jekyll | L'oublier = site sans CSS/JS |
| `public/CNAME` | Configure le domaine personnalisé | Vide ou absent = `*.github.io` |
| `astro.config.mjs` | `base: '/'`, `site: 'https://hydraetl.com'` | `base: ''` casse les chemins |
| `src/styles/global.css` | Variables CSS, jetons de couleur | Modifier sans mise à jour des 12 pages = chaos |
| `src/components/HydraCore.jsx` | Noyau des 6 tunnels | Dupliquer au lieu de partager = 6x les bugs |

---

## Nommage et conventions

### URLs et fichiers

- `/migrate/airflow` → `src/pages/migrate/airflow.astro`
- `/learn/first-job` → `src/pages/learn/first-job.astro`
- Minuscules, tirets, pas d'extension `.html`

### Variables CSS

```css
--bg              /* Arrière-plan principal */
--bg-soft         /* Légèrement plus clair */
--bg-panel        /* Panels/cards */
--bg-code         /* Blocs de code */

--text            /* Texte principal */
--text-soft       /* Secondaire */
--text-mut        /* Muet, annotation */

--accent          /* Primaire, action */
--accent-soft     /* Hover, highlight */
--accent-text     /* Texte sur accent */

--ok / --warn / --err   /* États */
--border / --border-strong

--mono / --sans   /* Polices */
```

Pas de `--purple`, `--blue`, `--red` — utiliser l'intention, pas la couleur.

### Jetons React

```jsx
<div client:visible>           {/* Hydrate au scroll */}
<div client:idle>              {/* Hydrate quand navigateur est libre */}
<div client:only="react">      {/* React côté client uniquement */}
```

Jamais `client:load` sauf bonne raison — chaque îlot ralentit le FCP.

---

## Sécurité

### Jamais

- De formulaire demandant un identifiant ou mot de passe
- De clé API, token ou secret affiché
- D'appel API externe depuis le client (CORS, exposition)
- De stockage localStorage pour les données sensibles

### Toujours

- Afficher `${SECRET.MY_VAR}` à la place d'une vraie valeur
- Valider les entrées utilisateur au lint (règle 3)
- Lister ce qui **ne peut pas** être traduit (règle 3)
- Expliquer où l'utilisateur doit aller ensuite (`/install`)

---

## Tests et vérification

### Avant commit local

```bash
# Linter
pnpm lint:js

# Build
pnpm build

# Vérifier qu'il n'y a pas de secrets
grep -r "password\|api_key\|secret=" src/
```

### Avant PR

GitHub Actions lance :
1. **Lint** — ESLint sur `.js`, `.jsx`, `.astro`
2. **Build** — `pnpm build` doit réussir
3. **HTML lint** — `htmlhint` sur `dist/`
4. **Tests** — Playwright sur les pages interactives
5. **Lighthouse** — budgets bloquants

Une étape échoue = PR bloquée.

### Test local complet (simule GitHub Pages)

```bash
pnpm build
pnpm preview
# Ouvrir http://localhost:3000
# Tester le clavier, la recherche, les thèmes
# Ouvrir DevTools > Network, vérifier zéro appel au chargement
```

---

## Workflows des tâches courantes

### Ajouter une page statique

```
src/pages/guide/scheduling.astro
---
import BaseLayout from '../../layouts/BaseLayout.astro';
---
<BaseLayout title="Scheduling" description="Déclencheurs et backfill">
  <h1>Déclencher les workflows</h1>
  <p>Trois types : manual, schedule (cron), webhook.</p>
</BaseLayout>
```

Puis commit, push → GitHub Actions compile automatiquement.

### Ajouter une fiche de référence

Deux cas :

**À la main :** copier `src/pages/reference/operations/filter.astro`, adapter le contenu

**Généré :** si la fiche peut être extraite du code Hydra (Pydantic, docstrings), créer un générateur :
```javascript
// scripts/gen-reference.js
const spec = require('hydra-etl/spec');
spec.operations.forEach(op => {
  const content = `...`;
  fs.writeFileSync(`src/pages/reference/operations/${op.name}.astro`, content);
});
```

Lancer au build : `"build": "node scripts/gen-reference.js && astro build"`

### Modifier les jetons CSS

Éditer `src/styles/global.css` → s'applique à toutes les 12 pages.

**Avant merge :**
- Vérifier qu'aucune variable n'est orpheline
- Tester en mode clair et sombre
- Vérifier contraste AA sur tous les états (normal, hover, active, disabled)

### Corriger un bug du traducteur Airflow

```
src/components/tools/airflow.patterns.js
```

La correction est **automatiquement partagée** avec les 5 autres outils grâce au noyau commun. Aucune duplication.

---

## Feuille de route

**Phase 1 — Squelette (cette semaine)**
- Repo créé, CI en place, `.nojekyll` + `CNAME`
- `/migrate/airflow` en ligne
- Budgets Lighthouse validés

**Phase 2 — Tunnels (semaine 2)**
- 5 autres traducteurs
- Extraction du noyau commun

**Phase 3 — Contenu statique (semaine 3)**
- Guide, Learn, Reference
- Navigation

**Phase 4 — Fiches (semaine 4)**
- Générations depuis le code
- Déploiement complet

---

## Aide

- **Syntaxe Astro** → https://docs.astro.build
- **Lighthouse budgets** → https://github.com/GoogleChrome/lighthouse-ci/blob/main/docs/budget.md
- **Pagefind** → https://pagefind.app
- **Accessibilité WCAG AA** → https://www.w3.org/WAI/WCAG21/quickref/

**Questions sur la charte ?** Lire `documentations/CHARTE_SITE.md` section par section.

**Questions sur l'arborescence ?** Lire `documentations/SITEMAP.md`.

