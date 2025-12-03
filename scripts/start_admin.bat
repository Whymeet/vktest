@echo off
chcp 65001 >nul
echo ========================================
echo 🚀 VK Ads Manager - Админ Панель
echo ========================================
echo.
echo Проверка зависимостей...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Flask не установлен. Устанавливаю зависимости...
    pip install -r requirements_admin.txt
) else (
    echo ✅ Flask установлен
)
echo.
echo Запуск админ-панели...
echo.
python admin_panel.py
pause
