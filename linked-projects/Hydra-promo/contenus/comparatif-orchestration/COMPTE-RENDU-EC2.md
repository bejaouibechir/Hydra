# Compte rendu — banc EC2 du 28/10/2026

Machine : Ubuntu 24.04, 4 processeurs, 15,3 Go, Python 3.12. Hydra ETL 0.14.0, Airflow 3.3.2, dlt, dbt-duckdb / dbt-postgres, Airbyte (abctl, mode réduit).
Données brutes : `results/` (COMPTE-RENDU-BRUT.md, metrics.csv, JSON).

## 1. Installation et ressources

| | Hydra ETL | Airflow + dlt + dbt | Airflow + Airbyte + dbt |
|---|---|---|---|
| Installation | 9 s | 36 s | 26 s (Python) + 13 s (Docker) + **323 s (Airbyte)** |
| Paquets Python | 15 | 170 | 162 |
| Taille | 189 Mo | 922 Mo | 531 Mo + **≈ 8,9 Go d'images Docker** (26 images) + 7,6 Go de volumes |
| Mémoire en plus du système (≈ 0,65 Go) | **+0,4 Go** en pointe, 0 au repos | +0,6 Go en pointe, 0 au repos | **+3,7 Go au repos** (18 conteneurs permanents), +5,5 Go en pointe |
| Services à faire tourner | aucun | aucun pour `dags test` (planificateur en production) | Docker, Kubernetes (kind), Airbyte, PostgreSQL, serveur SFTP |

## 2. Code écrit

| | Simple | Sûre |
|---|---|---|
| Hydra ETL (YAML) | 76 lignes, 11 fichiers | 97 lignes, 12 fichiers |
| Airflow + dlt + dbt (Python, SQL, YAML) | 78 lignes, 10 fichiers | 104 lignes, 10 fichiers |
| Airflow + Airbyte + dbt (Python, SQL, YAML) | 107 lignes, 11 fichiers | 131 lignes, 11 fichiers |

Airbyte demande en plus la configuration des sources, de la destination et des connexions : 58 lignes d'appels d'API ici (ou des clics dans l'interface).

## 3. Pannes (médiane de 3 runs pour Hydra ETL et dlt, 1 run pour Airbyte)

Sorties pays/mois : jour (`main`), secours (`backup`), inchangé (`previous`).

| Scénario | Hydra ETL simple | Hydra ETL sûre | dlt simple | dlt sûre | Airbyte simple | Airbyte sûre |
|---|---|---|---|---|---|---|
| normal | jour ✓ 1,3 s | jour ✓ 1,3 s | jour ✓ 14 s | jour ✓ 14 s | jour ✓ 138 s | jour ✓ 86 s |
| source absente | inchangé ✓ 0,5 s | **secours ✓** 1,2 s | inchangé ✓ 10 s | **secours ✓** 17 s | inchangé ✓ 89 s | **secours ✓** 172 s |
| montant illisible | inchangé ✓ 0,7 s | **secours ✓** 1,5 s | inchangé ✓ 14 s | **secours ✓** 23 s | inchangé ✓ 55 s | **secours ✓** 205 s |
| date impossible | ⚠ **incohérent** 1,1 s | **secours ✓** 1,9 s | ⚠ **incohérent** 14 s | **secours ✓** 23 s | inchangé ✓ 51 s | **secours ✓** 185 s |

- Variantes sûres : les trois piles arrivent au même résultat dans les 4 scénarios.
- Variante simple Airbyte « date impossible » cohérente : non grâce à Airbyte, mais parce que l'export vers les CSV est une étape séparée qui ne tourne qu'après un dbt entièrement réussi ; dans la pile dlt, dbt écrit les CSV directement, modèle par modèle. C'est un choix de conception du DAG, pas une propriété de l'outil.
- Durée d'un run : Hydra ETL ≈ 1,5 s ; dlt + dbt 14 à 23 s ; Airbyte + dbt 51 à 205 s (chaque synchronisation Airbyte démarre des conteneurs : 60 à 80 s).

### Pièges rencontrés avec Airbyte (utiles pour l'article, à formuler prudemment)

1. La source « File » en mode web force `https://` : un fichier servi en `http` simple échoue (erreur SSL). Contournement : SFTP.
2. Après le premier calcul dbt, toutes les synchronisations échouaient. Cause la plus probable : les **vues** créées par dbt sur les tables brutes empêchent Airbyte de les remplacer (mode *full refresh overwrite*). Corrigé en rendant les modèles intermédiaires *ephemeral* et en vidant le schéma `analytics`.
3. Le message d'erreur d'Airbyte par l'API reste générique (« Something went wrong in the connector ») : il a fallu un script de diagnostic pour obtenir la vraie raison.

## 4. Ce qu'on peut affirmer

- **Garanties en panne** : identiques pour les trois piles dans leurs variantes sûres ; Hydra ETL les obtient en YAML déclaratif (+21 lignes), les deux autres en Python écrit à la main (+26 et +24 lignes).
- **Installation** : Hydra ETL 15 paquets / 189 Mo ; Airflow + dlt + dbt 170 paquets / 922 Mo ; Airflow + Airbyte + dbt 162 paquets / 531 Mo **plus** ≈ 9 Go d'images, 18 conteneurs et 3,7 Go de mémoire en permanence.
- **Durée d'un run** : environ 10 fois plus court qu'avec dlt + dbt, et 45 à 190 fois plus court qu'avec Airbyte + dbt selon le scénario (réserve : `airflow dags test` et machine unique).
- **Code** : comparable (76/97, 78/104, 107/131 lignes) ; ne pas écrire « moins de code ». Avec Airbyte, s'ajoute la configuration des connexions (58 lignes d'API ou des clics).
- **Simplicité d'exploitation** : Hydra ETL = un `pip install` ; Airbyte = Docker + Kubernetes + base PostgreSQL + serveur de fichiers, et trois pièges avant le premier run réussi.

## 5. Limites

Une seule machine (4 processeurs, 15 Go) ; 200 000 lignes ; 1 run par scénario pour Airbyte ; `airflow dags test` (pas de planificateur) ; Airbyte en mode réduit (`--low-resource-mode`). À rappeler dans tout article.

## 6. Messages validés pour l'article (Bechir, 29/10)

Variantes renommées pour le lecteur : *sans protection* (ex-« simple ») et *avec protections* (ex-« sûre »).

1. **Volume** : « Vous n'avez probablement pas un problème de big data. » (tendance documentée : Redset / VLDB 2024, BigQuery ; pas de pourcentage précis).
2. **Résilience** : « Les mêmes garanties, sans les programmer » — 4 pannes traversées par les trois piles ; Hydra ETL avec `rollback`, `fallback`, `timeout` (+21 lignes de YAML), les autres avec du Python écrit à la main. Ne pas écrire « meilleures garanties ».
3. **Vitesse** : « Sur 200 000 lignes, un run complet prend 1 à 2 s avec Hydra ETL, contre 14 à 23 s avec Airflow + dlt + dbt et 1 à 3 minutes avec Airflow + Airbyte + dbt » ; hors orchestrateur, environ 5 fois plus rapide que dlt + dbt. Toujours préciser : durées de bout en bout, une machine, `airflow dags test`.
4. **Légèreté** : 15 paquets et 189 Mo, contre 170 paquets / 922 Mo, ou ≈ 9 Go d'images et 3,7 Go de mémoire permanente avec Airbyte.

Message de synthèse : « Pour vos volumes réels, Hydra ETL offre les mêmes garanties, intégrées plutôt que programmées, et des runs jusqu'à 10 fois plus rapides qu'Airflow + dlt + dbt — avec un seul outil et une fraction des ressources. »
