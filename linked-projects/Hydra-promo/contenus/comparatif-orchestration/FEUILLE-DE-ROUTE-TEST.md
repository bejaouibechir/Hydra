# Feuille de route du test comparatif — Hydra ETL / Airflow + dlt + dbt / Airflow + Airbyte + dbt

Décidée avec Bechir le 28/10/2026. Objectif : mesurer dans les mêmes conditions, rédiger un compte rendu, puis décider de publier ou non un article.

> Correction de vocabulaire : dlt et Airbyte font le même travail (charger les données). Les trois piles comparées sont donc **Hydra ETL**, **Airflow + dlt + dbt** et **Airflow + Airbyte + dbt**.

## Principes

- **Une seule machine EC2 jetable**, les trois piles l'une après l'autre : même matériel pour tous.
- **Même chaîne, mêmes données, mêmes pannes** : `README.md` du dossier (200 000 commandes, 2 000 clients, 2 sorties, 4 scénarios).
- **Mesures identiques** pour chaque pile (voir « Mesures »), chaque scénario rejoué **3 fois** (on garde la médiane).
- **Un script par phase**, lancé par Bechir ; chaque script écrit ses résultats dans `results/<phase>/`. Bechir les récupère avant de passer à la phase suivante.
- Rien n'est publié avant la décision de l'étape 6.
- **Pas de Prometheus ni de Grafana** (décision de Bechir, 28/10) : ils fausseraient les mesures. Les graphiques seront produits après coup à partir des fichiers de résultats (CSV / JSON).

## Machine

| | Valeur |
|---|---|
| Type | m6i.xlarge (4 processeurs, 16 Go) — à défaut t3.xlarge |
| Système | Ubuntu Server 24.04 LTS, x86 |
| Disque | 60 Go gp3, « Delete on termination » coché |
| Région | eu-west-3 (Paris) |
| Accès | port 22 pour l'IP de Bechir seulement ; paire de clés créée pour ce test |
| Coût | ≈ 0,24 $/h, ≈ 1 $ pour l'ensemble |

## Mesures (identiques pour les 3 piles)

| Mesure | Comment |
|---|---|
| Durée d'installation | sans cache pip / images (chronomètre du script) |
| Paquets et taille | nombre de paquets Python, taille de l'environnement, images Docker |
| Mémoire et processeur | échantillonnés chaque seconde (installation et runs) dans `metrics.csv`, pour tracer les courbes ensuite |
| Durée d'un run | 4 scénarios × 3 fois, médiane |
| Comportement en panne | version de chaque sortie (`main`, `backup`, `previous`, `other`) et cohérence |
| Code écrit | fichiers et lignes utiles, variantes *simple* et *safe* |
| Étapes manuelles | commandes ou configurations nécessaires en dehors du script |

## Étapes

### Étape 0 — Préparation (Claude, puis Bechir)
- Claude : écrire les 3 scripts de phase + un script de collecte, les tester dans le cloud (sauf Airbyte).
- Bechir : publier Hydra ETL **0.14.0** (`on_failure`, `timeout`), sinon le test Hydra ne peut pas tourner avec `pip install hydra-etl`.
- Bechir : créer l'EC2, s'y connecter, y copier le dossier `comparatif-orchestration` (ou `git clone`).

### Étape 1 — Hydra ETL (≈ 15 min)
- `bash phase1_hydra.sh` : installation sans cache, variantes *simple* et *safe*, 4 scénarios × 3, mesures.
- Bechir récupère `results/phase1_hydra/` (copie dans le dossier partagé ou colle le résumé dans la conversation).

### Étape 2 — Airflow + dlt + dbt (≈ 30 min)
- `bash phase2_airflow_dlt_dbt.sh` : même déroulé.
- Bechir récupère `results/phase2_airflow_dlt_dbt/`.
- Le script supprime son environnement à la fin (place pour Airbyte).

### Étape 3 — Airflow + Airbyte + dbt (≈ 1 h 30)
- `bash phase3_airflow_airbyte_dbt.sh` : installation de Docker et d'Airbyte (`abctl`), connexions CSV → DuckDB créées par l'API d'Airbyte, même déroulé.
- Bechir récupère `results/phase3_airflow_airbyte_dbt/`.
- Si Airbyte ne s'installe pas : noter l'erreur et les ressources, ne pas insister au-delà de 2 essais.

### Étape 4 — Fin de la machine
- Terminer l'instance, vérifier qu'aucun disque ne reste, supprimer la paire de clés.

### Étape 5 — Compte rendu (Claude)
- Tableau comparatif des 3 piles, chiffres bruts en annexe, limites du test (machine unique, `airflow dags test`, taille des données).
- Ce qu'on peut affirmer et ce qu'on ne peut pas affirmer.

### Étape 6 — Décision (Bechir)
Publier si :
- les garanties de Hydra ETL sont confirmées (mêmes résultats en panne que les piles sûres, sans code impératif) ;
- l'écart d'installation et de complexité est net et reproductible ;
- aucun chiffre ne dépend d'un défaut de notre environnement.
Sinon : garder les résultats pour améliorer Hydra ETL, sans article.

## Livrables

- `results/phase1_hydra/`, `results/phase2_airflow_dlt_dbt/`, `results/phase3_airflow_airbyte_dbt/` : JSON + journaux.
- `COMPTE-RENDU.md` : comparatif final.
- Décision notée dans ce document.
