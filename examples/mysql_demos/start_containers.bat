@echo off
REM Script de lancement des conteneurs MySQL/MariaDB pour tests Hydra
REM À exécuter depuis le dossier racine du projet

echo ========================================
echo Démarrage des conteneurs MySQL/MariaDB
echo ========================================
echo.

cd tests\docker

echo [1/3] Arrêt des conteneurs existants (si présents)...
docker-compose -f docker-compose.test.yml down 2>nul

echo.
echo [2/3] Démarrage des conteneurs...
docker-compose -f docker-compose.test.yml up -d

echo.
echo [3/3] Vérification des healthchecks (attendre ~10-15 secondes)...
timeout /t 15 /nobreak >nul

docker-compose -f docker-compose.test.yml ps

echo.
echo ========================================
echo Conteneurs prêts 
echo ========================================
echo.
echo MySQL  : 127.0.0.1:3307 (user=hydra, password=hydra, database=hydra_test)
echo MariaDB: 127.0.0.1:3308 (user=hydra, password=hydra, database=hydra_test)
echo.
echo Pour arrêter : docker-compose -f tests\docker\docker-compose.test.yml down
echo.

cd ..\..
