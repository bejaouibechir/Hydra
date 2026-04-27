@echo off
setlocal EnableExtensions

rem ============================================================
rem Génère des mocks Hydra DSL (fixtures) pour les tests.
rem
rem Usage :
rem   1) Ouvre un terminal dans : tests\fixtures\dsl_cases
rem   2) Exécute : generate_dsl_cases.bat
rem
rem Résultat :
rem   Crée 3 dossiers de cas :
rem     - ok_minimal_01
rem     - ko_unknown_source_01
rem     - ko_missing_env_01
rem   Et génère 4 fichiers YAML par cas :
rem     sources.yaml / destinations.yaml / pipeline.yaml / transformations.yaml
rem
rem Notes :
rem - Le script n'écrase pas un cas existant (il le laisse intact).
rem - Tu peux dupliquer un dossier et modifier les YAML pour créer un nouveau cas.
rem ============================================================

set "BASE=%CD%"

call :MakeCase "ok_minimal_01"
call :WriteOkMinimal "%BASE%\ok_minimal_01"

call :MakeCase "ko_unknown_source_01"
call :WriteKoUnknownSource "%BASE%\ko_unknown_source_01"

call :MakeCase "ko_missing_env_01"
call :WriteKoMissingEnv "%BASE%\ko_missing_env_01"

echo.
echo OK - Fixtures Hydra DSL generees dans :
echo   %BASE%
echo.
echo Tu peux maintenant lancer tes tests depuis la racine du projet :
echo   pytest -v
echo.
exit /b 0


rem -----------------------------
rem Crée le dossier de cas si absent
rem -----------------------------
:MakeCase
set "CASE=%~1"
if exist "%CASE%\" (
  echo [SKIP] %CASE% existe deja.
) else (
  echo [MKDIR] %CASE%
  mkdir "%CASE%" >nul
)
exit /b 0


rem -----------------------------
rem Ecrit le cas OK minimal
rem -----------------------------
:WriteOkMinimal
set "DIR=%~1"

rem sources.yaml
if not exist "%DIR%\sources.yaml" (
  > "%DIR%\sources.yaml" (
    echo sources:
    echo ^  src_orders:
    echo ^    type: mysql
    echo ^    connection:
    echo ^      host: ${ENV:DB_HOST}
    echo ^      user: etl
    echo ^      password: ${SECRET:db.password}
    echo ^      database: shop
    echo ^      port: 3306
    echo ^    extract:
    echo ^      table: orders
    echo ^      batch_size: 1000
  )
) else (
  echo [SKIP] ok_minimal_01\sources.yaml existe deja.
)

rem destinations.yaml
if not exist "%DIR%\destinations.yaml" (
  > "%DIR%\destinations.yaml" (
    echo destinations:
    echo ^  dest_dwh:
    echo ^    type: mariadb
    echo ^    connection:
    echo ^      host: ${ENV:DB_HOST}
    echo ^      user: etl
    echo ^      password: ${SECRET:db.password}
    echo ^      database: dwh
    echo ^      port: 3306
    echo ^    load:
    echo ^      table: orders_dwh
    echo ^      mode: append
    echo ^      batch_size: 1000
  )
) else (
  echo [SKIP] ok_minimal_01\destinations.yaml existe deja.
)

rem pipeline.yaml
if not exist "%DIR%\pipeline.yaml" (
  > "%DIR%\pipeline.yaml" (
    echo pipeline:
    echo ^  from: src_orders
    echo ^  to: dest_dwh
  )
) else (
  echo [SKIP] ok_minimal_01\pipeline.yaml existe deja.
)

rem transformations.yaml
if not exist "%DIR%\transformations.yaml" (
  > "%DIR%\transformations.yaml" (
    echo steps:
    echo ^  - select:
    echo ^      columns: ["id", "customer_id", "price", "qty"]
    echo ^  - filter:
    echo ^      expr: "price ^> 0"
    echo ^  - calculate:
    echo ^      column: "total"
    echo ^      expr: "price * qty"
    echo ^  - rename:
    echo ^      mapping:
    echo ^        customer_id: client_id
    echo ^  - cast:
    echo ^      mapping:
    echo ^        id: int
    echo ^        total: float
  )
) else (
  echo [SKIP] ok_minimal_01\transformations.yaml existe deja.
)

exit /b 0


rem -----------------------------
rem Ecrit le cas KO : source inconnue dans pipeline
rem -----------------------------
:WriteKoUnknownSource
set "DIR=%~1"

rem sources.yaml
if not exist "%DIR%\sources.yaml" (
  > "%DIR%\sources.yaml" (
    echo sources:
    echo ^  src_ok:
    echo ^    type: mysql
    echo ^    connection:
    echo ^      host: ${ENV:DB_HOST}
    echo ^    extract:
    echo ^      table: t
    echo ^      batch_size: 1000
  )
) else (
  echo [SKIP] ko_unknown_source_01\sources.yaml existe deja.
)

rem destinations.yaml
if not exist "%DIR%\destinations.yaml" (
  > "%DIR%\destinations.yaml" (
    echo destinations:
    echo ^  dest_ok:
    echo ^    type: mariadb
    echo ^    connection:
    echo ^      host: ${ENV:DB_HOST}
    echo ^    load:
    echo ^      table: t2
    echo ^      mode: append
    echo ^      batch_size: 1000
  )
) else (
  echo [SKIP] ko_unknown_source_01\destinations.yaml existe deja.
)

rem pipeline.yaml
if not exist "%DIR%\pipeline.yaml" (
  > "%DIR%\pipeline.yaml" (
    echo pipeline:
    echo ^  from: src_INCONNUE
    echo ^  to: dest_ok
  )
) else (
  echo [SKIP] ko_unknown_source_01\pipeline.yaml existe deja.
)

rem transformations.yaml
if not exist "%DIR%\transformations.yaml" (
  > "%DIR%\transformations.yaml" (
    echo steps:
    echo ^  - filter:
    echo ^      expr: "id ^> 0"
  )
) else (
  echo [SKIP] ko_unknown_source_01\transformations.yaml existe deja.
)

exit /b 0


rem -----------------------------
rem Ecrit le cas KO : ENV manquant
rem -----------------------------
:WriteKoMissingEnv
set "DIR=%~1"

rem sources.yaml
if not exist "%DIR%\sources.yaml" (
  > "%DIR%\sources.yaml" (
    echo sources:
    echo ^  src_orders:
    echo ^    type: mysql
    echo ^    connection:
    echo ^      host: ${ENV:DB_HOST_MISSING}
    echo ^    extract:
    echo ^      table: orders
    echo ^      batch_size: 1000
  )
) else (
  echo [SKIP] ko_missing_env_01\sources.yaml existe deja.
)

rem destinations.yaml
if not exist "%DIR%\destinations.yaml" (
  > "%DIR%\destinations.yaml" (
    echo destinations:
    echo ^  dest_dwh:
    echo ^    type: mariadb
    echo ^    connection:
    echo ^      host: localhost
    echo ^    load:
    echo ^      table: orders_dwh
    echo ^      mode: append
    echo ^      batch_size: 1000
  )
) else (
  echo [SKIP] ko_missing_env_01\destinations.yaml existe deja.
)

rem pipeline.yaml
if not exist "%DIR%\pipeline.yaml" (
  > "%DIR%\pipeline.yaml" (
    echo pipeline:
    echo ^  from: src_orders
    echo ^  to: dest_dwh
  )
) else (
  echo [SKIP] ko_missing_env_01\pipeline.yaml existe deja.
)

rem transformations.yaml
if not exist "%DIR%\transformations.yaml" (
  > "%DIR%\transformations.yaml" (
    echo steps:
    echo ^  - select:
    echo ^      columns: ["id"]
  )
) else (
  echo [SKIP] ko_missing_env_01\transformations.yaml existe deja.
)

exit /b 0
