# Index — Documentation du site Hydra

Tous les fichiers d'aide pour monter hydraetl.com. Lisez-les dans cet ordre.

---

## 1. Principes fondamentaux

### **CHARTE_SITE.md** (90 lignes)
Les 10 règles non négociables pour toute page. À lire en entier avant de coder.
- Montrer avant d'argumenter
- ≤ 250 mots de prose
- Jamais de silence (afficher les cas non supportés)
- Tout statique, zéro backend
- Budgets Lighthouse bloquants
- Et 5 autres…

**Quand ?** → Au démarrage du projet.

---

## 2. Architecture globale

### **SITEMAP.md** (140 lignes)
L'arborescence complète du site en 63 pages. Qui existe (✓), qui est gabarit (~), qui reste à concevoir (✗).

Montre aussi :
- Quelles 12 pages sont déjà maquettées
- Quelles 30 pages sont des fiches sur gabarit (duplication de contenu, pas conception)
- Quelles 21 pages restent à produire
- Trois décisions à trancher : versionnage, connecteurs, URLs

**Quand ?** → Avant de créer le repo Astro. Pour comprendre la taille réelle du travail.

---

## 3. Guide de setup technique

### **ASTRO_SETUP.md** (360 lignes)
Configuration complète du projet Astro, fichier par fichier.

Inclut :
- Arborescence complète (copier-coller)
- `astro.config.mjs` validé
- `package.json` avec dépendances exactes
- `.github/workflows/build.yml` pour CI/CD
- `public/.nojekyll` et `public/CNAME` critiques
- Scripts d'aide (lighthouse budgets, copy-mockups)
- Checklist du premier déploiement
- Commandes locales

**Quand ?** → En mains. À utiliser comme base pour créer le vrai projet.

---

## 4. Guide développeur Astro

### **CLAUDE_ASTRO_SITE.md** (240 lignes)
Instructions pour tout travail sur le site une fois le squelette créé.

Couvre :
- Stack : Astro + React + CSS natif
- Conventions de nommage (URLs, fichiers, variables CSS)
- Séparation pages statiques vs îlots interactifs
- Le noyau partagé des 6 traducteurs (HydraCore.jsx + hydra-core-lib.js)
- Budgets strictes et vérifications
- Workflow des tâches courantes
- Tests avant commit

**Quand ?** → À lire avant de toucher un fichier source (après la setup).

---

## 5. Tutoriel d'adaptation

### **MIGRATION_EXEMPLE.md** (290 lignes)
Pas-à-pas montrant comment une maquette HTML devient une page Astro opérationnelle.

Utilise `/migrate/airflow` comme cas d'école :
1. La maquette actuelle (structure, JavaScript)
2. Démêler les trois parties (interface, traitement, rendu)
3. Créer la page Astro
4. Créer le composant React
5. Créer les patterns Airflow
6. Styles CSS
7. Workflow d'import
8. Checklist de validation

**Quand ?** → Quand vous adaptez la première page (airflow). Le pattern vaut pour les 5 autres.

---

## 6. Feuille de route

### **PLAN_EXECUTION.md** (180 lignes)
Timeline réaliste pour les 3 prochaines semaines.

- **Semaine 1** : Infra GitHub, première page `/migrate/airflow` en production
- **Semaine 2** : Les 5 autres tunnels, noyau commun, tests
- **Semaine 3** : Pages statiques, fiches de référence, site complet

Inclut :
- Tâches quotidiennes par jour
- Dépendances entre tâches (blocants identifiés)
- Livrables mesurables par semaine
- Métriques de succès

**Quand ?** → Après ASTRO_SETUP. À imprimer ou garder ouvert.

---

## Fichiers de maquettes

### Mockups HTML (dans `documentations/mockups/`)

Tous les fichiers `.html` existants deviennent des pages Astro :

| Maquette | Route Astro | Pages Astro |
|---|---|---|
| migrate-airflow.html | /migrate/airflow | see MIGRATION_EXEMPLE.md |
| migrate-dagster.html | /migrate/dagster | same pattern |
| migrate-prefect.html | /migrate/prefect | same pattern |
| migrate-dbt.html | /migrate/dbt | same pattern |
| migrate-databricks.html | /migrate/databricks | same pattern |
| migrate-airbyte.html | /migrate/airbyte | same pattern |
| migrate.html | /migrate | portage direct |
| playground.html | /playground | portage direct |
| dsl-builder.html | /build | portage direct |
| guide.html | /guide | portage direct |
| learn.html | /learn | re-align charte, puis portage |
| fiche-filter.html | /reference/operations/filter | portage + duplication |
| workflow-view.html | (composant partagé) | import dans /migrate/* |

---

## Ordre de lecture recommandé

### Si c'est votre premier jour

1. **CHARTE_SITE.md** (10 min)
   → Comprendre les règles non négociables
   
2. **SITEMAP.md** (15 min)
   → Savoir ce qu'on construit
   
3. **PLAN_EXECUTION.md** (10 min)
   → Comprendre le timing et les étapes

4. **ASTRO_SETUP.md** (30 min)
   → Préparer la structure locale

### Une fois que le squelette est créé

5. **CLAUDE_ASTRO_SITE.md** (25 min)
   → Conventions et workflow courants

6. **MIGRATION_EXEMPLE.md** (45 min, hands-on)
   → Adapter la première maquette

### Pour toute question ultérieure

- Lexique CSS ? → CLAUDE_ASTRO_SITE.md « Variables CSS »
- Comment faire une fiche ? → CLAUDE_ASTRO_SITE.md « Ajouter une fiche de référence »
- Accès refusé au réseau ? → CHARTE_SITE.md « Jamais de silence »
- Lighthouse échoue ? → ASTRO_SETUP.md « Scripts d'aide » ou PLAN_EXECUTION.md « Métriques de succès »

---

## Fichiers connexes

Autres ressources dans le repo Hydra :

- `CLAUDE.md` — instructions globales pour tout le projet
- `documentations/` — ce dossier
- `mockups/` — maquettes HTML à adapter

---

## Résumé ultra-court

**Tu dois :**
1. Lire CHARTE_SITE.md (90 lignes, 15 min)
2. Copier ASTRO_SETUP.md complet dans un nouveau dossier
3. Créer le repo GitHub
4. Adapter migrate-airflow.html suivant MIGRATION_EXEMPLE.md
5. Valider avec PLAN_EXECUTION.md semaine 1
6. Déployer sur GitHub Pages

**C'est quoi le truc principal ?**
Pas de dépendances lourdes, pas de backend, pas d'API. Du HTML statique servi depuis GitHub Pages. Les six traducteurs partagent un noyau (hydra-core-lib.js) — **zéro duplication**.

**Quand ça marche ?**
Quand `/migrate/airflow` est en ligne, Lighthouse passe, clavier fonctionne, zéro appel réseau.

