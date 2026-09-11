# Plan de construction — Documentation Hydra (Hydra Guide)

> Plan pas à pas pour construire la documentation interactive de Hydra, à héberger
> sur GitHub Pages. Fondé sur `documentations.md` (stratégie, Partie I) et sur les
> décisions techniques convergées (Partie II, §21–27).
>
> **Principe directeur (§27) : livraison incrémentale.** Le Guide statique d'abord,
> une tranche verticale exemplaire (`filter`) ensuite, puis l'interactivité fiche
> par fiche. Ne jamais engager toutes les fonctionnalités en même temps. Le succès
> se mesure à la **date de première publication utile**, pas à l'exhaustivité.

---

## Décisions figées (rappel)

| Sujet | Décision |
|-------|----------|
| Contrainte | « Sans installation » — exécution locale *ou* distante (pas de dogme navigateur) |
| Générateur | **Astro** (îlots) — à confirmer par le prototype `filter` |
| CI / build | **GitHub Actions** |
| Hébergement | **GitHub Pages** (Guide statique) ; infra d'exécution séparée |
| Exécution N1 | **TypeScript** (cas simples) + **DuckDB-WASM** (tabulaire) |
| Exécution N2/N3 | **Moteur Hydra distant** — reporté après première mise en ligne |
| Source de vérité | Propriétés dérivées des modèles **Pydantic** (`model_json_schema()`) ; éditorial à la main |

---

## Structure cible du dossier `documentations/`

```text
documentations/
├── PLAN_DE_CONSTRUCTION.md      # ce fichier
├── site/                        # projet Astro (le site à héberger)
│   ├── src/
│   │   ├── pages/               # routes (/guide/transforms/filter, …)
│   │   ├── components/          # îlots interactifs (éditeur YAML, diagramme, runner)
│   │   ├── content/             # content collections (fiches générées)
│   │   └── layouts/
│   ├── public/                  # données canoniques statiques (CSV/JSON/Parquet)
│   ├── astro.config.mjs
│   └── package.json
├── metadata/                    # métadonnées canoniques des composants (source des fiches)
│   ├── schema/                  # schéma JSON validable d'une fiche
│   ├── generated/               # propriétés générées depuis Pydantic (auto, ne pas éditer)
│   └── editorial/               # résumé, exemples, erreurs, relations (écrit à la main)
├── data/                        # jeu de données canonique (customers/orders/products)
├── scripts/                     # générateurs (Pydantic → JSON, build des fiches)
└── .github/workflows/           # (à terme) Actions : génération, test, déploiement
```

> Note : le `.github/workflows/` final vit à la racine du dépôt ; on prototype
> d'abord ici, on déplace ensuite.

---

## Phase 0 — Préparation (0,5 jour)

**Objectif** : cadre de travail prêt, décisions figées accessibles.

1. Créer le dossier `documentations/` et sa structure ci-dessus.
2. Copier ce plan + un lien vers `documentations.md` (la stratégie reste la source).
3. Choisir le nom de travail public : **« Hydra Guide — Explore, edit and run every Hydra DSL element »** (§4).
4. Fixer les conventions d'URL (§14) : `/guide/{catégorie}/{élément}`.

**Livrable** : dossier initialisé.
**Validation** : la structure existe, le plan est lisible.

---

## Phase 1 — Socle métadonnées (2–3 jours) — *bloquant, invisible*

**Objectif** : le format canonique d'une fiche, avec les propriétés générées depuis le moteur.

1. **Définir le schéma canonique** d'une fiche (`metadata/schema/component.schema.json`) :
   nom, catégorie, résumé, `properties` (types/défauts/contraintes), capacités,
   erreurs, relations, équivalents migration, statut (stable/bêta/déprécié).
2. **Générer les propriétés depuis Pydantic** (`scripts/gen_properties.py`) :
   - itérer `_OP_MODEL_MAP` (`internal/parser/transform.py`, 18 ops) ;
   - pour chaque op, appeler `model.model_json_schema()` → écrire dans `metadata/generated/` ;
   - idem pour sources (`ExtractConfig`…) et destinations (`LoadConfig`).
3. **Rédiger l'éditorial** de départ (`metadata/editorial/`) pour `filter` uniquement :
   résumé, 1–2 exemples, erreurs fréquentes, éléments liés.
4. **Valider** : chaque fiche = `generated/` + `editorial/` conforme au schéma.

**Livrable** : format canonique + propriétés auto-générées pour tous les transforms.
**Validation** : `filter.json` complet et valide contre le schéma.

---

## Phase 2 — Jeu de données canonique (0,5–1 jour)

**Objectif** : données pédagogiques communes (§11.1), cohérentes entre exemples.

1. Créer `customers` / `orders` / `products` (petit volume, déterministe).
2. Exporter en **CSV, JSON, Parquet, SQLite/DuckDB** dans `data/`.
3. Copier les formats légers (CSV/JSON) dans `site/public/` pour l'accès client.

**Livrable** : jeu de données multi-format.
**Validation** : les 3 tables se chargent en DuckDB-WASM sans erreur.

---

## Phase 3 — Scaffold Astro (1 jour)

**Objectif** : squelette du site, navigation, rendu statique d'une fiche (sans interactivité).

1. Initialiser le projet Astro dans `site/` (`npm create astro`).
2. Configurer `astro.config.mjs` pour GitHub Pages (base path, sortie statique).
3. Mettre en place les **content collections** lisant `metadata/`.
4. Créer le layout de fiche + rendu **HTML sémantique** (H1, définition, tableau de
   propriétés, YAML dans le DOM, légendes) — c'est la couche SEO du §14.
5. Générer la page `/guide/transforms/filter` en **statique**, sans îlot encore.

**Livrable** : fiche `filter` rendue en HTML statique indexable.
**Validation** : `npm run build` produit une page complète et lisible sans JS.

---

## Phase 4 — Vertical slice `filter` interactif (2–4 jours) — *le prototype décisif*

**Objectif** : une fiche `filter` de bout en bout, îlot playground compris (§25).

1. Composant **éditeur YAML** (îlot) avec coloration + validation basique.
2. Composant **runner TypeScript** : applique `filter` sur le jeu canonique en mémoire.
3. Composant **diagramme** synchronisé (Source → Filter → View).
4. Synchronisation bidirectionnelle : YAML ↔ formulaire ↔ diagramme ↔ résultat (§8).
5. Boutons **Exécuter / Réinitialiser / Ouvrir dans Playground**.
6. Exercice « casser puis réparer » minimal (colonne inexistante).

**Livrable** : fiche `filter` pleinement interactive.
**Validation** : parcours Observer → Modifier → Exécuter → Visualiser fonctionnel.

---

## Phase 5 — Mesure & décision de stack (0,5 jour) — *checkpoint*

**Objectif** : confirmer ou infirmer Astro sur données réelles (5 critères, §22).

Mesurer sur la fiche `filter` :

1. poids de chargement ;
2. temps avant première interaction ;
3. fidélité de la simulation ;
4. SEO effectivement rendu (HTML statique indexable) ;
5. facilité de génération des fiches.

**Livrable** : court rapport de mesure.
**Décision** : valider Astro, ou basculer sur le repli (Docusaurus) avant d'industrialiser.

---

## Phase 6 — Guide statique complet (3–5 jours)

**Objectif** : toutes les fiches publiées, générées depuis les métadonnées (§27.2 : livrer le Guide d'abord).

1. Générer une fiche par composant (transforms, sources, destinations) depuis `metadata/`.
2. Rédiger l'éditorial minimal de chaque fiche (résumé + 1 exemple).
3. Mettre en place la **navigation** (§6) : A–Z, groupes, recherche `Ctrl/⌘ K`.
4. Page catalogue filtrable (§7) + badges de capacité (§8).
5. **Les autres fiches restent statiques** (pas encore d'îlot) — c'est volontaire.

**Livrable** : Guide complet navigable, une seule fiche (`filter`) interactive.
**Validation** : toutes les URL du §14 répondent, contenu indexable.

---

## Phase 7 — CI/CD GitHub Actions + déploiement Pages (1 jour)

**Objectif** : automatiser génération, test et déploiement (§17, §22).

1. Action **build** : régénère les propriétés depuis Pydantic à chaque push moteur.
2. Action **test** : valide chaque exemple YAML contre le schéma réel Hydra (§17).
3. Action **deploy** : build Astro → publication GitHub Pages.
4. Vérifier sitemap, URL canoniques, données structurées (§14).

**Livrable** : pipeline automatisé, site en ligne.
**Validation** : un push déclenche build + test + déploiement sans intervention.

> **JALON — Première publication utile.** À la fin de la Phase 7, le Guide est en
> ligne. C'est le succès mesuré par le §27.

---

## Phase 8 — Enrichissement interactif incrémental (continu)

**Objectif** : ajouter l'îlot playground **fiche par fiche**, sans jamais bloquer le Guide.

1. Prioriser les éléments à fort trafic / forte valeur pédagogique (filter, select, join, aggregate…).
2. Réutiliser les composants de la Phase 4 (éditeur, runner, diagramme).
3. Basculer les exemples tabulaires (join, aggregate) sur **DuckDB-WASM**.
4. Ajouter les niveaux pédagogiques (§9) et les exercices (§12) progressivement.

**Livrable** : couverture interactive croissante.
**Validation** : chaque fiche enrichie passe le parcours interactif complet.

---

## Phases reportées (après première mise en ligne) — §27.2

Explicitement **non engagées** dans la première livraison :

- **Backend d'exécution éphémère** (niveaux 2/3, §16, §23) — bac à sable réaliste distant.
- **Laboratoires de bases de données** (§11) — sources/destinations SQL simulées.
- **Parcours de migration** (§13) — Airflow d'abord, puis Dagster/Prefect.
- **Couche `describe()` moteur** — remplacer progressivement l'éditorial manuel par des métadonnées exposées par le moteur (non intrusif, Règle 0).

---

## Récapitulatif du chemin critique

```text
P0 Préparation
   → P1 Métadonnées (bloquant)
      → P2 Données canoniques
         → P3 Scaffold Astro
            → P4 Vertical slice filter
               → P5 CHECKPOINT stack
                  → P6 Guide statique complet
                     → P7 CI/CD + JALON publication
                        → P8 Enrichissement incrémental (continu)
```

**Estimation première publication utile (P0→P7) : ~2 à 3 semaines**, une personne.
Les phases reportées viennent après, sans bloquer le jalon.
