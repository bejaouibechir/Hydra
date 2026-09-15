# Corpus d'exemples réels

Récolté par `eval/corpus/harvest.py` depuis `test_scenarios/`, `examples/` et
`tests/fixtures/`. Ce sont des manifestes **exécutés en test**, donc réputés
corrects — le script le revérifie quand même avec les vrais parseurs du moteur,
parce qu'un corpus qui contient une erreur l'enseigne.

## Séparation à ne jamais franchir

| Fichier | Usage | Montré au modèle ? |
|---|---|---|
| `eval/corpus/corpus.jsonl` | few-shot, RAG, futur entraînement | **oui** |
| `eval/generation/cases.json` | mesure | **jamais** |
| `documentations/chatbot-hydra-dsl/evaluation/eval-dataset.json` | mesure (chatbot) | **jamais** |

## Contenu

- **72 entrées exploitables** (jobs et workflows valides)
- **11 exemples négatifs** `tests/fixtures/dsl_cases/ko_*` — invalides par
  construction, précieux pour apprendre à *expliquer* une erreur plutôt qu'à la
  produire
- **8 entrées invalides non voulues** (stubs vides du dépôt), listées dans
  `coverage.md` et exclues du few-shot

## `coverage.md`

Le fichier qui compte. Un `0` y désigne un élément du DSL qu'aucun exemple
n'illustre : c'est précisément là qu'un modèle inventera.

Trous connus à la première récolte :

- **Connecteurs** : `parquet`, `postgres`, `web_api` — aucun exemple
- **Actions** : `condition`, `email`, `ssh`, `webhook` — aucun exemple
- **Mode de chargement** : `upsert` — aucun exemple
- **Opérations rares** : `deduplicate`, `merge`, `trim`, `union` — un seul exemple

Écrire un exemple pour chaque trou coûte quelques minutes et vaut mieux que
n'importe quel réglage de modèle.

## L'oracle

`python -m hydra_etl.cli.hdrctl validate <dossier>` valide les quatre
manifestes **et** la résolution `pipeline.from` / `pipeline.to`. Les modèles
Pydantic seuls ne vérifient pas ce câblage : trois cas `ko_*` passent la
validation Pydantic et ne sont rattrapés que par la CLI. C'est donc la CLI, et
elle seule, qui sert d'oracle au harnais d'évaluation.
