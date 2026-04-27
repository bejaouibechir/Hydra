@echo off
setlocal

REM ============================================================
REM Hydra MVP - Job end-to-end CSV -> CSV
REM Emplacement final : D:\job_minimal_ok
REM ============================================================

set JOB_DIR=D:\job_minimal_ok

echo [0/6] Nettoyage si le job existe déjà...
if exist "%JOB_DIR%" (
  rmdir /S /Q "%JOB_DIR%"
)

echo [1/6] Création du dossier job...
mkdir "%JOB_DIR%"

REM ------------------------------------------------------------
REM .env du job
REM ------------------------------------------------------------
echo [2/6] Création du fichier .env
(
echo JOB_NAME=job_minimal_ok
) > "%JOB_DIR%\.env"

REM ------------------------------------------------------------
REM CSV source (input.csv)
REM ------------------------------------------------------------
echo [3/6] Création du CSV source
(
echo id,customer_id,price,qty
echo 1,100,10,2
echo 2,101,
