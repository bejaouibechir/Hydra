@echo off
REM ============================================================================
REM Générateur de fixtures CSV (Windows .bat)
REM ----------------------------------------------------------------------------
REM Objectif :
REM - Générer des CSV mocks locaux dans : tests\fixtures\csv
REM - Permettre de régénérer rapidement les fichiers pendant les tests/démos
REM
REM Utilisation (depuis la racine du projet Hydra) :
REM   tests\fixtures\csv\generate_mocks.bat
REM
REM Remarque :
REM - Les tests pytest n'ont PAS besoin d'exécuter ce .bat pour passer
REM   si les fichiers CSV existent déjà dans le repo.
REM ============================================================================

setlocal enabledelayedexpansion

REM Dossier cible (relatif à la racine du projet)
set "TARGET_DIR=tests\fixtures\csv"

REM Crée le dossier s'il n'existe pas
if not exist "%TARGET_DIR%" (
  mkdir "%TARGET_DIR%"
)

REM ---------------------------------------------------------------------------
REM users.csv
REM ---------------------------------------------------------------------------
REM Colonnes :
REM - id     : identifiant user
REM - name   : nom
REM - active : "true"/"false" (strings volontairement)
REM ---------------------------------------------------------------------------
(
  echo id,name,active
  echo 1,Alice,true
  echo 2,Bob,false
  echo 3,Charly,true
) > "%TARGET_DIR%\users.csv"

REM ---------------------------------------------------------------------------
REM orders.csv
REM ---------------------------------------------------------------------------
REM Colonnes :
REM - order_id : identifiant commande
REM - user_id  : identifiant user
REM - total    : montant
REM ---------------------------------------------------------------------------
(
  echo order_id,user_id,total
  echo 1001,1,19.90
  echo 1002,2,5.00
  echo 1003,1,12.50
) > "%TARGET_DIR%\orders.csv"

echo.
echo [OK] Fixtures CSV générées dans: %TARGET_DIR%
echo.
endlocal
