@echo off
REM ============================================================================
REM Générateur de démos MySQL/MariaDB pour Hydra (Étape 8)
REM ============================================================================
REM Ce script crée automatiquement toute la structure examples/mysql_demos/
REM avec tous les fichiers YAML, scripts, et données de test.
REM
REM Utilisation (depuis la racine du projet Hydra) :
REM   examples\generate_mysql_demos.bat
REM
REM Auteur : Claude (Anthropic)
REM Date : Décembre 2024
REM ============================================================================

setlocal enabledelayedexpansion

echo ========================================
echo Génération des démos MySQL/MariaDB
echo ========================================
echo.

REM Dossier de base
set "BASE_DIR=examples\mysql_demos"

REM Créer la structure de dossiers
echo [1/17] Création de la structure de dossiers...
if not exist "%BASE_DIR%" mkdir "%BASE_DIR%"
if not exist "%BASE_DIR%\mysql_to_csv" mkdir "%BASE_DIR%\mysql_to_csv"
if not exist "%BASE_DIR%\mysql_to_csv\data" mkdir "%BASE_DIR%\mysql_to_csv\data"
if not exist "%BASE_DIR%\csv_to_mysql" mkdir "%BASE_DIR%\csv_to_mysql"
if not exist "%BASE_DIR%\csv_to_mysql\data" mkdir "%BASE_DIR%\csv_to_mysql\data"
if not exist "%BASE_DIR%\mysql_to_mysql" mkdir "%BASE_DIR%\mysql_to_mysql"

REM ============================================================================
REM FICHIER 1: .env.example
REM ============================================================================
echo [2/17] Création de .env.example...
(
echo # Configuration MySQL/MariaDB pour les démos Hydra ^(Étape 8^)
echo # Ce fichier doit être placé à la racine du projet ou dans examples/mysql_demos/
echo.
echo # MySQL Test Container ^(port 3307^)
echo MYSQL_HOST=127.0.0.1
echo MYSQL_PORT=3307
echo MYSQL_USER=hydra
echo MYSQL_PASSWORD=hydra
echo MYSQL_DATABASE=hydra_test
echo.
echo # MariaDB Test Container ^(port 3308^)
echo MARIADB_HOST=127.0.0.1
echo MARIADB_PORT=3308
echo MARIADB_USER=hydra
echo MARIADB_PASSWORD=hydra
echo MARIADB_DATABASE=hydra_test
) > "%BASE_DIR%\.env.example"

REM ============================================================================
REM FICHIER 2: start_containers.bat
REM ============================================================================
echo [3/17] Création de start_containers.bat...
(
echo @echo off
echo REM Script de lancement des conteneurs MySQL/MariaDB pour tests Hydra
echo REM À exécuter depuis le dossier racine du projet
echo.
echo echo ========================================
echo echo Démarrage des conteneurs MySQL/MariaDB
echo echo ========================================
echo echo.
echo.
echo cd tests\docker
echo.
echo echo [1/3] Arrêt des conteneurs existants ^(si présents^)...
echo docker-compose -f docker-compose.test.yml down 2^>nul
echo.
echo echo.
echo echo [2/3] Démarrage des conteneurs...
echo docker-compose -f docker-compose.test.yml up -d
echo.
echo echo.
echo echo [3/3] Vérification des healthchecks ^(attendre ~10-15 secondes^)...
echo timeout /t 15 /nobreak ^>nul
echo.
echo docker-compose -f docker-compose.test.yml ps
echo.
echo echo.
echo echo ========================================
echo echo Conteneurs prêts !
echo echo ========================================
echo echo.
echo echo MySQL  : 127.0.0.1:3307 ^(user=hydra, password=hydra, database=hydra_test^)
echo echo MariaDB: 127.0.0.1:3308 ^(user=hydra, password=hydra, database=hydra_test^)
echo echo.
echo echo Pour arrêter : docker-compose -f tests\docker\docker-compose.test.yml down
echo echo.
echo.
echo cd ..\..
) > "%BASE_DIR%\start_containers.bat"

REM ============================================================================
REM FICHIER 3: run_all_demos.bat
REM ============================================================================
echo [4/17] Création de run_all_demos.bat...
(
echo @echo off
echo REM Script d'exécution des 3 démos MySQL/MariaDB Hydra
echo REM À exécuter depuis examples/mysql_demos/
echo.
echo echo ========================================
echo echo Exécution des démos MySQL/MariaDB Hydra
echo echo ========================================
echo echo.
echo.
echo REM Vérifier que .env existe
echo if not exist .env ^(
echo     echo ERREUR: Fichier .env manquant !
echo     echo.
echo     echo Créez un fichier .env en copiant .env.example :
echo     echo   copy .env.example .env
echo     echo.
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo [Démo 1/3] MySQL -^> CSV
echo echo ==================
echo cd mysql_to_csv
echo hydra run .
echo if errorlevel 1 ^(
echo     echo ERREUR lors de l'exécution de la démo 1
echo     pause
echo     exit /b 1
echo ^)
echo echo.
echo echo Résultat : data\employees_export.csv
echo type data\employees_export.csv
echo echo.
echo cd ..
echo.
echo echo.
echo echo [Démo 2/3] CSV -^> MySQL
echo echo ==================
echo cd csv_to_mysql
echo hydra run .
echo if errorlevel 1 ^(
echo     echo ERREUR lors de l'exécution de la démo 2
echo     pause
echo     exit /b 1
echo ^)
echo echo.
echo echo Vérification MySQL :
echo docker exec -it hydra_mysql_test mysql -uhydra -phydra hydra_test -e "SELECT COUNT^(^*^) as total FROM employees;"
echo echo.
echo cd ..
echo.
echo echo.
echo echo [Démo 3/3] MySQL -^> MySQL ^(vers MariaDB^)
echo echo ==========================================
echo cd mysql_to_mysql
echo hydra run .
echo if errorlevel 1 ^(
echo     echo ERREUR lors de l'exécution de la démo 3
echo     pause
echo     exit /b 1
echo ^)
echo echo.
echo echo Vérification MariaDB :
echo docker exec -it hydra_mariadb_test mariadb -uhydra -phydra hydra_test -e "SELECT * FROM employees LIMIT 3;"
echo echo.
echo cd ..
echo.
echo echo.
echo echo ========================================
echo echo Toutes les démos terminées avec succès !
echo echo ========================================
echo echo.
echo pause
) > "%BASE_DIR%\run_all_demos.bat"

REM ============================================================================
REM DÉMO 1: MySQL → CSV
REM ============================================================================
echo [5/17] Création de mysql_to_csv/sources.yaml...
(
echo # Sources pour démo : MySQL -^> CSV
echo # IMPORTANT : Utilise ${ENV:...} pour résoudre les secrets depuis .env
echo.
echo sources:
echo   mysql_employees:
echo     type: mysql
echo     connection:
echo       host: ${ENV:MYSQL_HOST}
echo       port: ${ENV:MYSQL_PORT}
echo       user: ${ENV:MYSQL_USER}
echo       password: ${ENV:MYSQL_PASSWORD}
echo       database: ${ENV:MYSQL_DATABASE}
echo     extract:
echo       table: employees
echo       batch_size: 100
) > "%BASE_DIR%\mysql_to_csv\sources.yaml"

echo [6/17] Création de mysql_to_csv/destinations.yaml...
(
echo # Destinations pour démo : MySQL -^> CSV
echo.
echo destinations:
echo   csv_employees:
echo     type: csv
echo     load:
echo       path: ./data/employees_export.csv
echo       mode: replace
) > "%BASE_DIR%\mysql_to_csv\destinations.yaml"

echo [7/17] Création de mysql_to_csv/transformations.yaml...
(
echo # Transformations pour démo : MySQL -^> CSV
echo # MVP : Aucune transformation ^(export direct^)
echo.
echo steps:
echo   - select:
echo       columns: ["id", "full_name", "email", "age", "created_at"]
) > "%BASE_DIR%\mysql_to_csv\transformations.yaml"

echo [8/17] Création de mysql_to_csv/pipeline.yaml...
(
echo # Pipeline pour démo : MySQL -^> CSV
echo # Extrait la table employees de MySQL vers un fichier CSV
echo.
echo pipeline:
echo   name: mysql_to_csv_demo
echo   source: mysql_employees
echo   destination: csv_employees
echo   transformations: transformations
) > "%BASE_DIR%\mysql_to_csv\pipeline.yaml"

REM ============================================================================
REM DÉMO 2: CSV → MySQL
REM ============================================================================
echo [9/17] Création de csv_to_mysql/data/new_employees.csv...
(
echo id,full_name,email,age
echo 1,Mohamed Salah,mohamed@tech.tn,29
echo 2,Leila Gharbi,leila@corp.tn,34
echo 3,Yassine Mejri,yassine@startup.tn,27
) > "%BASE_DIR%\csv_to_mysql\data\new_employees.csv"

echo [10/17] Création de csv_to_mysql/sources.yaml...
(
echo # Sources pour démo : CSV -^> MySQL
echo.
echo sources:
echo   csv_new_employees:
echo     type: csv
echo     extract:
echo       path: ./data/new_employees.csv
echo       batch_size: 100
) > "%BASE_DIR%\csv_to_mysql\sources.yaml"

echo [11/17] Création de csv_to_mysql/destinations.yaml...
(
echo # Destinations pour démo : CSV -^> MySQL
echo # IMPORTANT : Utilise ${ENV:...} pour résoudre les secrets depuis .env
echo.
echo destinations:
echo   mysql_employees:
echo     type: mysql
echo     connection:
echo       host: ${ENV:MYSQL_HOST}
echo       port: ${ENV:MYSQL_PORT}
echo       user: ${ENV:MYSQL_USER}
echo       password: ${ENV:MYSQL_PASSWORD}
echo       database: ${ENV:MYSQL_DATABASE}
echo     load:
echo       table: employees
echo       mode: append
) > "%BASE_DIR%\csv_to_mysql\destinations.yaml"

echo [12/17] Création de csv_to_mysql/transformations.yaml...
(
echo # Transformations pour démo : CSV -^> MySQL
echo # MVP : Validation et nettoyage basique
echo.
echo steps:
echo   - select:
echo       columns: ["id", "full_name", "email", "age"]
echo   - filter:
echo       expr: "age ^> 0"
) > "%BASE_DIR%\csv_to_mysql\transformations.yaml"

echo [13/17] Création de csv_to_mysql/pipeline.yaml...
(
echo # Pipeline pour démo : CSV -^> MySQL
echo # Charge un fichier CSV vers la table employees de MySQL
echo.
echo pipeline:
echo   name: csv_to_mysql_demo
echo   source: csv_new_employees
echo   destination: mysql_employees
echo   transformations: transformations
) > "%BASE_DIR%\csv_to_mysql\pipeline.yaml"

REM ============================================================================
REM DÉMO 3: MySQL → MySQL (MariaDB)
REM ============================================================================
echo [14/17] Création de mysql_to_mysql/sources.yaml...
(
echo # Sources pour démo : MySQL -^> MySQL ^(réplication table^)
echo # IMPORTANT : Utilise ${ENV:...} pour résoudre les secrets depuis .env
echo.
echo sources:
echo   mysql_source:
echo     type: mysql
echo     connection:
echo       host: ${ENV:MYSQL_HOST}
echo       port: ${ENV:MYSQL_PORT}
echo       user: ${ENV:MYSQL_USER}
echo       password: ${ENV:MYSQL_PASSWORD}
echo       database: ${ENV:MYSQL_DATABASE}
echo     extract:
echo       table: employees
echo       batch_size: 50
) > "%BASE_DIR%\mysql_to_mysql\sources.yaml"

echo [15/17] Création de mysql_to_mysql/destinations.yaml...
(
echo # Destinations pour démo : MySQL -^> MySQL ^(vers MariaDB^)
echo # IMPORTANT : Utilise ${ENV:...} pour résoudre les secrets depuis .env
echo # Note : On cible le conteneur MariaDB pour démontrer la compatibilité
echo.
echo destinations:
echo   mariadb_target:
echo     type: mariadb
echo     connection:
echo       host: ${ENV:MARIADB_HOST}
echo       port: ${ENV:MARIADB_PORT}
echo       user: ${ENV:MARIADB_USER}
echo       password: ${ENV:MARIADB_PASSWORD}
echo       database: ${ENV:MARIADB_DATABASE}
echo     load:
echo       table: employees
echo       mode: replace
) > "%BASE_DIR%\mysql_to_mysql\destinations.yaml"

echo [16/17] Création de mysql_to_mysql/transformations.yaml...
(
echo # Transformations pour démo : MySQL -^> MySQL
echo # Enrichissement : ajout d'un champ calculé
echo.
echo steps:
echo   - select:
echo       columns: ["id", "full_name", "email", "age"]
echo   - calculate:
echo       column: "age_category"
echo       expr: "'Senior' if age ^>= 30 else 'Junior'"
echo   - rename:
echo       mapping:
echo         full_name: name
) > "%BASE_DIR%\mysql_to_mysql\transformations.yaml"

echo [17/17] Création de mysql_to_mysql/pipeline.yaml...
(
echo # Pipeline pour démo : MySQL -^> MySQL ^(MySQL -^> MariaDB^)
echo # Copie et enrichit la table employees de MySQL vers MariaDB
echo.
echo pipeline:
echo   name: mysql_to_mysql_demo
echo   source: mysql_source
echo   destination: mariadb_target
echo   transformations: transformations
) > "%BASE_DIR%\mysql_to_mysql\pipeline.yaml"

REM ============================================================================
REM README.md (création en plusieurs parties à cause des limitations BAT)
REM ============================================================================
echo [Bonus] Création de README.md...
(
echo # Démos MySQL/MariaDB - Hydra ^(Étape 8^)
echo.
echo ## 📦 Prérequis
echo.
echo 1. **Docker** installé et démarré
echo 2. **Python 3.10+** avec les dépendances Hydra installées
echo 3. **Fichier .env** configuré ^(copier `.env.example` -^> `.env`^)
echo.
echo ## 🚀 Démarrage des Conteneurs
echo.
echo ```bash
echo # Depuis le dossier tests/docker/
echo cd tests/docker
echo docker-compose -f docker-compose.test.yml up -d
echo.
echo # Vérifier que les conteneurs sont healthy
echo docker ps
echo ```
echo.
echo ## 🎯 Exécution des Démos
echo.
echo ### Démo 1 : MySQL -^> CSV
echo.
echo ```bash
echo cd examples/mysql_demos/mysql_to_csv
echo hydra run .
echo cat data/employees_export.csv
echo ```
echo.
echo ### Démo 2 : CSV -^> MySQL
echo.
echo ```bash
echo cd examples/mysql_demos/csv_to_mysql
echo hydra run .
echo docker exec -it hydra_mysql_test mysql -uhydra -phydra hydra_test -e "SELECT * FROM employees;"
echo ```
echo.
echo ### Démo 3 : MySQL -^> MySQL ^(vers MariaDB^)
echo.
echo ```bash
echo cd examples/mysql_demos/mysql_to_mysql
echo hydra run .
echo docker exec -it hydra_mariadb_test mariadb -uhydra -phydra hydra_test -e "SELECT * FROM employees;"
echo ```
echo.
echo ## 🔧 Configuration
echo.
echo Copier `.env.example` -^> `.env` :
echo.
echo ```bash
echo copy .env.example .env
echo ```
echo.
echo ## 🛑 Arrêt des Conteneurs
echo.
echo ```bash
echo cd tests/docker
echo docker-compose -f docker-compose.test.yml down
echo ```
echo.
echo ## 📚 Sécurité
echo.
echo ✅ Tous les fichiers YAML utilisent `${ENV:...}` pour les secrets
echo ✅ Pas de credentials en dur
echo ✅ Mot de passe masqué dans les logs
echo.
echo ## 🎓 Prochaines Étapes
echo.
echo - Étape 9 : Tests d'intégration automatisés
echo - Étape 10 : Support incrémental
echo - Étape 11 : Mode upsert
) > "%BASE_DIR%\README.md"

REM ============================================================================
REM Finalisation
REM ============================================================================
echo.
echo ========================================
echo ✅ Génération terminée avec succès !
echo ========================================
echo.
echo Structure créée dans: %BASE_DIR%
echo.
echo Fichiers générés:
echo   ├── .env.example
echo   ├── README.md
echo   ├── start_containers.bat
echo   ├── run_all_demos.bat
echo   ├── mysql_to_csv/
echo   │   ├── sources.yaml
echo   │   ├── destinations.yaml
echo   │   ├── transformations.yaml
echo   │   └── pipeline.yaml
echo   ├── csv_to_mysql/
echo   │   ├── data/new_employees.csv
echo   │   ├── sources.yaml
echo   │   ├── destinations.yaml
echo   │   ├── transformations.yaml
echo   │   └── pipeline.yaml
echo   └── mysql_to_mysql/
echo       ├── sources.yaml
echo       ├── destinations.yaml
echo       ├── transformations.yaml
echo       └── pipeline.yaml
echo.
echo 📋 Prochaines étapes:
echo   1. cd examples\mysql_demos
echo   2. copy .env.example .env
echo   3. start_containers.bat
echo   4. run_all_demos.bat
echo.
pause