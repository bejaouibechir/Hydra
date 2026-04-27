# Document 1 – Sprint 1 Backlog

**Projet Hydra ETL**  
**Période** : 02–04 Janvier 2026  
**Durée estimée totale** : 8 à 10 heures  
**Objectif principal** : Livrer le mode **upsert** pour MySQL/MariaDB en production-ready  
**Objectif secondaire** : Poser les premières briques d’extensibilité sans scope creep

**Statut** : Sprint validé par le consortium – focus strict sur l’upsert + préparation minimale registry

### Principes directeurs du sprint

- Pas de breaking change sur le DSL Hydra v1.1
- Aucun nouveau connecteur (MySQL/MariaDB + CSV uniquement)
- Priorité absolue : qualité, tests, documentation
- Pas d’implémentation d’adapter concret (seulement interface vide si temps)
- Estimation temps inclut écriture + tests + debug

### Backlog détaillé Sprint 1

| #   | Priorité | Tâche                                                                          | Fichier(s) principal(s)                         | Temps estimé | Livrables concrets                                                                               | Critère de finition (Definition of Done)                             |
| --- | -------- | ------------------------------------------------------------------------------ | ----------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| 1.1 | P0       | Refactor léger du registry des connecteurs → dictionnaire de constructeurs     | `internal/connector/registry.py`                | 40–50 min    | Dictionnaire `CONNECTOR_REGISTRY` + 2–3 factories simples (csv, mysql, mariadb)                  | +1 ligne = nouveau type de connecteur sans modifier le core          |
| 1.2 | P0       | Extension du modèle `LoadConfig` pour supporter le mode `upsert` + champ `key` | `internal/parser/destination.py`                | 45–60 min    | `LoadMode` enum (append, replace, upsert), champ `key: Optional[List[str]]`, validation stricte  | Validation Pydantic échoue si upsert sans key                        |
| 2.1 | P0       | Implémentation de la génération SQL pour upsert MySQL/MariaDB                  | `internal/connector/mysql_mariadb_connector.py` | 90–120 min   | Méthode `_build_upsert_sql(columns, key_columns)` → syntaxe `INSERT ... ON DUPLICATE KEY UPDATE` | SQL généré correct pour clés simples et composites + tests unitaires |
| 2.2 | P0       | Adaptation de `write_batches` / `load_batches` pour gérer le mode upsert       | `internal/connector/mysql_mariadb_connector.py` | 60–90 min    | Branchement mode → append / replace / upsert, gestion transactionnelle par batch                 | Insertion idempotente, rollback correct sur erreur                   |
| 2.3 | P0       | Validation runtime des capacités destination dans l’executor                   | `internal/runner/executor.py`                   | 30–45 min    | Méthode `_validate_destination_mode()` qui vérifie que le mode est supporté par le connecteur    | Erreur claire si mode upsert sur CSV par ex.                         |
| 3.1 | P0       | Tests unitaires génération SQL upsert                                          | `tests/unit/test_mysql_upsert_sql.py` (nouveau) | 45–60 min    | 6–8 tests : clé simple, composite, colonnes partielles, sans clé (erreur)                        | Couverture > 90% sur la génération SQL                               |
| 3.2 | P0       | Tests d’intégration E2E CSV → MySQL upsert (idempotence)                       | `tests/integration/test_upsert_csv_to_mysql.py` | 90–120 min   | Fixtures Docker MySQL, seed initial, 2 runs successifs → même résultat final                     | Assert sur nombre de lignes et contenu final identique               |
| 3.3 | P0       | Tests parser destination (nouveaux modes)                                      | `tests/unit/test_destination_parser.py`         | 20–30 min    | 4 tests : upsert sans key → erreur, upsert avec key → OK, modes existants inchangés              | Validation Pydantic exhaustive                                       |
| 4.1 | P1       | Création exemple fonctionnel CSV → MySQL upsert                                | `examples/mysql_demos/csv_to_mysql_upsert/`     | 30–45 min    | Nouveau dossier avec sources.yaml, destinations.yaml, pipeline.yaml, data/input.csv              | Exemple exécutable via CLI                                           |
| 4.2 | P1       | Mise à jour README – section Load Modes                                        | `README.md` + `docs/load-modes.md`              | 30–45 min    | Tableau comparatif modes, syntaxe upsert, limitations actuelles, exemple YAML                    | Documentation claire et à jour                                       |
| 5.1 | P2       | (Optionnel) Création module adapters vide + doc pattern                        | `internal/adapters/__init__.py`                 | 20–30 min    | Interface `TableAdapter` vide + docstring détaillée + README pattern                             | Seulement si temps restant – pas bloquant                            |

### Récapitulatif planning & capacité

- **Temps minimum** : ~7h (backlogs P0 stricts)
- **Temps réaliste** : **8–10h** (incluant debug/tests Docker)
- **Capacité recommandée** : 1 jour complet (ou 2 demi-journées)
- **Risques principaux** :
  - Problèmes Docker MySQL (seed, connexion, volumes)
  - Bugs subtils sur upsert avec clés composites
  - Temps perdu sur tests d’intégration

### Critères de fin de sprint (DoD Sprint)

1. Mode upsert fonctionne sur MySQL/MariaDB (idempotence prouvée)
2. Tests unitaires SQL + intégration E2E verts (Docker)
3. Exemple CSV → MySQL upsert fonctionnel et documenté
4. Registry passé en factory simple (extensible)
5. Aucun breaking change DSL
6. README + exemples à jour

Prochain document à générer : **Vision Stratégique & Architecture Long Terme**  
Souhaitez-vous que je le rédige maintenant, ou préférez-vous d’abord valider / ajuster ce backlog Sprint 1 ?

# Avis de chatgpt à propos du sprint 1

## Avis sur Document 1 – Sprint 1

Ce document est très bon : il est “actionnable”, mesurable, et il protège le sprint contre le scope creep.

Mes suggestions (petites, mais utiles) :

1. DSL  
   Vous dites “pas de breaking change”, mais vous ajoutez mode upsert et key : c’est une extension non-breaking. Ajoutez une phrase du type “extension additive” pour éviter les débats.
- Pré-requis MySQL/MariaDB  
  Ajoutez un critère de DoD : “la table cible doit avoir PK ou unique index compatible”. Sinon l’upsert est imprévisible dans certains cas.

- Executor validation  
  La tâche 2.3 est très bien (erreur claire si upsert sur CSV). Je recommanderais aussi d’ajouter : “erreur claire si key contient une colonne absente”.

Estimation  
Le doc est honnête : 8–10h avec debug/tests Docker. Très bien.

Je proposerais juste un mini plan de coupe si retard : l’interface adapter (5.1) reste optionnelle, et docs (4.2) peut être réduite au strict nécessaire.#  

Voila
