@echo off
REM ============================================================
REM Reset MongoDB - Run from tests/docker directory
REM ============================================================

echo.
echo ============================================================
echo RESET MONGODB CONTAINER
echo ============================================================
echo.

echo [1/4] Stopping MongoDB...
docker-compose -f docker-compose.test.yml down mongodb 2>nul

echo [2/4] Removing volumes...
docker volume rm hydra_mongodb_data 2>nul
docker volume prune -f 2>nul

echo [3/4] Starting fresh MongoDB...
docker-compose -f docker-compose.test.yml up -d mongodb

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start MongoDB
    pause
    exit /b 1
)

echo [4/4] Waiting 15 seconds for initialization...
timeout /t 15 /nobreak > nul

echo.
echo ============================================================
echo VERIFYING DATA
echo ============================================================

docker exec hydra_test_mongodb mongosh -u hydra_app -p hydra_app_pwd hydra_test_db --quiet --eval "print('users_flat: ' + db.users_flat.countDocuments()); print('orders_nested: ' + db.orders_nested.countDocuments()); print('products_mixed: ' + db.products_mixed.countDocuments()); print('events_evolving: ' + db.events_evolving.countDocuments()); print('analytics_arrays: ' + db.analytics_arrays.countDocuments());"

echo.
echo ============================================================
echo ✅ MongoDB Ready!
echo ============================================================