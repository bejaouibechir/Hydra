# Feuille de route — comparatif Hydra ETL / Flowfile

Préparée le 29/10/2026, à valider par Bechir. Même méthode que le comparatif Airflow + dlt + dbt / Airbyte : mêmes données, mêmes pannes, mêmes mesures, une seule machine.

Objectif : **trouver les limites de chacun** (pannes, reprise, volume, mémoire) et décider de ce qu'on peut affirmer — ou de ce que Hydra ETL doit améliorer.

## Versions

| Outil | Version | Installation | Lancement d'un run |
|---|---|---|---|
| Hydra ETL | 0.16.0 | `pip install "hydra-etl[native,duckdb]"` | `hdrctl run .` |
| Flowfile | 0.23.3 | `pip install flowfile` | `flowfile run flow <flow>.yaml --backend local` |

Flowfile : flux construits avec son API Python (`flowfile_frame`) puis enregistrés en YAML (`save_graph`), contrôlés dans son éditeur. Même chaîne que le banc : commandes payées → jointure clients → CA par pays et par mois, sorties CSV.

## Principes

- **Une EC2 jetable** (m6i.xlarge, 4 processeurs, 16 Go, Ubuntu 24.04), les deux outils l'un après l'autre.
- Données, pannes, vérification : **réutiliser `shared/`** (`make_data.py`, `scenarios.py`) et `montee-en-volume/` (`gen.py`, `measure.py`, `check.py`).
- Chaque mesure **3 fois, médiane**. Pas de Prometheus ni Grafana.
- Un dossier par outil : `hydra/`, `hydra_simple/` (existants, passés en 0.16.0) et `flowfile/`, `flowfile_simple/` (à créer).
- Ne jamais tordre un outil : si une garantie n'existe pas dans Flowfile, on l'écrit en Python comme le ferait un utilisateur, et **on compte ce code**.

## Volet A — Pannes (scénarios existants)

`normal`, `missing_source`, `bad_amount`, `bad_date` ; variantes *simple* et *safe* (secours `backup` + sorties publiées en tout ou rien).

| | Hydra ETL 0.16.0 | Flowfile 0.23.3 |
|---|---|---|
| *simple* | workflow actuel | un flux, deux sorties |
| *safe* | `rollback`, `fallback` (`when`, `on_failure`), `timeout` (déclaratif) | aucun équivalent natif : script Python d'enrobage (essai → secours, écriture en fichiers temporaires puis `os.replace`) |

Attendu à vérifier : `bad_date` en *simple* → sorties incohérentes chez les deux.

## Volet B — Limites de résilience (nouveaux scénarios)

| Scénario | Ce qu'on provoque | Ce qu'on regarde |
|---|---|---|
| B1 Panne passagère | la source n'apparaît qu'après 20 s | retry espacé : Hydra `retry: {max, delay}` ; Flowfile : rien de natif (boucle à écrire) |
| B2 Étape non critique en échec | une notification (webhook) qui échoue après le calcul | Hydra `on_failure: continue` ; Flowfile : tout le run échoue ? |
| B3 Arrêt brutal | `kill -9` au milieu du chargement | état des sorties, puis comportement du run suivant (journal d'annulation Hydra) |
| B4 Délai dépassé | source lente (pipe nommé ou fichier qui grossit) | arrêt propre, sorties intactes |
| B5 Base de données | chargement PostgreSQL `replace`, panne au milieu (ligne invalide après 100 000 lignes) | table vide, partielle ou intacte ; Hydra tout ou rien vs Flowfile `if_exists=replace` |
| B6 Reprise | relance après correction de la panne | qui reprend tout, qui ne refait que ce qui manque |

B5 demande Docker + PostgreSQL sur l'EC2 (≈ 5 min de plus).

## Volet C — Montée en volume

200 000, 1 M, 2 M, 3 M, 5 M, 10 M, 20 M, puis **50 M** pour trouver la limite mémoire (16 Go).

| Variante | Détail |
|---|---|
| Hydra `pandas` | moteur de référence |
| Hydra `native` | lecteur Rust |
| Hydra `engine: auto` / `duckdb` | moteur gros volumes (0.16.0) |
| Flowfile `local` | `flowfile run flow`, mode performance |
| Polars pur | code exporté par Flowfile : montre le coût propre de Flowfile au-dessus de Polars |

Mesures : durée de bout en bout, mémoire maximale de l'arbre de processus, justesse (`check.py`), délai fixe de démarrage (run à 1 000 lignes).

## Volet D — Installation et empreinte

Durée sans cache, nombre de paquets, taille de l'environnement, mémoire au repos de l'interface (`hdrctl serve` vs `flowfile run ui`).

## Volet E — Ce qu'il faut écrire

- Lignes utiles, *simple* et *safe* (`shared/count_lines.py`).
- Flowfile : le YAML du flux est généré par l'éditeur → compter à part le **nombre de nœuds** et les **lignes Python** ajoutées pour la variante *safe*.

## Étapes

| # | Qui | Quoi |
|---|---|---|
| 0 | Claude | Flux Flowfile (*simple*, *safe*), scénarios B1–B6, `phase_flowfile` dans `run.py`, test dans le cloud (sauf B5) |
| 1 | Bechir | Valider cette feuille de route ; créer l'EC2 |
| 2 | Bechir | `python3 run.py` : phases Hydra 0.16.0 puis Flowfile (≈ 1 h) |
| 3 | Bechir | `run_scale.sh` avec les 5 variantes (≈ 1 h 30 avec 50 M) |
| 4 | Bechir | Récupérer `results/`, terminer l'EC2 |
| 5 | Claude | `COMPTE-RENDU-FLOWFILE.md` : tableaux, limites du test, ce qu'on peut / ne peut pas affirmer |
| 6 | Bechir | Décision : article, ou améliorations Hydra seulement |

## Biais à surveiller

- Polars est multi-cœur, pandas non : présenter les chiffres avec le nombre de processeurs.
- Flowfile est d'abord un outil visuel : le comparer aussi sur ce qu'il fait mieux (aperçu des données, export de code), pas seulement sur nos critères.
- Flux Flowfile écrits par nous : les faire relire dans son éditeur pour vérifier qu'ils sont « normaux ».
- Garder la même version de Flowfile pendant tout le test (sorties fréquentes).
