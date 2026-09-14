# Compte rendu — Stratégie de construction de la documentation Hydra

> Document destiné à interroger Codex (ou tout autre agent) sur les choix
> d'architecture de la doc Hydra. Résume la discussion, les décisions prises,
> leur justification, et les questions encore ouvertes.

---

## 1. Point de départ

Analyse de `documentations.md` (stratégie de doc interactive Hydra). La contrainte
centrale identifiée, celle qui détermine toute l'architecture technique :

> **Exécuter du Hydra DSL dans le navigateur, sans installation, de façon
> déterministe et sécurisée.** Tout le reste (fiches type dax.guide, migration
> Airflow, SEO) repose sur ce socle.

Second prérequis souvent sous-estimé (§17 du document) : les fiches du Guide
doivent être **générées depuis la source de vérité** (schémas réels du DSL,
registre des composants, métadonnées de capacité), pas écrites à la main.

---

## 2. Décisions prises pendant la discussion

| # | Sujet | Décision | Justification courte |
|---|-------|----------|----------------------|
| D1 | Voie d'exécution du playground | **Hybride** | Fidèle au §11.5 (3 niveaux d'exécution). Niveau 1 = client-side ; niveaux 2/3 = backend éphémère externe. |
| D2 | Hébergement | **GitHub Pages** (esprit Kubernetes) | GitHub-native, Actions, contribution par PR, gratuit, versionné. |
| D3 | Générateur de site | **Astro** (îlots interactifs) | Seul candidat qui concilie « interactif-first » (§3) ET « SEO sans JS lourd » (§14) sans bricolage. |
| D4 | Stratégie métadonnées | **Pragmatique (« B »)** | Fiches écrites à la main d'abord dans un format structuré conçu pour matcher ce que le moteur exposera → bascule ultérieure = simple changement de source. |

### Stack cible retenu

- **Astro** — génère le site statique (fiches = HTML sémantique + îlots interactifs).
- **React ou Svelte dans les îlots** — éditeur YAML, diagramme synchronisé, simulation. Un composant réutilisé partout.
- **GitHub Actions** — à chaque push : génère les fiches depuis les métadonnées, teste les exemples YAML contre le schéma Hydra, déploie.
- **GitHub Pages** — héberge la doc statique.
- **Backend d'exécution externe (plus tard, optionnel)** — pour les niveaux 2/3, découplé du site.

---

## 3. Conséquences de GitHub Pages (statique) sur l'hybride

1. **Niveau 1 = 100% client-side** (simulation JS ou WASM). C'est ce que Pages sait servir → confirme l'hybride.
2. **Backend éphémère (niveaux 2/3) hors Pages** : vit ailleurs (Fly.io, conteneur, Function), appelé via API. Hébergement doc et infra d'exécution découplés.
3. **GitHub Actions = moteur du §17** : régénération + test automatique des exemples + déploiement à chaque push. Transforme la stratégie « B » en pipeline solide.

---

## 4. Pourquoi Astro plutôt que les alternatives

- **Hugo (stack Kubernetes)** : excellent pour du texte statique, mais pas de notion de composant interactif → il faudrait bricoler du JS à la main sur chaque fiche. La doc k8s est textuelle ; la nôtre est interactive-first (§3). Écarté.
- **Docusaurus / Next.js** : savent faire l'interactif (React), mais envoient un runtime React sur toute la page → plus de JS, SEO à surveiller, pages plus lourdes (Core Web Vitals §14). Docusaurus = bon second choix si besoin de versionning de doc intégré ; Next = surdimensionné.
- **Astro** : îlots = HTML statique sémantique par défaut (indexable §14) + JS uniquement sur les blocs interactifs, à la demande. « Content collections » lit des JSON/YAML au build → génère chaque fiche automatiquement depuis les métadonnées (aligné §17). Bémol honnête : communauté plus petite, suppose un minimum de confort front (coût inhérent à tout choix interactif-first).

---

## 5. État réel du codebase Hydra (vis-à-vis du §17)

**Fondations présentes :**
- `internal/connector/registry.py` — registry factory extensible → énumération auto des connecteurs possible.
- `ConnectorCapabilities` (dans `interface.py`) — flags déclaratifs (`supports_transactions`, `supports_upsert`, `supports_incremental`) → embryon des badges de capacité (§8, §11.4).
- Interface `Connector` stable (`extract_batches`, `load_batches`, `test_connection`).

**Ce qui manque pour générer les fiches automatiquement :**
- Pas de `description` / `summary` / `category` exposés par composant.
- Pas de schéma de propriétés exposé (types, défauts, requis/optionnel) — ni connecteurs, ni transformations.
- Pas de catalogue d'erreurs normalisé, ni relations/alternatives, ni équivalents migration.
- Pas de registry symétrique pour les **transformations** (filter, join, aggregate…) → rien à énumérer côté transforms.

**Conclusion :** métadonnées présentes **partiellement, côté connecteurs seulement**, insuffisantes pour la génération auto. → justifie la stratégie D4.

---

## 6. Séquencement proposé (non tranché)

- **Étape 0 (bloquante, invisible)** : définir le jeu de données canonique (§11.1) + concevoir le format de métadonnées d'un composant.
- **Étape 1** : vertical slice — une fiche `filter` de bout en bout (fiche + playground en simulation JS) pour valider l'archi Astro + îlots.
- **Étape 2** : industrialiser — générer les autres fiches depuis les métadonnées via Actions ; brancher progressivement le moteur comme source réelle.

---

## 7. Questions ouvertes à poser à Codex

1. **Simulation JS vs WASM pour le niveau 1** : réimplémenter une version légère du DSL (filter/select/join/aggregate) en TypeScript, ou faire tourner le vrai moteur Python/DuckDB via Pyodide / DuckDB-WASM ? Compromis fidélité (§17) vs poids de chargement vs effort.
2. **Astro : confirmer** que c'est le meilleur choix pour interactif-first + SEO sémantique + génération depuis données, ou existe-t-il un meilleur candidat pour ce triplet ?
3. **Format des métadonnées (§17)** : à quoi doit ressembler le JSON/YAML canonique d'un composant (nom, catégorie, résumé, schéma de propriétés, capacités, erreurs, relations, équivalents migration, statut) pour être à la fois générable par le moteur et consommable par Astro ?
4. **Couche `describe()` dans le moteur** : quelle est la façon la moins intrusive d'ajouter aux connecteurs ET aux transformations une méthode/métadonnée qui expose ces infos, sans casser l'archi existante (§ Règle 0 du CLAUDE.md) ?
5. **Registry des transformations** : faut-il créer un registry symétrique à celui des connecteurs pour énumérer les transforms, et comment ?
6. **Backend éphémère (niveaux 2/3)** : quelle infra minimale et sûre (§16) pour exécuter du vrai Hydra en sandbox jetable, appelée depuis un site statique ?
7. **Par où démarrer concrètement** : vertical slice (`filter`) d'abord, ou format des métadonnées d'abord ?

---

## 8. Critères d'acceptation (rappel du §20, à ne pas perdre de vue)

Le vrai indicateur n'est pas le nombre de pages lues mais le nombre
d'interactions réussies. La solution est non conforme si elle devient un site de
longs tutoriels, une référence statique avec quelques boutons « Run », un
playground isolé de la doc, ou une copie de dax.guide sans exécution.
