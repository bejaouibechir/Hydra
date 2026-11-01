# Montée en volume — Hydra ETL vs dlt + dbt (DuckDB), 29/10/2026

Machine : environnement cloud de Claude, 2 processeurs, 8 Go. Même pipeline que le comparatif (commandes payées → jointure clients → CA par pays et par mois), variante sans protection, **sans Airflow** (moteurs seuls). Hydra ETL 0.14.0, avec et sans l'accélérateur `hydra-etl[native]` (lecteur Rust). Justesse vérifiée à chaque fois contre une référence DuckDB : **tous les résultats sont exacts**.

| Lignes | Hydra ETL | Hydra ETL + native | dlt + dbt (DuckDB) |
|---|---|---|---|
| 200 000 | **1,6 s** · 161 Mo | — | 10,7 s · 393 Mo |
| 1 M | 5,9 s · 360 Mo | **5,0 s** · 315 Mo | 12,1 s · 461 Mo |
| 2 M | 11,5 s · 616 Mo | — | **10,7 s** · 446 Mo |
| 3 M | 16,9 s · 882 Mo | — | **15,3 s** · 528 Mo |
| 5 M | 26,8 s · 1,4 Go | 21,0 s · 683 Mo | **19,8 s** · 553 Mo |
| 10 M | 65,0 s · 2,7 Go | 40,1 s · 1,3 Go | **28,3 s** · 686 Mo |
| 20 M | 112,8 s · 5,4 Go | 83,5 s · 2,3 Go | **46,2 s** · 789 Mo |

Durée de bout en bout · mémoire maximale de l'arbre de processus.

## Lecture

- **Seuil de bascule ≈ 2 millions de lignes** (≈ 5 M avec `native`). En dessous, Hydra ETL est plus rapide : jusqu'à 6 fois à 200 000 lignes, car dlt + dbt paient ≈ 9 s de démarrage fixe. Au-dessus, DuckDB (moteur en colonnes, multi-cœur) l'emporte : 2 à 2,4 fois plus rapide à 20 M.
- **Mémoire** : Hydra ETL croît avec le volume (≈ 270 Mo par million de lignes, ≈ 115 Mo avec `native`) car la jointure et l'agrégation chargent toutes les lignes en mémoire (pandas) ; dlt + dbt restent presque plats (< 0,8 Go). Limite estimée sur 8 Go : ≈ 25 M lignes (≈ 60 M avec `native`), non testée.
- **Où passe le temps chez Hydra ETL** (profil, 5 M lignes) : **lecture du CSV ≈ 70 %**, transformations ≈ 25 %.
- Avec Airflow (mesuré dans le comparatif : +5 à 10 s par run), le seuil monte un peu pour la pile dlt + dbt.

## Ce qu'on peut affirmer

- « Jusqu'à quelques millions de lignes par run — le cas le plus courant —, Hydra ETL est le plus rapide. Au-delà, un moteur en colonnes comme DuckDB prend l'avantage ; Hydra ETL reste exact mais plus lent et plus gourmand en mémoire. »
- Recommander `hydra-etl[native]` dès le million de lignes.

## Pour la feuille de route Hydra ETL

> **Point clé (Bechir, 29/10) :** dlt ne fait que charger, par lots, via le disque ; dbt ne calcule pas, il envoie du SQL au moteur (DuckDB). DuckDB travaille **en flux** : il ne garde en mémoire que la petite table d'une jointure (2 000 clients) et les totaux en cours d'une agrégation (8 pays, 9 mois), et déborde sur le disque si besoin. Hydra ETL (pandas) rassemble d'abord toutes les lignes. **Chemin d'amélioration : soit faire l'agrégation et la jointure en flux, lot par lot, en ne gardant que les totaux et la petite table ; soit confier ces opérations globales à DuckDB.**

> **Pourquoi la lecture CSV coûte 70 % du temps** (code de 0.14.0, `csv_connector.py`) : analyse ligne par ligne en Python pur (module `csv`), sur un seul cœur ; chaque valeur devient un objet chaîne Python (≈ 25 millions pour 5 M lignes), puis une colonne pandas de type objet, reconvertie ensuite en nombres par `cast` ; lots de 10 000 lignes (100 000 au plus) ; parité exacte avec l'ancien `csv.DictReader` exigée, ce qui écarte les lecteurs rapides. DuckDB lit en C++, sur plusieurs cœurs, directement en colonnes typées. **À vérifier :** dans 0.14.0, `_extract_frames_one` appelle toujours le lecteur Python : l'accélérateur Rust (`native`) ne semble pas utilisé pour `csv.read` sur ce chemin (le gain mesuré viendrait d'ailleurs).

1. **Lecture CSV** : 70 % du temps ; lecteur multi-cœur (Arrow / Rust) par défaut.
2. **Agrégations et jointures en flux ou en colonnes** : éviter de tout charger en mémoire.
3. **Option moteur DuckDB** pour les opérations globales (l'extra `hydra-etl[duckdb]` existe déjà) : garderait les garanties de Hydra ETL avec la vitesse d'un moteur en colonnes sur les gros volumes.

## Reproduire

`gen.py N dossier` (données), `run_scale.sh N…` (mesure + vérification), `measure.py`, `check.py` ; résultats bruts : `results.jsonl`.
