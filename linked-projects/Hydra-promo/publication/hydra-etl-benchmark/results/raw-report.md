# Compte rendu brut du banc

Machine : Ubuntu 24.04.5 LTS, 4 processeurs, 15.3 Go, Python 3.12.

## Installation

| Pile | Durée | Paquets Python | Taille env. | Mémoire max (phase) | Autres |
|---|---|---|---|---|---|
| Hydra ETL | 9.0 s | 15 | 189 Mo | 1036 Mo | — |
| Airflow + dlt + dbt | 36.0 s | 170 | 922 Mo | 1290 Mo | — |
| Airflow + Airbyte + dbt | 26.0 s | 162 | 531 Mo | 6372 Mo | docker_install_seconds: 13.0, abctl_install_seconds: 3.0, airbyte_install_seconds: 323.1, airbyte_low_resource_mode: True, first_sync_orders_main_seconds: 82.0, first_sync_customers_seconds: 66.0, airbyte_images: 26, airbyte_running_containers: 18, airbyte_images_mb: 7050, docker_df: Images 8.879GB; Containers 3.641MB; Local Volumes 7.622GB; Build Cache 0B |

## Code écrit (lignes utiles)

| Pile | Simple | Sûre |
|---|---|---|
| Hydra ETL | 76 lignes, 11 fichiers | 97 lignes, 12 fichiers |
| Airflow + dlt + dbt | 78 lignes, 10 fichiers | 104 lignes, 10 fichiers |
| Airflow + Airbyte + dbt | 107 lignes, 11 fichiers | 131 lignes, 11 fichiers |

## Pannes — variante simple

Sorties pays/mois, cohérence, médiane des durées.

| Scénario | Hydra ETL | Airflow + dlt + dbt | Airflow + Airbyte + dbt |
|---|---|---|---|
| normal | main/main ✓ (1.25 s) | main/main ✓ (14.13 s) | main/main ✓ (137.71 s) |
| missing_source | previous/previous ✓ (0.47 s) | previous/previous ✓ (9.88 s) | previous/previous ✓ (89.28 s) |
| bad_amount | previous/previous ✓ (0.7 s) | previous/previous ✓ (13.94 s) | previous/previous ✓ (54.67 s) |
| bad_date | main/previous ⚠ incohérent (1.12 s) | main/previous ⚠ incohérent (13.97 s) | previous/previous ✓ (51.26 s) |

## Pannes — variante sûre

Sorties pays/mois, cohérence, médiane des durées.

| Scénario | Hydra ETL | Airflow + dlt + dbt | Airflow + Airbyte + dbt |
|---|---|---|---|
| normal | main/main ✓ (1.3 s) | main/main ✓ (14.14 s) | main/main ✓ (86.17 s) |
| missing_source | backup/backup ✓ (1.24 s) | backup/backup ✓ (17.11 s) | backup/backup ✓ (171.81 s) |
| bad_amount | backup/backup ✓ (1.5 s) | backup/backup ✓ (23.45 s) | backup/backup ✓ (205.13 s) |
| bad_date | backup/backup ✓ (1.88 s) | backup/backup ✓ (23.49 s) | backup/backup ✓ (185.16 s) |

## Durée des étapes

| Étape | Statut | Durée |
|---|---|---|
| 0.1 | done | 0.0 s |
| 0.2 | done | 20.0 s |
| 0.3 | done | 11.0 s |
| 0.4 | done | 1.0 s |
| 1.1 | done | 13.2 s |
| 1.2 | done | 2.0 s |
| 1.3 | done | 12.0 s |
| 1.4 | done | 19.0 s |
| 2.1 | done | 40.3 s |
| 2.2 | done | 7.0 s |
| 2.3 | done | 2.0 s |
| 2.4 | done | 159.0 s |
| 2.5 | done | 239.0 s |
| 3.1 | done | 13.0 s |
| 3.2 | done | 4.0 s |
| 3.3 | done | 324.1 s |
| 3.4 | done | 17.0 s |
| 3.5 | done | 30.3 s |
| 3.6 | done | 51.0 s |
| 3.7 | done | 162.0 s |
| 3.8 | done | 8.0 s |
| 3.9 | done | 3.0 s |
| 3.10 | done | 335.1 s |
| 3.11 | done | 650.2 s |
| 3.12 | done | 4.0 s |
