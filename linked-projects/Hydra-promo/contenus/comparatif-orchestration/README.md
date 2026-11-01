# Comparatif : Hydra ETL vs dlt + dbt + Airflow

Même chaîne, mêmes données, mêmes pannes. Tout tourne en local, sans serveur
ni base de données (CSV en entrée, CSV en sortie ; DuckDB côté dbt).

**Chaîne** : commandes (200 000 lignes) + clients (2 000) → commandes payées →
chiffre d'affaires par pays (jointure) et par mois. Deux sorties :
`output/revenue_by_country.csv`, `output/revenue_by_month.csv`.

**Pannes rejouées** (`shared/scenarios.py`) — avant chaque run, les sorties
contiennent le run de l'avant-veille (« previous ») :

| Scénario | Panne |
|---|---|
| normal | aucune |
| missing_source | `data/orders.csv` absent |
| bad_amount | un montant illisible (`abc`) : la 1re sortie échoue |
| bad_date | une date impossible (`2026-13-45`) : seule la 2e sortie échoue |

Une source de secours existe : `data/backup/orders.csv` (export de la veille,
199 000 lignes). Le script dit, pour chaque sortie, de quelle version elle
vient : `main` (jour), `backup` (veille), `previous` (avant-veille) ou `other`.

## Lancer

Sur une machine Ubuntu 24.04 (EC2 conseillée) : **`python3 run.py`**. Le programme
enchaîne les phases avec confirmations, barres de progression et points de
reprise. Mode d'emploi complet : `GUIDE-EC2.md`.

| Phase | Pile |
|---|---|
| 0 | préparation (paquets, données) |
| 1 | Hydra ETL (`hydra/`, `hydra_simple/`) |
| 2 | Airflow + dlt + dbt (`modern/`, DuckDB) |
| 3 | Airflow + Airbyte + dbt (`airbyte/`, PostgreSQL) |
| 4 | compte rendu brut (`results/COMPTE-RENDU-BRUT.md`) |

Variantes : *simple* = ce qu'on écrit d'habitude ; *safe* = secours si la
source manque ou si le calcul échoue, et sorties publiées en tout ou rien.
