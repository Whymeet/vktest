@echo off
echo 📊 Проверка структуры VK Ads Manager
echo ====================================
echo.

echo ✅ Основные директории:
if exist "bot" echo    ✓ bot/ - Telegram бот
if exist "cfg" echo    ✓ cfg/ - Конфигурация  
if exist "scheduler" echo    ✓ scheduler/ - Планировщик
if exist "scripts" echo    ✓ scripts/ - Скрипты управления
if exist "src" echo    ✓ src/ - Основной код
if exist "utils" echo    ✓ utils/ - Утилиты
if exist "web" echo    ✓ web/ - Веб-интерфейс

echo.
echo ✅ Основные файлы:
if exist "bot\telegram_bot.py" echo    ✓ bot\telegram_bot.py - Telegram бот
if exist "src\main.py" echo    ✓ src\main.py - Основное приложение  
if exist "web\admin_panel.py" echo    ✓ web\admin_panel.py - Админ панель
if exist "scheduler\scheduler_main.py" echo    ✓ scheduler\scheduler_main.py - Планировщик
if exist "utils\vk_api.py" echo    ✓ utils\vk_api.py - VK API
if exist "utils\config.py" echo    ✓ utils\config.py - Конфигурация
if exist "utils\logging_setup.py" echo    ✓ utils\logging_setup.py - Логирование

echo.
echo ✅ Скрипты управления:
if exist "scripts\start.sh" echo    ✓ scripts\start.sh - Запуск (Linux)
if exist "scripts\stop.sh" echo    ✓ scripts\stop.sh - Остановка (Linux)  
if exist "scripts\status.sh" echo    ✓ scripts\status.sh - Статус (Linux)
if exist "scripts\start_admin.bat" echo    ✓ scripts\start_admin.bat - Админ панель (Windows)

echo.
echo 🎉 Структура проекта успешно организована!
echo.
pause