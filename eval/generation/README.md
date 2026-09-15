# Jeu d'évaluation — génération de manifestes

Ce jeu mesure une chose : **la capacité d'un modèle à produire des manifestes
Hydra valides à partir d'une demande en français**.

Il est **distinct** de `documentations/chatbot-hydra-dsl/evaluation/eval-dataset.json`,
qui évalue le *chatbot pédagogique* (niveaux d'assistance, explications
d'erreurs, affirmations interdites). Deux produits, deux mesures :

| Jeu | Produit évalué | Périmètre commercial |
|---|---|---|
| `evaluation/eval-dataset.json` (100 cas) | chatbot d'apprentissage du DSL | gratuit — marketing |
| `eval/generation/cases.json` (34 cas) | génération de pipelines | payant |

**Aucun des deux ne doit servir à entraîner un modèle.** Un jeu utilisé pour
l'entraînement cesse de mesurer quoi que ce soit.

## Composition

| Niveau | Cas | Ce qui est éprouvé |
|---|---:|---|
| `simple` | 8 | un manifeste minimal, zéro ou une opération |
| `intermediaire` | 7 | chaînes de 2 à 3 opérations, ordre imposé (`cast` avant toute comparaison numérique) |
| `compose` | 5 | deux sources, `join`, `union`, `pivot`, `unpivot` |
| `base_de_donnees` | 5 | PostgreSQL, MySQL, MongoDB, API web, modes de chargement, secrets |
| `workflow` | 4 | DAG, `depends_on`, fan-in, trigger cron, `retry`, actions |
| `adversarial` | 5 | le modèle doit **refuser** et expliquer, jamais inventer |

## Les cinq pièges adverses

Ils comptent autant que le reste : un modèle qui invente est plus dangereux
qu'un modèle qui échoue.

- `adv-050` — **conteneurs** : notion de Hydra Studio, absente du DSL.
- `adv-051` — **S3 / BigQuery** : connecteurs inexistants.
- `adv-052` — **action `teams`** : inexistante — et à l'exécution elle serait
  ignorée en silence, le step comptant comme réussi (anomalie A1).
- `adv-053` — **exécution distribuée** : hors du périmètre assumé de Hydra.
- `adv-054` — **opération `lowercase`** : n'existe pas, c'est `clean` avec
  `case: lower`. Le modèle doit rediriger.

## Les trois métriques

1. **Validité** — `hdrctl validate` passe sur le job généré. Binaire, automatique.
2. **Exactitude** — la structure attendue est présente : bons types de
   connecteurs, bonnes opérations, câblage `pipeline.from` / `pipeline.to`
   pointant vers des identifiants réellement déclarés.
3. **Sobriété** — aucune clé hors schéma, aucune opération hors des 18, aucune
   action hors des 11, aucun connecteur hors des 9, **aucun conteneur**.

La comparaison est **structurelle**, jamais textuelle : plusieurs YAML
différents peuvent être également corrects.

## Garde-fou

```bash
python eval/generation/check_cases.py
```

Vérifie que le jeu ne référence que des opérations, connecteurs et actions qui
existent réellement, en relisant les schémas générés par `tools/spec_export.py`.
À lancer en CI : un jeu d'évaluation faux fait échouer des réponses correctes.

## Suite

`eval/run_eval.py` (étape 4) rejouera ces cas contre Ollama et produira le
tableau de scores qui décidera de la suite : contrainte de schéma, boucle de
réparation, contexte ciblé, ou affinage.
