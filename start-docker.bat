@echo off
echo ========================================
echo VK Ads Manager - Docker Start
echo ========================================
echo.

echo Stopping old containers...
docker-compose down

echo.
echo Building and starting services...
docker-compose up --build -d

echo.
echo Waiting for services to start...
timeout /t 10 /nobreak

echo.
echo ========================================
echo Services started!
echo ========================================
echo Frontend: http://localhost:3000
echo Backend API: http://localhost:8000
echo PostgreSQL: localhost:5432
echo.
echo To view logs: docker-compose logs -f
echo To stop: docker-compose down
echo ========================================
