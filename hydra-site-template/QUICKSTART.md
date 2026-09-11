# QUICKSTART — Build the site locally

Vous êtes dans `hydra-site/`. Le serveur tourne sur `http://localhost:4321/`. Voici comment monter le site sans GitHub.

---

## Commandes essentielles

```bash
# Serveur de développement (rechargement auto)
pnpm dev

# Build production
pnpm build

# Vérifier le build (simule GitHub Pages)
pnpm preview

# Tuer le serveur
Ctrl+C
```

---

## Structure des pages

### Page statique simple

```astro
---
import BaseLayout from '../layouts/BaseLayout.astro';
---

<BaseLayout title="Mon titre" description="Description courte">
  <h1>Mon titre</h1>
  <p>Contenu statique.</p>
</BaseLayout>
```

### Page avec composant React interactif

```astro
---
import BaseLayout from '../layouts/BaseLayout.astro';
import HydraCore from '../components/HydraCore.jsx';
---

<BaseLayout title="Traducteur Airflow">
  <HydraCore client:visible tool="airflow" />
</BaseLayout>
```

Le `client:visible` signifie : charger le JavaScript seulement quand l'utilisateur scrolle jusqu'à ce composant.

---

## Pages à créer — ordre de priorité

### Phase 1 : Pages statiques (2-3 heures)

#### 1. `/guide`
- Source : `../documentations/mockups/guide.html`
- Fichier : `src/pages/guide.astro`
- Contenu : copier le HTML, envelopper dans BaseLayout
- Temps : 20 min

**Exemple :**
```astro
---
import BaseLayout from '../layouts/BaseLayout.astro';
---

<BaseLayout title="Guide" description="La documentation Hydra">
  <!-- Copier tout le contenu du <body> de guide.html -->
  <h1>Guide Hydra</h1>
  <p>...</p>
</BaseLayout>
```

#### 2. `/migrate`
- Source : `../documentations/mockups/migrate.html`
- Fichier : `src/pages/migrate.astro`
- Contenu : copier, envelopper
- Temps : 20 min

#### 3. `/playground`
- Source : `../documentations/mockups/playground.html`
- Fichier : `src/pages/playground.astro`
- Contenu : copier tout le `<script>` aussi (c'est du JavaScript pur)
- Temps : 20 min

**Important :** le JavaScript de playground.html est utilisable tel quel. Mettez-le dans un bloc `<script>` à la fin de la page.

#### 4. `/build`
- Source : `../documentations/mockups/dsl-builder.html`
- Fichier : `src/pages/build.astro`
- Contenu : copier + script
- Temps : 20 min

#### 5. `/learn` (réalignée charte)
- Source : `../documentations/mockups/learn.html`
- Fichier : `src/pages/learn.astro`
- **Attention :** réduire à ≤ 250 mots de prose (voir `../documentations/CHARTE_SITE.md`)
- Temps : 30 min

**Résultat phase 1 :** 5 pages, site à 50 %.

---

### Phase 2 : Fiches de référence (2-3 heures)

#### 6. `/reference/operations/filter`
- Source : `../documentations/mockups/fiche-filter.html`
- Fichier : `src/pages/reference/operations/filter.astro`
- Contenu : copier, envelopper
- Temps : 15 min

#### 7–21. Dupliquer pour les autres opérations (14 copies)

Copier `src/pages/reference/operations/filter.astro` 14 fois :
```
select.astro, rename.astro, cast.astro, aggregate.astro, sort.astro, 
deduplicate.astro, fill_null.astro, derive.astro, calculate.astro, 
pivot.astro, unpivot.astro, clean.astro, trim.astro, index.astro
```

Modifier juste le titre et la description dans le frontmatter.

**Temps :** 1 min × 14 = 15 min.

#### 22. `/reference/operations` (index)
- Fichier : `src/pages/reference/operations.astro`
- Contenu : liste avec liens vers chaque opération
- Temps : 15 min

#### 23–29. Connectors (7 fiches, même pattern)

```
src/pages/reference/connectors/csv.astro
src/pages/reference/connectors/json.astro
src/pages/reference/connectors/parquet.astro
src/pages/reference/connectors/mysql.astro
src/pages/reference/connectors/postgresql.astro
src/pages/reference/connectors/mongodb.astro
src/pages/reference/connectors/webapi.astro
```

Contenu : copier depuis la documentation Hydra ou des blocs simples.

**Temps :** 15 × 7 = 1 h 45.

**Résultat phase 2 :** 25 pages (fiches + index), site à 80 %.

---

### Phase 3 : Pages Learn et autres (1-2 heures)

#### 30. `/learn` (index)
- Fichier : `src/pages/learn.astro`
- Contenu : liste des 5 leçons
- Temps : 15 min

#### 31–35. Leçons (5 pages)
```
src/pages/learn/first-job.astro      ← déjà dans mockups/learn.html
src/pages/learn/transformations.astro
src/pages/learn/connectors.astro
src/pages/learn/workflows.astro
src/pages/learn/next.astro
```

Contenu : court (max 250 mots), avec un contrôle interactif chaque fois.

**Temps :** 20 min × 5 = 1 h 40.

#### 36. `/studio`
- Fichier : `src/pages/studio.astro`
- Contenu : nouvelle page de présentation (pas de simulateur)
- Temps : 20 min

#### 37. `/install`
- Fichier : `src/pages/install.astro`
- Contenu : **critique** — cible de tous les tunnels, guide `pip install` + `hdrctl`
- Temps : 45 min

**Résultat phase 3 :** 100 % du site statique (37 pages).

---

## Workflow rapide pour chaque page

### Exemple : créer `/guide`

```bash
# 1. Ouvrir la maquette
code ../documentations/mockups/guide.html

# 2. Créer le fichier Astro
code src/pages/guide.astro

# 3. Écrire (copier-coller du HTML)
---
import BaseLayout from '../layouts/BaseLayout.astro';
---

<BaseLayout title="Guide" description="La documentation Hydra">
  <!-- Coller le HTML ici -->
</BaseLayout>

# 4. Sauvegarder
# → pnpm dev rechargera auto

# 5. Vérifier sur http://localhost:4321/guide
```

---

## Fichiers à copier depuis mockups/

| Page | Maquette | Cible |
|---|---|---|
| `/guide` | guide.html | `src/pages/guide.astro` |
| `/migrate` | migrate.html | `src/pages/migrate.astro` |
| `/playground` | playground.html | `src/pages/playground.astro` |
| `/build` | dsl-builder.html | `src/pages/build.astro` |
| `/learn` | learn.html | `src/pages/learn.astro` |
| `/reference/operations/filter` | fiche-filter.html | `src/pages/reference/operations/filter.astro` |

---

## CSS global

Tous les styles sont dans `src/styles/global.css` — variables CSS, couleurs, responsive.

**N'ajoutez pas de styles inline.** Utilisez les variables :

```css
color: var(--text);
background: var(--bg-panel);
border: 1px solid var(--border);
```

Voir la liste complète dans `global.css`.

---

## Checklist avant de pousser sur GitHub

- [ ] Toutes les pages chargent (zéro 404)
- [ ] Clavier complet (Tab, Enter, Escape)
- [ ] Pas d'appel réseau au load (DevTools → Network)
- [ ] ≤ 250 mots de prose par page
- [ ] Aucun secret en clair
- [ ] Tous les liens résolvent
- [ ] Lighthouse budgets respectés (< 50 ko JS)

Lancez :
```bash
pnpm build
```

Si le build échoue → corrigez les erreurs avant de pousser.

---

## Structure finale (37 pages)

```
src/pages/
├── index.astro                    # /
├── guide.astro                    # /guide
├── migrate.astro                  # /migrate
├── playground.astro               # /playground
├── build.astro                    # /build
├── learn.astro                    # /learn
├── install.astro                  # /install
├── studio.astro                   # /studio
├── learn/
│   ├── first-job.astro            # /learn/first-job
│   ├── transformations.astro      # /learn/transformations
│   ├── connectors.astro           # /learn/connectors
│   ├── workflows.astro            # /learn/workflows
│   └── next.astro                 # /learn/next
├── reference/
│   ├── operations.astro           # /reference/operations
│   ├── connectors.astro           # /reference/connectors
│   ├── operations/
│   │   ├── filter.astro           # /reference/operations/filter
│   │   ├── select.astro           # ...
│   │   └── (13 autres)
│   └── connectors/
│       ├── csv.astro              # /reference/connectors/csv
│       └── (6 autres)
└── migrate/
    ├── airflow.astro              # /migrate/airflow (phase 4+)
    ├── dagster.astro              # ...
    └── (4 autres)
```

---

## Tâches par session

**Session 1 (2-3h) : Phase 1**
- Créer `/guide`, `/migrate`, `/playground`, `/build`, `/learn`
- 5 pages ✓

**Session 2 (2-3h) : Phase 2**
- Créer `/reference/operations` + 15 fiches
- Index et structure
- 17 pages ✓

**Session 3 (1-2h) : Phase 3**
- Leçons learn, `/studio`, `/install`
- 8 pages ✓

**Résultat :** 30 pages sans effort, site 85 % complet.

---

## Notes

- Les maquettes HTML utilisent leurs propres styles — conservez-les en copiant `<style>` aussi
- Si une maquette a du JavaScript, collez-le dans un bloc `<script>` Astro
- Les variables CSS vont surcharger certains styles — c'est intentionnel (cohérence)
- Testez chaque page en local avant de continuer
- Commit régulièrement : `git add .` → `git commit -m "feat: add /guide page"`

---

## Ressources

| Fichier | Utilité |
|---|---|
| `../documentations/CHARTE_SITE.md` | 10 règles avant chaque commit |
| `../documentations/mockups/` | Toutes les maquettes HTML |
| `src/styles/global.css` | Toutes les variables CSS |
| `src/layouts/BaseLayout.astro` | Template pour toutes les pages |

---

## Prochaine étape

Ouvrez une **nouvelle discussion** en disant "je suis dans hydra-site/" et je vous ferai les 5 premières pages en live.

