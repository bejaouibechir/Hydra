@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Hydra - Etape 7 : Generation demo officielle examples/minimal_csv
REM - Trouve la racine projet automatiquement (via presence de cli\main.py)
REM - Cree examples\minimal_csv\... avec chemins relatifs
REM - Ecrit les fichiers ligne par ligne + verifications
REM ============================================================

REM --- 1) Trouver la racine du projet (on remonte depuis le dossier courant)
set "ROOT="
set "CUR=%CD%"

:find_root
if exist "%CUR%\cli\main.py" (
  set "ROOT=%CUR%"
  goto :root_found
)

REM Remonter d'un niveau
for %%I in ("%CUR%") do set "PARENT=%%~dpI"
REM Enlever le "\" final
set "PARENT=%PARENT:~0,-1%"

REM Si on ne peut plus remonter, stop
if /I "%PARENT%"=="%CUR%" goto :root_not_found
set "CUR=%PARENT%"
goto :find_root

:root_not_found
echo ERREUR: Impossible de trouver la racine du projet (cli\main.py introuvable).
echo Astuce: place ce BAT a la racine du projet et relance.
exit /b 1

:root_found
echo [OK] Racine projet detectee:
echo      %ROOT%
echo.

REM --- 2) Definir les chemins
set "EXAMPLES_DIR=%ROOT%\examples"
set "JOB_DIR=%EXAMPLES_DIR%\minimal_csv"
set "DATA_DIR=%JOB_DIR%\data"

echo [1/7] Creation des dossiers...
if not exist "%EXAMPLES_DIR%" mkdir "%EXAMPLES_DIR%"
if not exist "%JOB_DIR%" mkdir "%JOB_DIR%"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

if not exist "%JOB_DIR%\" (
  echo ERREUR: dossier job non cree: %JOB_DIR%
  exit /b 1
)

REM --- 3) .env
echo [2/7] Ecriture: %JOB_DIR%\.env
> "%JOB_DIR%\.env" echo JOB_NAME=minimal_csv_demo
if not exist "%JOB_DIR%\.env" (
  echo ERREUR: .env non cree
  exit /b 1
)

REM --- 4) data\input.csv
echo [3/7] Ecriture: %DATA_DIR%\input.csv
> "%DATA_DIR%\input.csv" echo id,customer_id,price,qty
>> "%DATA_DIR%\input.csv" echo 1,100,10,2
>> "%DATA_DIR%\input.csv" echo 2,101,0,5
>> "%DATA_DIR%\input.csv" echo 3,102,7,3
>> "%DATA_DIR%\input.csv" echo 4,103,15,1
>> "%DATA_DIR%\input.csv" echo 5,104,20,4

if not exist "%DATA_DIR%\input.csv" (
  echo ERREUR: input.csv non cree
  exit /b 1
)

REM --- 5) sources.yaml
echo [4/7] Ecriture: %JOB_DIR%\sources.yaml
> "%JOB_DIR%\sources.yaml"  echo version: "1.0"
>> "%JOB_DIR%\sources.yaml" echo.
>> "%JOB_DIR%\sources.yaml" echo sources:
>> "%JOB_DIR%\sources.yaml" echo   source_csv:
>> "%JOB_DIR%\sources.yaml" echo     type: csv
>> "%JOB_DIR%\sources.yaml" echo     extract:
>> "%JOB_DIR%\sources.yaml" echo       table: data/input.csv
>> "%JOB_DIR%\sources.yaml" echo       batch_size: 10

if not exist "%JOB_DIR%\sources.yaml" (
  echo ERREUR: sources.yaml non cree
  exit /b 1
)

REM --- 6) destinations.yaml
echo [5/7] Ecriture: %JOB_DIR%\destinations.yaml
> "%JOB_DIR%\destinations.yaml"  echo version: "1.0"
>> "%JOB_DIR%\destinations.yaml" echo.
>> "%JOB_DIR%\destinations.yaml" echo destinations:
>> "%JOB_DIR%\destinations.yaml" echo   dest_csv:
>> "%JOB_DIR%\destinations.yaml" echo     type: csv
>> "%JOB_DIR%\destinations.yaml" echo     load:
>> "%JOB_DIR%\destinations.yaml" echo       table: data/output.csv
>> "%JOB_DIR%\destinations.yaml" echo       mode: replace

if not exist "%JOB_DIR%\destinations.yaml" (
  echo ERREUR: destinations.yaml non cree
  exit /b 1
)

REM --- 7) transformations.yaml
echo [6/7] Ecriture: %JOB_DIR%\transformations.yaml
> "%JOB_DIR%\transformations.yaml"  echo version: "1.0"
>> "%JOB_DIR%\transformations.yaml" echo.
>> "%JOB_DIR%\transformations.yaml" echo transformations:
>> "%JOB_DIR%\transformations.yaml" echo   steps:
>> "%JOB_DIR%\transformations.yaml" echo     - cast:
>> "%JOB_DIR%\transformations.yaml" echo         mapping:
>> "%JOB_DIR%\transformations.yaml" echo           id: int
>> "%JOB_DIR%\transformations.yaml" echo           customer_id: int
>> "%JOB_DIR%\transformations.yaml" echo           price: float
>> "%JOB_DIR%\transformations.yaml" echo           qty: int
>> "%JOB_DIR%\transformations.yaml" echo     - filter:
>> "%JOB_DIR%\transformations.yaml" echo         expr: "price > 0"
>> "%JOB_DIR%\transformations.yaml" echo     - calculate:
>> "%JOB_DIR%\transformations.yaml" echo         column: total
>> "%JOB_DIR%\transformations.yaml" echo         expr: "price * qty"
>> "%JOB_DIR%\transformations.yaml" echo     - rename:
>> "%JOB_DIR%\transformations.yaml" echo         mapping:
>> "%JOB_DIR%\transformations.yaml" echo           customer_id: client_id

if not exist "%JOB_DIR%\transformations.yaml" (
  echo ERREUR: transformations.yaml non cree
  exit /b 1
)

REM --- 8) pipeline.yaml (ton executor attend from/to)
echo [7/7] Ecriture: %JOB_DIR%\pipeline.yaml
> "%JOB_DIR%\pipeline.yaml"  echo version: "1.0"
>> "%JOB_DIR%\pipeline.yaml" echo.
>> "%JOB_DIR%\pipeline.yaml" echo pipeline:
>> "%JOB_DIR%\pipeline.yaml" echo   from: source_csv
>> "%JOB_DIR%\pipeline.yaml" echo   to: dest_csv

if not exist "%JOB_DIR%\pipeline.yaml" (
  echo ERREUR: pipeline.yaml non cree
  exit /b 1
)

echo.
echo ============================================================
echo OK - Demo creee :
echo   %JOB_DIR%
echo.
echo Verifie les fichiers crees :
echo   %JOB_DIR%\.env
echo   %JOB_DIR%\sources.yaml
echo   %JOB_DIR%\transformations.yaml
echo   %JOB_DIR%\destinations.yaml
echo   %JOB_DIR%\pipeline.yaml
echo   %DATA_DIR%\input.csv
echo.
echo Run (depuis n'importe ou) :
echo   py -m cli.main run examples/minimal_csv
echo ============================================================
pause
exit /b 0
