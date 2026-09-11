# Demande de revue — Mock fiche `filter` (Hydra Guide)

> À transmettre à Codex. Le fichier à examiner :
> `documentations/mockups/fiche-filter.html` (mock HTML autonome, ~550 lignes).

## Contexte

Prototype fictif (site fictif) validant l'UX de la **fiche canonique** de la
documentation interactive Hydra, avant tout développement réel. C'est le gabarit
qui sera répliqué sur toutes les fiches du Guide.

Décisions déjà figées : Astro (îlots) + React/React Flow + GitHub Pages + GitHub
Actions ; commentaires prévus via GitHub Discussions (giscus) ; source de vérité
des propriétés = modèles Pydantic du moteur.

Le mock est volontairement statique et jetable : moteur non branché, données et
exécution fictives. Objectif = valider l'expérience, pas le code de production.

## Ce que contient la page

- Barre de nav (Playground · Learn · Guide · Migrate), recherche ⌘K, toggle clair/sombre.
- Sidebar de navigation par groupes (burger sur mobile).
- En-tête `filter` + badges de capacité (Stable, Batch, Streaming, SQL Pushdown).
- Board interactif : éditeur DSL ↔ diagramme ↔ données d'entrée ↔ résultat, avec
  bouton Run qui filtre réellement les données fictives + métriques.
- Bloc-hameçon « Coming from another tool? » (Airflow/Dagster/Prefect/dbt/Pandas)
  avec comparaison source → Hydra et CTA de migration. C'est l'axe d'acquisition principal.
- Propriétés (annotées « générées depuis FilterOp »), erreurs fréquentes, éléments liés.
- Section Discussion (simulant giscus / GitHub Discussions).

## Questions précises pour la revue

1. **UX / hiérarchie visuelle** : l'ordre des blocs est-il optimal ? Le hook migration
   est-il au bon endroit (sous le board), ou devrait-il être encore plus haut ?
2. **Efficacité du hook migration** : capte-t-il vraiment l'intention ? Manque-t-il
   quelque chose pour convertir un utilisateur venant d'Airflow ?
3. **Accessibilité** : contrastes (clair ET sombre), navigation clavier, focus visibles,
   ARIA, sémantique HTML. Points bloquants ?
4. **Responsive** : les breakpoints (960 / 720 / 480) couvrent-ils les cas réels ?
   Problèmes sur mobile/tablette ?
5. **Fidélité au futur stack** : ce mock se transpose-t-il proprement en composants
   Astro + React, ou certains choix vont poser problème à la reprise ?
6. **Ce qui manque** pour une fiche canonique complète (cf. §8 de la stratégie) :
   schéma YAML interactif, versions de compatibilité, « casser puis réparer », etc.
7. **Risques SEO** (§14) : le contenu essentiel reste-t-il indexable une fois passé
   en îlots hydratés ? Recommandations.
8. **Note globale /20** et les 3 corrections prioritaires.
