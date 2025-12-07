@echo off
chcp 65001 > nul
echo ================================
echo VK Ads Manager - Web Interface
echo ================================
echo.

:: Start backend
echo Starting backend API server...
cd /d "%~dp0backend\api"
start "VK Ads Backend" cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

:: Wait for backend to start
timeout /t 3 /nobreak > nul

:: Start frontend
echo Starting frontend dev server...
cd /d "%~dp0frontend"
start "VK Ads Frontend" cmd /k "npm run dev"

echo.
echo ================================
echo Servers starting...
echo Backend API:  http://localhost:8000
echo Frontend:     http://localhost:5173
echo API Docs:     http://localhost:8000/docs
echo ================================
echo.
echo Press any key to open the web interface...
pause > nul
start http://localhost:5173
