# Étape 7 — Moteur local et déterministe

## Résultat

Le moteur de réponse Hydra DSL est implémenté dans `hydra-site-template/src/lib/chatbot/`.
Il fonctionne entièrement dans le navigateur, sans LLM, backend, clé API ou requête réseau.
La connexion à l'interface visuelle existante de Playground est volontairement réservée à l'étape 8.

## Composants

- `normalize.ts` normalise les questions et extrait les termes significatifs.
- `knowledge.ts` charge les 40 exemples validés et décrit les 10 notions MVP.
- `search.ts` classe les exemples selon le contexte de leçon, l'opération sélectionnée,
  la question, les erreurs de validation et le DSL courant.
- `policies.ts` traite en priorité les secrets, les tentatives de détournement,
  les actions externes et les questions manifestement hors périmètre.
- `engine.ts` produit un `ChatResponse` conforme au contrat de l'étape 6.

## Ordre de décision

1. Validation du `ChatRequest`.
2. Détection de secrets potentiels.
3. Refus des tentatives de modification des instructions.
4. Refus des actions externes impossibles depuis un site statique.
5. Signalement des fonctions Hydra connues mais incompatibles ou absentes.
6. Détection de la notion, recherche pondérée et choix des exemples.
7. Réponse adaptée au niveau `hint_1`, `hint_2`, `explanation` ou `solution`.
8. Ajout des citations, actions proposées, score de confiance et notice d'exécution locale.

## Corpus embarqué

Le fichier source reste :

`documentations/chatbot-hydra-dsl/examples/examples.json`

Sa copie destinée au bundle Astro est :

`hydra-site-template/src/data/hydra-dsl/examples.json`

Les deux fichiers doivent rester identiques. Les chemins des guides et des actions sont relatifs
afin de rester compatibles avec GitHub Pages.

## Limites volontaires du MVP

- Le moteur ne reformule pas librement : il assemble des réponses anglaises validées.
- Il ne lance pas réellement un pipeline et ne modifie aucun fichier.
- Une question sans correspondance produit `no_match` au lieu d'une invention.
- L'interface Playground demeure simulée jusqu'à l'étape 8.

## Vérifications

Les tests isolés couvrent la recherche contextuelle, les quatre niveaux d'aide,
les secrets, le détournement d'instructions, les limitations de version,
les opérations inconnues, le hors périmètre, les actions externes et l'absence de correspondance.
