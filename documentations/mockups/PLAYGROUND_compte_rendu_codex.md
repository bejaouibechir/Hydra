# Compte rendu — Mock du Playground (Hydra Guide)

> À transmettre à Codex. Fichier concerné :
> `documentations/mockups/playground.html` (mock HTML autonome, ~590 lignes, à ouvrir dans un navigateur).

## Nature

Prototype fictif et jetable validant l'**UX du Playground** avant tout développement réel.
Moteur non branché : données, exécution, CLI et API sont **simulées** en JavaScript.
Même langage visuel que la fiche `filter` (accent teal, toggle clair/sombre, responsive).

Décisions déjà figées : Astro (îlots) + React/React Flow + GitHub Pages + Actions ;
propriétés de fiches générées depuis les modèles Pydantic ; on ne réimplémente pas
le DSL en JS (simulation légère seulement).

## Anatomie de l'écran

Structure alignée sur l'anatomie d'un job Hydra, gauche → droite :

- **Sources** (gauche) : catalogue diversifié — Files (csv/json/parquet), Databases
  (postgres/mysql/mongo), APIs (web-api). Survol = tooltip ; double-clic = modale avec
  les données de la source. Aperçu d'entrée sous le catalogue.
- **Fichiers du job** (centre, grille 2×2) : `sources.yml`, `transformations.yml`,
  `pipeline.yml` (manifeste : version/name/from/to/transformations), `destinations.yml`.
  Seul `transformations.yml` est **éditable** ; les trois autres sont **figés** (lecture
  seule, badge « locked ») et pilotés par la source/l'exemple choisi.
- **Destinations** (droite) : carte qui s'adapte en direct à `destinations.yml`, plus
  deux menus guidés **type × mode** filtrés par les capacités du connecteur (§11.4) —
  les modes non supportés (ex. CSV + upsert) apparaissent barrés. Aperçu de sortie zébré.
- **Bas** : onglets **CLI / API / Studio** réellement interactifs (terminal qui répond +
  autocomplétion ; console API avec endpoints ; Studio = placeholder assumé).

## Interactions implémentées

- Liste déroulante d'**exemples** : 5–10 cas **par source** ; se filtre sur la source active.
- Boucle de jeu : on édite `transformations.yml` → **Run** (bouton dans l'en-tête du volet,
  en haut à droite) → Destinations + CLI + API se mettent à jour ensemble.
- **IntelliSense** : validation en direct (chip ✓/⚠/✗), garde-fous — colonne inconnue,
  opérateur `< >` sur colonne texte signalé, ajout d'étape contrôlé (`＋ step`).
- Jeux de données de 12–14 lignes par source pour manipuler confortablement.
- Blocs **repliables** (collapse/expand) : « Pipeline builder » et « Run output ».

## Ce qui reste stub (volontaire)

Vrai moteur, vrais connecteurs, Share/Export, simulateur Studio (conçu plus tard),
backend d'exécution niveaux 2/3.

## Questions pour Codex

1. L'anatomie (Sources · fichiers · Destinations · CLI/API/Studio) est-elle la bonne
   métaphore pour un Playground, ou trop proche d'un IDE ?
2. Figer 3 fichiers sur 4 (seul `transformations.yml` éditable) : bon compromis
   pédagogique, ou trop restrictif ?
3. Le trio CLI / API / Studio en bas transmet-il bien l'idée « un job, exécuté partout » (§15) ?
4. Le garde-fou capacités type × mode (§11.4) est-il assez lisible (modes barrés) ?
5. Manque-t-il une interaction clé pour juger l'UX (diagramme de pipeline visuel absent
   pour l'instant — le réintroduire ?) ?
6. Transposition vers Astro + React : des choix du mock qui poseront problème à la reprise ?
7. Note globale /20 + 3 priorités.
