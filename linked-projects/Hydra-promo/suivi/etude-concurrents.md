# Étude des concurrents — Hydra ETL

Relevé du 21/10/2026, API GitHub interrogée depuis le PC (sans jeton). Les chiffres sont vérifiés, aucun n'est estimé.

## 1. Activité des dépôts

| Outil | Dépôt | ★ | Forks | Contrib. | Langage | Licence | Dernière release | Issues+PR ouvertes |
|---|---|---|---|---|---|---|---|---|
| **Hydra ETL** | bejaouibechir/Hydra | 4 | 1 | 5 | Python | AGPL-3.0 | v0.11.2 (26/09/2026) | 7 |
| Sling | slingdata-io/sling-cli | 917 | 87 | 34 | Go | GPL-3.0 | v1.6.5 (08/10/2026) | 24 |
| Embulk | embulk/embulk | 1 785 | 208 | 57 | Java | Apache-2.0 | v0.11.5 (17/09/2024) ⚠️ | 167 |
| Meltano | meltano/meltano | 2 666 | 274 | 207 | Python | MIT | v4.4.1 (07/10/2026) | 146 |
| PipelineWise | transferwise/pipelinewise | 661 | 140 | 53 | Python | Apache-2.0 | 0.96.3 (14/10/2026) | 88 |
| dlt | dlt-hub/dlt | 5 996 | 631 | 225 | Python | Apache-2.0 | 1.31.0 (07/10/2026) | 465 |
| Kestra | kestra-io/kestra | 29 934 | 3 447 | 768 | Java | Apache-2.0 | v2.0.7 (20/10/2026) | 911 |
| Mage | mage-ai/mage-ai | 8 835 | 992 | 164 | Python | Apache-2.0 | 0.9.80 (09/10/2026) | 636 |
| Redpanda Connect | redpanda-data/connect | 8 790 | 978 | 374 | Go | (mixte) | v4.114.0 (16/10/2026) | 365 |
| Airbyte | airbytehq/airbyte | 22 251 | 5 413 | 1 256 | Python/Java | ELv2+MIT | v2.0.0 (15/10/2025) | 2 668 |
| Apache Hop | apache/hop | 1 506 | 484 | 157 | Java | Apache-2.0 | 2.19.0-rc1 (12/08/2026) | 333 |
| Luigi | spotify/luigi | 18 785 | 2 474 | 642 | Python | Apache-2.0 | v3.8.1 (07/05/2026) | 192 |
| Airflow | apache/airflow | 47 244 | 18 113 | 4 734 | Python | Apache-2.0 | 3.3.2 (17/09/2026) | 1 909 |

**Hypothèses corrigées :** Meltano et PipelineWise sont **actifs** (releases en octobre 2026). Le seul vrai signe de stagnation est Embulk (aucune release depuis plus de 2 ans).

## 2. Positionnement : qui Hydra ETL peut remplacer

| Cible | Recoupement | Verdict |
|---|---|---|
| **Sling** | CLI + YAML, fichiers ↔ bases | Concurrent n°1. Petite communauté (peu de 👍 dans les issues). Hydra ETL se distingue par les transformations, les DAG, Studio, la validation et Python |
| **Airbyte** (petits besoins) | CSV/DB → DB | Meilleur gisement de « trop lourd » : installation et mémoire (voir § 3) |
| **Embulk** | Chargement en masse en YAML | Stagnant : ses utilisateurs vont chercher une alternative |
| **Kestra** | YAML déclaratif | Énorme communauté. Angle Hydra ETL : sans serveur, `pip install` |
| **Meltano / PipelineWise** | YAML + Singer | Actifs. Angle Hydra ETL : pas d'écosystème Singer à maîtriser |
| **dlt** | ETL Python léger | Demandes orientées entrepôt (BigQuery, partitions). Angle Hydra ETL : déclaratif plutôt que code |
| Mage, Luigi, Hop, Airflow | Partiel | Écoute seulement, pas de cible prioritaire |

## 3. Signaux relevés dans les issues (depuis le 01/06/2024)

### Lourdeur / installation (Airbyte surtout)
- airbyte#56386 « abctl install stuck on nginx » — 7 👍, 19 commentaires, ouverte
- airbyte#50429 « abctl local install on M4 macOS fails » — 4 👍, 14 commentaires, ouverte
- airbyte#70969 « Cannot install Airbyte 2.0.1 — Docker images not found » — 5 👍, ouverte
- airbyte#84928 « Fresh installs cannot publish Connector Builder » — 4 👍, ouverte (08/2026)
- airbyte#3239 « Define Airbyte's Minimum Resource Requirements » — 19 👍, gelée
- airbyte#69336 « [source-postgres] Excessive memory usage (60 % of heap) » — 4 👍
- kestra#11881 « Kestra's IDE is very slow » — 9 commentaires
- mage-ai#5559 « Memory leak in mage app » — ouverte

### Validation / tests
- kestra#4927 « CLI Validate marking 1 flow as invalid when it's valid » — 18 commentaires
- kestra#844 « Test unit / integration of flows » — **fermée non planifiée**
- kestra#11659 « Add dry-run option to API requests » — ouverte
- redpanda connect#4998 — lint qui échoue sur des pipelines valides (10/2026)

### Configuration
- sling-cli#362 « Externalize connection config » — ouverte
- meltano#6386 « add support for `env` key for `jobs` » — ouverte
- kestra#1865 « Simplify secrets setup in getting started » — **non planifiée**
- airbyte#65568 « Connector builder: invalid yaml since 1.7.1 » — 9 👍

### Windows
- sling-cli#744 et #783 — plantages sous Windows (2026)
- mage-ai#5287 — exécution impossible depuis l'interface sous Windows
- kestra#12989 « Process Runner Fails Silently on Windows » — ouverte
- dlt#2339 — « Access is denied » sous Windows

### Fonctionnalités demandées
- dlt#2049 « ssh tunnelling for database connections » — 7 👍, ouverte
- pipelinewise#218 « filter rows with a custom WHERE clause in tap config » — 4 👍, ouverte
- sling-cli#545 « Excluding columns when selecting from Parquet » — **non planifiée**
- sling-cli#524 « Create index when replicating into an existing table » — ouverte

## 4. Lacunes à vérifier dans Hydra ETL (test obligatoire avant toute réponse)

| # | Besoin | Source | Hydra ETL le fait ? | Test à mener |
|---|---|---|---|---|
| 1 | Installation légère, sans Docker, empreinte mémoire faible | Airbyte | À mesurer | `pip install` dans un venv propre ; RAM d'un job CSV → Postgres de 1 M lignes |
| 2 | Validation fiable en CI (pas de faux négatifs) + GitHub Action | kestra#4927 | À vérifier | `hdrctl validate` sur 10 YAML valides et invalides |
| 3 | Tests unitaires des pipelines | kestra#844 | `hdrctl test` ? | Écrire un test sur un job d'exemple |
| 4 | Fonctionnement natif sous Windows | Sling, Mage, Kestra, dlt | À vérifier | Exécution complète sous Windows (PowerShell) |
| 5 | Connexions / secrets externalisés (variables d'environnement) | sling#362, meltano#6386 | À vérifier | Job utilisant `${ENV}` |
| 6 | Filtre WHERE à la source | pipelinewise#218 | À vérifier | Job MySQL/Postgres avec filtre |
| 7 | Exclure des colonnes d'un Parquet | sling#545 | Probable | Job Parquet → CSV avec sélection de colonnes |
| 8 | Tunnel SSH pour les bases | dlt#2049 | Probablement non | Décider si cela entre dans le périmètre |
| 9 | Créer des index sur la table cible | sling#524 | À vérifier | Job → Postgres avec index |

## 5. Règles d'engagement
- Les issues des concurrents servent à **écouter**, pas à promouvoir. On ne répond dans une issue que si l'auteur demande explicitement une alternative, avec « disclosure: I'm the author ».
- Aucun scénario Hydra ETL n'est publié sans test (✅ TESTÉ / ⛔ NON TESTÉ).
- On compare par les faits, sans dénigrement. Pas de posture de « sauveur » : Hydra ETL est en bêta, avec 4 ★.
