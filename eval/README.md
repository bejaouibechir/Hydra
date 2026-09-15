# Évaluation de la capacité IA de Hydra

## Ce que l'on mesure, et pourquoi

Générer du YAML Hydra n'est pas un problème d'apprentissage mais de
**génération sous contrainte vérifiée**. Deux atouts rendent l'entraînement
inutile dans un premier temps :

- les **schémas JSON** du DSL, générés depuis le code (`tools/spec_export.py`) ;
- **`hdrctl validate`**, un oracle déterministe.

Un modèle affiné donne une probabilité d'avoir raison. Schéma + oracle donnent
une certitude. On mesure donc **avant** de toucher au modèle.

## Les trois dossiers, et leur séparation

| Dossier | Rôle | Montré au modèle ? |
|---|---|---|
| `eval/corpus/` | exemples réels récoltés du dépôt | **oui** (few-shot, RAG) |
| `eval/generation/` | 34 cas de mesure | **jamais** |
| `eval/results/` | scores produits | — |

Un jeu d'évaluation montré au modèle cesse de mesurer quoi que ce soit.

## Marche à suivre

```bash
# 0. (une fois) regenerer la specification depuis le code
python tools/spec_export.py
python eval/corpus/harvest.py
python eval/generation/check_cases.py

# 1. LIGNE DE BASE — aucune optimisation, c'est le chiffre de reference
python eval/run_eval.py --model qwen3:1.7b
python eval/run_eval.py --model qwen3:4b

# 2. etape B — sortie JSON imposee
python eval/run_eval.py --model qwen3:1.7b --mode constrained

# 3. etape C — boucle generer -> valider -> reparer (3 tentatives max)
python eval/run_eval.py --model qwen3:1.7b --mode repair
```

Résultats dans `eval/results/<modele>_<mode>.md` et `.json`.

Options utiles : `--limit 5` (essai rapide), `--level simple`, `--examples 3`
(plus de few-shot), `--think` (laisse le raisonnement actif ; par défaut le
harnais ajoute `/nothink`), `--verbose` (détail des échecs), `--keep-raw`.

## Les trois scores

| Score | Définition | Comment il est établi |
|---|---|---|
| **Validité** | le job généré passe l'oracle | `hdrctl validate` en sous-processus |
| **Exactitude** | la structure demandée est là | comparaison **structurelle** : connecteurs, opérations, ordre, câblage `from`/`to` |
| **Sobriété** | rien d'inventé | aucune opération hors des 18, aucun connecteur hors des 9, aucune action hors des 11, aucun conteneur |

La comparaison n'est jamais textuelle : plusieurs YAML différents peuvent être
également corrects.

**Cas adverses** : la bonne réponse est un refus argumenté. Un modèle qui
invente y marque zéro, un modèle qui refuse marque un.

## Prérequis

- `ollama serve` en marche, les modèles téléchargés (`ollama list`)
- Hydra installé ou lancé depuis la racine du dépôt (le harnais appelle
  `python -m hydra_etl.cli.hdrctl`)
- PyYAML ; aucune autre dépendance

## Lire les résultats

L'important n'est pas le total mais **l'écart entre niveaux**. Un modèle fort
en `simple` et faible en `compose` a un problème de cohérence inter-fichiers
— c'est la faiblesse attendue d'un petit modèle, et c'est ce que la contrainte
de schéma corrige le mieux. Une sobriété basse est plus grave qu'une validité
basse : un modèle qui invente est plus dangereux qu'un modèle qui échoue.
