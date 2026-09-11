# Étape 8 — Intégration du chatbot dans Playground

## Résultat

Le mockup visuel de Playground a été promu en page Astro réelle :

`hydra-site-template/src/pages/playground.astro`

Le fichier standalone utilisé pour les revues de mockup est également connecté au même moteur :

`documentations/mockups/playground.html`

Il charge le bundle autonome `documentations/mockups/assets/hydra-chatbot-engine.js`, généré depuis
le moteur TypeScript partagé avec `npm run build:mockup-chatbot`.

Son chatbot n'utilise plus les réponses simulées. Il appelle le moteur local déterministe
de l'étape 7, sans backend, LLM, clé API ou requête réseau à l'exécution.

## Contexte transmis au moteur

- transformation actuellement sélectionnée ;
- contenu des quatre fichiers YAML du Playground ;
- source et lignes d'entrée sélectionnées ;
- dernier résultat simulé ;
- erreur de validation affichée par l'éditeur ;
- détection locale de secrets potentiels.

## Interactions disponibles

- choix entre premier indice, explication et solution ;
- passage du premier au second indice puis à la solution ;
- chargement d'un exemple compatible dans les éditeurs YAML ;
- ouverture du guide ou de la leçon citée ;
- affichage du score de correspondance, du niveau d'aide et de la décision de périmètre ;
- états d'attente, d'erreur, d'absence de correspondance et d'avertissement de secret.

## Fallback vers le contenu du site

Lorsqu'aucune réponse directe validée n'est disponible, le moteur extrait les mots-clés et classe
un index local des pages Guide, DSL, tutoriel et Migrate. Il affiche jusqu'à trois ressources
cliquables avec la mention explicite qu'il s'agit de suggestions. Si aucun contenu n'atteint le
seuil minimal, il demande à l'utilisateur de choisir entre jobs et pipelines, sources,
transformations, destinations, workflows ou migration.

La correspondance utilise uniquement des mots complets et des expressions normalisées afin
d'éviter les faux positifs par sous-chaîne. Aucun appel réseau ou LLM n'est nécessaire.

## Accessibilité et responsive

- fenêtre déclarée comme dialogue et messages annoncés avec `aria-live` ;
- focus placé dans la question à l'ouverture et rendu au lanceur à la fermeture ;
- envoi au clavier avec Entrée ;
- niveau d'aide associé à son libellé ;
- mise en page mobile conservée depuis le mockup.

## Vérifications

- build Astro statique réussi ;
- 15 tests unitaires du moteur réussis ;
- tests Playwright du parcours indice → second indice → solution ;
- test de prise en compte d'une erreur de colonne dans l'éditeur ;
- test d'avertissement en présence d'un secret ;
- test clavier sur une fenêtre mobile ;
- test direct du mockup standalone avec la question de compatibilité `derive` ;
- toutes les requêtes observées restent sur l'origine locale du site ;
- bundle du moteur et du corpus : environ 40,99 kB, soit 11,22 kB gzip.

## Limites conservées

Les sources, l'exécution, la CLI, l'API et les commentaires de Playground restent simulés.
Seul le chatbot Hydra DSL est maintenant fonctionnel. L'évaluation complète sur les 100 scénarios
préparés reste l'étape 9.
