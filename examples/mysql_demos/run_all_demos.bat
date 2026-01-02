@echo off
REM Script d'exécution des 3 démos MySQL/MariaDB Hydra
REM À exécuter depuis la RACINE du projet Hydra

echo ============================================================
echo 🚀 Exécution des démos MySQL/MariaDB Hydra
echo ============================================================
echo.

REM Vérifier que nous sommes à la racine (cli\main.py doit exister)
if not exist cli\main.py (
    echo ERREUR: Ce script doit être exécuté depuis la racine du projet Hydra
    echo.
    echo Usage depuis la racine :
    echo   examples\mysql_demos\run_all_demos.bat
    echo.
    pause
    exit /b 1
)

REM Vérifier que .env existe
if not exist .env (
    echo ERREUR: Fichier .env manquant à la racine du projet
    echo.
    echo Créez un fichier .env en copiant .env.example :
    echo   copy .env.example .env
    echo.
    pause
    exit /b 1
)

REM Vérifier que les containers Docker sont démarrés
echo [Préparation] Vérification des containers Docker...
docker ps | findstr hydra_mysql_test > nul
if errorlevel 1 (
    echo.
    echo ERREUR: Container MySQL non démarré
    echo.
    echo Démarrez les containers avec :
    echo   cd examples\mysql_demos
    echo   start_containers.bat
    echo.
    pause
    exit /b 1
)
echo ✅ Containers MySQL/MariaDB prêts
echo.

echo ============================================================
echo [Démo 1/3] MySQL → CSV
echo ============================================================
py cli\main.py run examples\mysql_demos\mysql_to_csv
if errorlevel 1 (
    echo.
    echo ❌ ERREUR lors de l'exécution de la démo 1
    pause
    exit /b 1
)
echo.
echo 📄 Fichier généré : examples\mysql_demos\mysql_to_csv\data\employees_export.csv
if exist examples\mysql_demos\mysql_to_csv\data\employees_export.csv (
    echo ✅ Fichier créé avec succès
    type examples\mysql_demos\mysql_to_csv\data\employees_export.csv
) else (
    echo ❌ ERREUR: Fichier CSV non créé
)
echo.

echo ============================================================
echo [Démo 2/3] CSV → MySQL
echo ============================================================
py cli\main.py run examples\mysql_demos\csv_to_mysql
if errorlevel 1 (
    echo.
    echo ❌ ERREUR lors de l'exécution de la démo 2
    pause
    exit /b 1
)
echo.
echo 🔍 Vérification MySQL (nombre total d'employés) :
docker exec hydra_mysql_test mysql -uhydra -phydra hydra_test -e "SELECT COUNT(*) as total FROM employees;" 2>nul
echo.

echo ============================================================
echo [Démo 3/3] MySQL → MariaDB
echo ============================================================
py cli\main.py run examples\mysql_demos\mysql_to_mysql
if errorlevel 1 (
    echo.
    echo ❌ ERREUR lors de l'exécution de la démo 3
    pause
    exit /b 1
)
echo.
echo 🔍 Vérification MariaDB (3 premiers employés) :
docker exec hydra_mariadb_test mariadb -uhydra -phydra hydra_test -e "SELECT * FROM employees LIMIT 3;" 2>nul
echo.

echo ============================================================
echo ✅ Toutes les démos terminées avec succès !
echo ============================================================
echo.
echo 📊 Résumé :
echo   1. MySQL → CSV       : ✅
echo   2. CSV → MySQL       : ✅
echo   3. MySQL → MariaDB   : ✅
echo.
pause