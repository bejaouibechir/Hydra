# Plan d'exécution — Mise en ligne de hydraetl.com

Feuille de route pour les trois semaines à venir.

---

## Semaine 1 : Squelette et validation

**Objectif :** Premier site live sur GitHub Pages avec une page valide.

### Jour 1–2 : Infra GitHub

- [ ] Créer le repo `hydra-site` sur GitHub (ou équivalent)
- [ ] Cloner localement
- [ ] Créer la structure Astro (voir `ASTRO_SETUP.md`)
- [ ] `public/.nojekyll` (fichier vide) ← **critique**
- [ ] `public/CNAME` avec `hydraetl.com`
- [ ] `.github/workflows/build.yml` — CI/CD complète
- [ ] Premier push `main`
- [ ] Vérifier que le workflow GitHub Actions s'exécute

**Livrable :** Repo fonctionnel, CI en place, premier build réussi (même si vide)

### Jour 3–5 : Page `/migrate/airflow`

Voir `MIGRATION_EXEMPLE.md` pour le détail.

- [ ] Convertir `mockups/migrate-airflow.html` en Astro
  - [ ] `src/pages/migrate/airflow.astro`
  - [ ] `src/components/HydraCore.jsx` (enveloppe React)
  - [ ] `src/components/tools/airflow.patterns.js` (620 lignes extraites)
  - [ ] `src/components/hydra-core-lib.js` (tokenizer partagé)
  - [ ] `src/styles/HydraCore.css` (styles)
- [ ] Tester localement : `pnpm dev` → `/migrate/airflow`
- [ ] Vérifier :
  - [ ] Paste fonctionne
  - [ ] Traduction DAG → YAML
  - [ ] Graphe SVG rendu
  - [ ] Aucun appel réseau au load
  - [ ] Clavier complet
- [ ] Build et preview : `pnpm build && pnpm preview`
- [ ] Lighthouse : < 50 ko JS, LCP < 1,5 s
- [ ] Push → site live

**Checkpoint :** `/migrate/airflow` accessible sur hydraetl.com

### Jour 6–7 : Validation et nettoyage

- [ ] Vérifier `.nojekyll` est bien en place (GitHub Pages)
- [ ] Vérifier `CNAME` configure le domaine
- [ ] Test clavier complet
- [ ] DevTools : Network vide au chargement
- [ ] Test depuis téléphone
- [ ] Lighthouse audit local
- [ ] Archiver les maquettes : `mockups/ → _archive/mockups/`

**Livrable :** Site en production, première page validée, CI automatisée

---

## Semaine 2 : Les 5 autres tunnels

**Objectif :** `/migrate/*` pour tous les outils.

### Jour 8–12 : Portage des 5 outils

Réutiliser le pattern `/migrate/airflow`, adapter pour chaque outil.

- [ ] `/migrate/dagster`
  - [ ] Extraire `mockups/migrate-dagster.html`
  - [ ] `src/components/tools/dagster.patterns.js` (detection: @asset, multi-asset, checks, IO managers, etc.)
  - [ ] Tester
- [ ] `/migrate/prefect`
  - [ ] `src/components/tools/prefect.patterns.js` (@flow, @task, .serve(), Secret, async)
- [ ] `/migrate/dbt`
  - [ ] `src/components/tools/dbt.patterns.js` (sources.yml → ingestion, Python models)
- [ ] `/migrate/databricks`
  - [ ] `src/components/tools/databricks.patterns.js` (notebooks, bundles, Quartz)
- [ ] `/migrate/airbyte`
  - [ ] `src/components/tools/airbyte.patterns.js` (connections, streams, secrets)

Chaque fichier `.patterns.js` fait ~400 lignes. **Zéro duplication grâce au noyau commun.**

### Jour 13–14 : Nettoyage du noyau

- [ ] Vérifier que `HydraCore.jsx` est vraiment partagé par les 6
- [ ] Extraire tous les patterns communs dans `hydra-core-lib.js`
- [ ] Chaque outil ne doit apporter que ses motifs reconnaître (`lintPy`, `lintYaml`, etc.)
- [ ] Tests Playwright sur les 6 pages

**Livrable :** `/migrate/` complet et fonctionnel

---

## Semaine 3 : Contenu et fiches

**Objectif :** Pages statiques et début de référence.

### Jour 15–17 : Pages statiques

Toutes les pages sans interactif — aucun JavaScript côté client.

- [ ] `/` (accueil) — maquette et contenu
- [ ] `/install` — **critique** : cible de tout tunnels, guide `pip install` + hdrctl
- [ ] `/playground` → portage de `mockups/playground.html`
- [ ] `/build` → portage de `mockups/dsl-builder.html`
- [ ] `/guide` et sous-pages
- [ ] `/learn` → alignment sur CHARTE_SITE (max 250 mots, ajouter les 4 leçons manquantes)
- [ ] `/studio` — page de présentation (pas de simulateur)

Temps par page : 30–60 min (1 Astro statique + CSS)

### Jour 18–20 : Fiches de référence

Deux stratégies :

**À la main (rapide)**
- [ ] Copier `src/pages/reference/operations/filter.astro`
- [ ] Dupliquer 14 fois pour les autres opérations
- [ ] Duplicater pour connecteurs et plugins

**Générées (scalable)**
- [ ] Créer un script `scripts/gen-reference.js`
- [ ] Lire le spec Hydra (Pydantic + docstrings)
- [ ] Générer les `.astro` à la compilation
- [ ] Intégrer à `pnpm build`

Recommandation : **à la main d'abord, généré en phase 4.**

### Jour 21 : Validation et déploiement

- [ ] Tous les liens résolvent (linkinator)
- [ ] Aucun secret en clair (grep)
- [ ] Lighthouse budgets sur toutes les pages
- [ ] Tests d'accessibilité (clavier, contraste)
- [ ] Sitemap XML pour les moteurs
- [ ] Robots.txt
- [ ] Analytics (optionnel : Plausible)

**Livrable :** Site complet et en production

---

## Après phase 3 : Optimisations et itération

### Phase 4+ (semaines 4+)

- **Génération de fiches** depuis le code Hydra
- **Lazy loading des images** en AVIF
- **Code splitting** des îlots
- **Caching stratégique** sur GitHub Pages
- **PWA** (offline reading)
- **Multilingue** (EN principal, ES/FR optionnels)

---

## Dépendances critiques

| Tâche | Dépend de | Statut |
|---|---|---|
| Semaine 1 | Repo GitHub, domaine, CI | À faire |
| `/migrate/*` | Semaine 1 | À faire |
| `/install` | `/migrate/*` | À faire (blocant) |
| Pages statiques | `/install` OK | À faire |
| Fiches de référence | Gabarit validé | À faire |
| Production | Tout + Lighthouse OK | À faire |

---

## Ressources à portée de main

| Fichier | Rôle |
|---|---|
| `ASTRO_SETUP.md` | Config complète, structure, scripts |
| `CHARTE_SITE.md` | 10 règles + checklist avant merge |
| `SITEMAP.md` | Arborescence complète |
| `CLAUDE_ASTRO_SITE.md` | Guide pour les développeurs |
| `MIGRATION_EXEMPLE.md` | Tutoriel pas-à-pas `/migrate/airflow` |
| `mockups/migrate-airflow.html` | Source pour la première page |

---

## Command-line quick-start

```bash
# Créer et initialiser
mkdir hydra-site && cd hydra-site
git init
git remote add origin https://github.com/[user]/hydra-site.git

# Copier les fichiers de configuration
# (Voir ASTRO_SETUP.md pour astro.config.mjs, package.json, etc.)

# Installer et dev
pnpm install
pnpm dev

# Build et preview (simule GitHub Pages)
pnpm build
pnpm preview

# Vérifier les liens
npx linkinator dist/

# Commit et push
git add .
git commit -m "initial: scaffold Astro site"
git push -u origin main
```

---

## Métriques de succès

À la fin de chaque semaine :

**Semaine 1**
- ✅ `/migrate/airflow` en ligne sur hydraetl.com
- ✅ Lighthouse budgets respectés
- ✅ Zéro appel réseau au load
- ✅ Clavier complet

**Semaine 2**
- ✅ Les 5 autres tunnels en ligne
- ✅ Noyau commun extracté (pas de duplication)
- ✅ 6 pages traducteurs testées

**Semaine 3**
- ✅ Site complet (12 pages + fiches)
- ✅ `/install` accueille tous les tunnels
- ✅ Accueil et navigation OK
- ✅ Tous les budgets respectés

---

## Support

- **Questions sur Astro ?** → `ASTRO_SETUP.md`
- **Questions sur la charte ?** → `CHARTE_SITE.md`
- **Comment adapter une maquette ?** → `MIGRATION_EXEMPLE.md`
- **Architecture générale ?** → `CLAUDE_ASTRO_SITE.md`

**Bloqué ?** Consulter ces docs dans cet ordre. 99 % des questions y sont répondues.

