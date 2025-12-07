@echo off
chcp 65001 > nul
echo ================================
echo Остановка VK Ads Manager
echo ================================
echo.

echo Остановка backend (порт 8000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
)

echo Остановка frontend (порт 5173)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
)

echo.
echo ================================
echo Все процессы остановлены
echo ================================
pause
