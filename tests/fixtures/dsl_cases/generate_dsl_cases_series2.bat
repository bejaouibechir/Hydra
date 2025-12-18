@echo off
setlocal EnableExtensions

rem ============================================================
rem Génère une SERIE 2 de cas DSL (stress tests) :
rem - cas OK et KO très diversifiés
rem - toujours dans le périmètre : select/filter/calculate/rename/cast
rem - pipeline wiring minimal (from/to)
rem
rem Usage :
rem   - Ouvre un terminal dans : tests\fixtures\dsl_cases
rem   - Exécute : generate_dsl_cases_series2.bat
rem
rem Résultat :
rem   Crée un dossier "series2" avec plusieurs cas.
rem ============================================================

set "BASE=%CD%\series2"

if not exist "%BASE%\" (
  echo [MKDIR] %BASE%
  mkdir "%BASE%" >nul
) else (
  echo [INFO] series2 existe deja : %BASE%
)

rem ---------------- OK CASES ----------------
call :MakeCase "ok_select_dedup_trim_01"
call :WriteCommonOk "%BASE%\ok_select_dedup_trim_01" "src_orders" "dest_dwh"
call :WriteTransform_ok_select_dedup_trim "%BASE%\ok_select_dedup_trim_01"

call :MakeCase "ok_rename_chain_01"
call :WriteCommonOk "%BASE%\ok_rename_chain_01" "src_orders" "dest_dwh"
call :WriteTransform_ok_rename_chain "%BASE%\ok_rename_chain_01"

call :MakeCase "ok_cast_mixed_types_01"
call :WriteCommonOk "%BASE%\ok_cast_mixed_types_01" "src_orders" "dest_dwh"
call :WriteTransform_ok_cast_mixed "%BASE%\ok_cast_mixed_types_01"

call :MakeCase "ok_filter_with_complex_expr_01"
call :WriteCommonOk "%BASE%\ok_filter_with_complex_expr_01" "src_orders" "dest_dwh"
call :WriteTransform_ok_filter_complex "%BASE%\ok_filter_with_complex_expr_01"

call :MakeCase "ok_calculate_complex_expr_01"
call :WriteCommonOk "%BASE%\ok_calculate_complex_expr_01" "src_orders" "dest_dwh"
call :WriteTransform_ok_calculate_complex "%BASE%\ok_calculate_complex_expr_01"

rem ---------------- KO CASES (Transform) ----------------
call :MakeCase "ko_step_two_ops_01"
call :WriteCommonOk "%BASE%\ko_step_two_ops_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_two_ops "%BASE%\ko_step_two_ops_01"

call :MakeCase "ko_unknown_op_01"
call :WriteCommonOk "%BASE%\ko_unknown_op_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_unknown_op "%BASE%\ko_unknown_op_01"

call :MakeCase "ko_params_not_dict_01"
call :WriteCommonOk "%BASE%\ko_params_not_dict_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_params_not_dict "%BASE%\ko_params_not_dict_01"

call :MakeCase "ko_select_empty_column_01"
call :WriteCommonOk "%BASE%\ko_select_empty_column_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_select_empty_col "%BASE%\ko_select_empty_column_01"

call :MakeCase "ko_filter_blank_expr_01"
call :WriteCommonOk "%BASE%\ko_filter_blank_expr_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_filter_blank "%BASE%\ko_filter_blank_expr_01"

call :MakeCase "ko_calculate_missing_expr_01"
call :WriteCommonOk "%BASE%\ko_calculate_missing_expr_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_calculate_missing_expr "%BASE%\ko_calculate_missing_expr_01"

call :MakeCase "ko_rename_empty_key_value_01"
call :WriteCommonOk "%BASE%\ko_rename_empty_key_value_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_rename_empty "%BASE%\ko_rename_empty_key_value_01"

call :MakeCase "ko_cast_invalid_type_01"
call :WriteCommonOk "%BASE%\ko_cast_invalid_type_01" "src_orders" "dest_dwh"
call :WriteTransform_ko_cast_invalid "%BASE%\ko_cast_invalid_type_01"

rem ---------------- KO CASE (Pipeline wiring) ----------------
call :MakeCase "ko_pipeline_unknown_destination_01"
call :WriteCommonOk "%BASE%\ko_pipeline_unknown_destination_01" "src_orders" "dest_dwh"
call :WritePipeline_unknown_destination "%BASE%\ko_pipeline_unknown_destination_01"
call :WriteTransform_ok_select_dedup_trim "%BASE%\ko_pipeline_unknown_destination_01"

echo.
echo OK - Serie2 generee sous :
echo   %BASE%
echo.
exit /b 0


rem ============================================================
rem Helpers
rem ============================================================

:MakeCase
set "CASE=%~1"
if exist "%BASE%\%CASE%\" (
  echo [SKIP] series2\%CASE% existe deja.
) else (
  echo [MKDIR] series2\%CASE%
  mkdir "%BASE%\%CASE%" >nul
)
exit /b 0


:WriteCommonOk
set "DIR=%~1"
set "SRCNAME=%~2"
set "DSTNAME=%~3"

rem sources.yaml
if not exist "%DIR%\sources.yaml" (
  > "%DIR%\sources.yaml" (
    echo sources:
    echo ^  %SRCNAME%:
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
)

rem destinations.yaml
if not exist "%DIR%\destinations.yaml" (
  > "%DIR%\destinations.yaml" (
    echo destinations:
    echo ^  %DSTNAME%:
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
)

rem pipeline.yaml (par défaut OK)
if not exist "%DIR%\pipeline.yaml" (
  > "%DIR%\pipeline.yaml" (
    echo pipeline:
    echo ^  from: %SRCNAME%
    echo ^  to: %DSTNAME%
  )
)

exit /b 0


rem ---------------- Transform OK ----------------

:WriteTransform_ok_select_dedup_trim
set "DIR=%~1"
if not exist "%DIR%\transformations.yaml" (
  > "%DIR%\transformations.yaml" (
    echo steps:
    echo ^  - select:
    echo ^      columns: [" id ", "name", "name", "  price", "qty  "]
  )
)
exit /b 0

:WriteTransform_ok_rename_chain
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - rename:
  echo ^      mapping:
  echo ^        customer_id: client_id
  echo ^        created_at: createdOn
  echo ^        updated_at: updatedOn
  echo ^  - rename:
  echo ^      mapping:
  echo ^        client_id: customerKey
)
exit /b 0

:WriteTransform_ok_cast_mixed
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - cast:
  echo ^      mapping:
  echo ^        id: int
  echo ^        price: float
  echo ^        active: bool
  echo ^        created_at: datetime
  echo ^        birth_date: date
  echo ^        comment: str
)
exit /b 0

:WriteTransform_ok_filter_complex
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - filter:
  echo ^      expr: "price ^> 0 AND (qty ^>= 1 OR promo = 'YES') AND country IN ('TN','FR')"
)
exit /b 0

:WriteTransform_ok_calculate_complex
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - calculate:
  echo ^      column: "total"
  echo ^      expr: "(price * qty) - (discount ?? 0)"
  echo ^  - calculate:
  echo ^      column: "label"
  echo ^      expr: "concat('ORD-', cast(id as str))"
)
exit /b 0


rem ---------------- Transform KO ----------------

:WriteTransform_ko_two_ops
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - select:
  echo ^      columns: ["id"]
  echo ^    filter:
  echo ^      expr: "id ^> 0"
)
exit /b 0

:WriteTransform_ko_unknown_op
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - aggregate:
  echo ^      by: ["id"]
)
exit /b 0

:WriteTransform_ko_params_not_dict
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - filter: "id ^> 0"
)
exit /b 0

:WriteTransform_ko_select_empty_col
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - select:
  echo ^      columns: ["id", "   ", "name"]
)
exit /b 0

:WriteTransform_ko_filter_blank
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - filter:
  echo ^      expr: "   "
)
exit /b 0

:WriteTransform_ko_calculate_missing_expr
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - calculate:
  echo ^      column: "total"
)
exit /b 0

:WriteTransform_ko_rename_empty
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - rename:
  echo ^      mapping:
  echo ^        "": newName
  echo ^        oldName: ""
)
exit /b 0

:WriteTransform_ko_cast_invalid
set "DIR=%~1"
> "%DIR%\transformations.yaml" (
  echo steps:
  echo ^  - cast:
  echo ^      mapping:
  echo ^        id: uuid
)
exit /b 0


rem ---------------- Pipeline KO ----------------

:WritePipeline_unknown_destination
set "DIR=%~1"
> "%DIR%\pipeline.yaml" (
  echo pipeline:
  echo ^  from: src_orders
  echo ^  to: dest_INCONNUE
)
exit /b 0
