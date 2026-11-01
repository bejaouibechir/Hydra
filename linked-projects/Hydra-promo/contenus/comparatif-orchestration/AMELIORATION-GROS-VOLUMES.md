# Amélioration prioritaire — moteur « gros volumes » (décision du 29/10/2026)

Origine : test de montée en volume (`claude/comparatif-montee-en-volume.md`). Hydra ETL est le plus rapide jusqu'à ≈ 2 millions de lignes (≈ 5 M avec `native`), puis dlt + dbt (DuckDB) devient 2 fois plus rapide à 20 M et reste sous 0,8 Go de mémoire, quand Hydra ETL monte à 5,4 Go.

## Décisions de Bechir

- **Python reste le moteur de référence et par défaut sous ≈ 2 millions de lignes** : il y donne des résultats brillants (jusqu'à 6 fois plus rapide que dlt + dbt à 200 000 lignes).
- **Au-dessus, un moteur alternatif, sur le même modèle que l'accélérateur Rust `native`** : implémentation optionnelle (extra `hydra-etl[duckdb]`), choisie par opération, jamais de repli silencieux, tests de parité avec la référence Python.
- **À noter comme amélioration prioritaire.**

## Diagnostic

1. **Mémoire** : pandas rassemble toutes les lignes avant la jointure et l'agrégation (≈ 270 Mo par million de lignes). DuckDB travaille **en flux** : il ne garde que la petite table d'une jointure et les totaux en cours d'une agrégation, et déborde sur le disque si besoin. dlt ne fait que charger (par lots, via le disque) ; dbt ne calcule pas, il envoie du SQL à DuckDB.
2. **Lecture CSV ≈ 70 % du temps** (0.14.0, `csv_connector.py`) : Python pur ligne par ligne, un seul cœur ; une chaîne Python par valeur, colonnes pandas « objet » reconverties par `cast` ; lots de 10 000 (100 000 au plus) ; parité exacte avec `csv.DictReader` imposée. **À vérifier : l'accélérateur Rust ne semble pas branché sur `csv.read` dans `_extract_frames_one`** (appelle toujours `_frames_python`).

## Solution retenue

| Élément | Contenu |
|---|---|
| Moteur gros volumes | DuckDB : lecture → `filter` → `join` → `aggregate` → `sort` (+ `cast`, `calculate`) traduits en SQL et exécutés en flux, multi-cœur, débordement disque. `script` (Python libre) reste sur pandas. |
| Choix automatique | `engine: auto` : estimation avant le run (taille du fichier CSV/Parquet, statistiques de la table en base), seuil réglable `large_volume_threshold` (≈ 2 M par défaut), forçable par job (`engine: pandas` / `duckdb`). Choix affiché dans `--dry-run`, Studio et le profil, avec la raison. |
| Garanties | Inchangées : tout ou rien, `rollback`, `fallback`, `timeout` agissent au chargement et au workflow, pas dans le moteur de calcul. |
| Parité | Tests : mêmes résultats que la référence Python, comme pour `native`. |
| Cache | **Une source lue une seule fois par run et partagée entre les jobs** (conversion en Parquet ou base DuckDB temporaire) : évite de relire 20 M lignes pour chaque job. Plus tard : cache identifié par empreinte (taille + date) pour les runs répétés sur des données inchangées. **Pas de cache en mémoire.** |
| Écarté | Moteur Rust maison pour jointures et agrégations (des mois de travail, moins éprouvé) ; Rust garde la lecture et les petites opérations. |

## Étapes (une étape = code + tests + doc + commit, accord de Bechir entre chaque)

1. Lecture CSV : brancher réellement l'accélérateur Rust (ou pyarrow) sur `csv.read` ; mesurer.
2. Choix du moteur par volume dans `_backend.py` : seuil, estimation, `engine: auto | pandas | duckdb`.
3. Moteur DuckDB pour les opérations globales + tests de parité.
4. Source partagée entre les jobs d'un run (cache Parquet / DuckDB).
5. Affichage du moteur choisi (`--dry-run`, Studio, profil) ; DSL, schémas, doc.
6. Rejouer `montee-en-volume` (200 000 → 20 M lignes) pour mesurer le nouveau seuil.

Objectif mesurable : à 20 M lignes, durée ≤ dlt + dbt (46 s sur 2 processeurs) et mémoire < 1 Go, sans perdre l'avantage sous 2 M.
