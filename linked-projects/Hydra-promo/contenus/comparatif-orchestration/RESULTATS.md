# Comparatif Hydra ETL vs dlt + dbt + Airflow — résultats (28/10/2026)

Machine : environnement cloud Linux, 2 processeurs, 8 Go. Python 3.13.
Versions : Hydra ETL 0.13.0 publiée (installation) + version de développement
`afc172d` (runs : `on_failure` et `timeout` ne sont pas encore publiés) ;
Apache Airflow 3.3.2, dlt 1.31.0, dbt-core 1.12.6, dbt-duckdb 1.11.1, DuckDB 2.0.0.

Scénario, pannes et commandes : `README.md`. Résultats bruts : `results_*.json`.

## 1. Comportement face aux pannes

État de départ de chaque scénario : les sorties contiennent le run de
l'avant-veille (`previous`). Secours disponible : export de la veille (`backup`).

| Scénario | Hydra *simple* | Airflow *simple* | Hydra *safe* | Airflow *safe* |
|---|---|---|---|---|
| normal | main / main | main / main | main / main | main / main |
| source absente | previous / previous (échec) | previous / previous (échec) | **backup / backup** | **backup / backup** |
| montant illisible | previous / previous (échec) | previous / previous (échec) | **backup / backup** | **backup / backup** |
| date impossible (2e sortie) | ⚠ **main / previous** (incohérent) | ⚠ **main / previous** (incohérent) | **backup / backup** | **backup / backup** |

Lecture : pays / mois. Sans précaution, **les deux piles** laissent des
sorties incohérentes quand la 2e sortie échoue. Avec précautions, **les deux**
arrivent au même résultat.

## 2. Ce qu'il a fallu écrire

Lignes utiles (sans lignes vides, commentaires ni docstrings) — `shared/count_lines.py`.

| | Hydra ETL | dlt + dbt + Airflow |
|---|---|---|
| Version *simple* | 76 lignes, 11 fichiers | 75 lignes, 10 fichiers |
| Version *safe* | 97 lignes, 12 fichiers | 101 lignes, 10 fichiers |
| Ajout pour passer à *safe* | **+21 lignes de YAML déclaratif** : `rollback: true`, bloc `fallback` (`when`, `on_failure`), `timeout`, un workflow de secours | **+26 lignes de Python** : règles de déclenchement (`one_failed`, `one_success`), dossiers de travail, publication atomique écrite à la main |
| Langages | 1 (YAML) | 3 (Python, SQL, YAML) + notions Airflow (trigger rules, branches) |

À dire honnêtement : **le volume est le même**. La différence est ailleurs :

- côté Hydra ETL, les garanties sont **déclarées** et testées par le moteur
  (tout ou rien par job, annulation, bascule vérifiée avant le départ) ;
- côté Airflow, elles sont **programmées** par l'utilisateur. Ma première
  version du DAG *safe* avait une erreur de logique (le secours partait même
  après un succès) : il a fallu la corriger, ce qui illustre le risque ;
- la publication atomique écrite ici ne marche que pour des fichiers ; pour
  une base de données, il faudrait encore écrire l'échange de tables. Hydra
  ETL annule nativement en base (`replace`, `append` avec clé, `upsert`).
- Hydra ETL décide **avant** de lancer (source absente → secours directement) ;
  Airflow doit d'abord échouer, ce qui produit une tâche en échec et une alerte.

## 3. Installation (sans cache pip)

| | Hydra ETL | dlt + dbt + Airflow |
|---|---|---|
| Commande | `pip install hydra-etl` | Airflow avec fichier de contraintes, puis `dlt[duckdb]`, `dbt-duckdb`, `pandas`, `pyarrow` |
| Durée (2 mesures) | 27 s et 75 s | 333 s et 536 s |
| Paquets installés | 15 | 171 |
| Taille de l'environnement | 188 Mo | 923 Mo |
| Étapes en plus | aucune | `airflow db migrate`, variables `AIRFLOW_HOME`, profil dbt |

Les durées dépendent beaucoup du réseau : donner des ordres de grandeur.
Piège rencontré : sans le fichier de contraintes officiel, l'installation
d'Airflow + dlt + dbt n'avait pas fini après 10 minutes (résolution des versions).
Autre piège : dlt a refusé de recharger après un changement de format d'entrée
(paquet en attente dans son état local) ; il a fallu effacer cet état.

## 4. Durée d'un run

| Scénario | Hydra *safe* | Airflow *safe* (`airflow dags test`) |
|---|---|---|
| normal | 2,3 s | 19,3 s |
| source absente | 2,4 s | 24,5 s |
| montant illisible | 2,6 s | 30,1 s |
| date impossible | 3,8 s | 30,8 s |

Hors Airflow, chargement dlt + calcul dbt ≈ 10 s (6 s + 4 s). À présenter
avec prudence : `airflow dags test` ajoute le démarrage d'Airflow à chaque run ;
en production, le planificateur tourne en continu.

## 5. Airbyte

Non mesuré. Docker fonctionne dans mon environnement, mais aucun Kubernetes
ne peut y démarrer de conteneur (kind via `abctl`, puis k3s : le bac à sable
interdit `oom_score_adj`). C'est une limite de l'environnement, **pas un défaut
d'Airbyte** : à ne pas présenter comme tel. Pour le mesurer :
la phase 3 de `run.py` sur une EC2 jetable (voir `GUIDE-EC2.md`).
D'après la documentation d'Airbyte, l'installation locale demande Docker et
un cluster Kubernetes (créé par `abctl`).

## 6. Ce qu'on peut affirmer dans l'article

- Même chaîne, même résultat : les deux piles savent être sûres.
- Hydra ETL : un outil, un langage, des garanties déclarées (+21 lignes de
  YAML) ; installation ≈ 10 fois plus légère (15 paquets contre 171).
- Run ≈ 8 fois plus court ici, avec la réserve sur `airflow dags test`.
- Sans précaution, **les deux** piles peuvent laisser des sorties incohérentes :
  ce qui compte, c'est le prix des précautions.

À ne pas affirmer : « moins de code » (faux ici), « Airbyte ne marche pas ».

## 7. Avant publication

- Publier Hydra ETL 0.14.0 (`on_failure`, `timeout`) : le lecteur doit pouvoir
  rejouer avec `pip install hydra-etl`.
- Rejouer sur une machine du lecteur type (Windows et Linux) pour vérifier.
- Mesurer Airbyte sur EC2 si on veut le citer avec des chiffres.
