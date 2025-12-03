#!/bin/bash
# Остановка всех процессов VK Ads Manager

# Получаем директорию скрипта и переходим в корень проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "⏹️  Остановка процессов..."

# Останавливаем по PID файлам если есть
if [ -f scheduler.pid ]; then
    SCHEDULER_PID=$(cat scheduler.pid)
    kill $SCHEDULER_PID 2>/dev/null && echo "⏰ Планировщик остановлен (PID: $SCHEDULER_PID)"
    rm scheduler.pid
fi

if [ -f telegram_bot.pid ]; then
    BOT_PID=$(cat telegram_bot.pid)
    kill $BOT_PID 2>/dev/null && echo "🤖 Telegram бот остановлен (PID: $BOT_PID)"
    rm telegram_bot.pid
fi

# Убиваем по имени процесса (на всякий случай)
pkill -f "python.*scheduler_main.py" && echo "⏰ Планировщик остановлен (по имени)"
pkill -f "python.*telegram_bot.py" && echo "🤖 Telegram бот остановлен (по имени)"

echo ""
echo "✅ Все процессы остановлены"
