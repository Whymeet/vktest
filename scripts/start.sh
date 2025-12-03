#!/bin/bash
# Запуск планировщика и Telegram бота в фоне

# Получаем директорию скрипта и переходим в корень проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Активируем виртуальное окружение
source .venv/bin/activate

# Останавливаем старые процессы если есть
pkill -f "python.*scheduler_main.py"
pkill -f "python.*telegram_bot.py"

echo "🚀 Запуск VK Ads Manager..."

# Запускаем планировщик в фоне
nohup python scheduler/scheduler_main.py > scheduler.log 2>&1 &
SCHEDULER_PID=$!
echo "⏰ Планировщик запущен (PID: $SCHEDULER_PID)"

# Ждем 2 секунды
sleep 2

# Запускаем Telegram бота в фоне
nohup python bot/telegram_bot.py > telegram_bot.log 2>&1 &
BOT_PID=$!
echo "🤖 Telegram бот запущен (PID: $BOT_PID)"

# Сохраняем PID'ы для остановки
echo $SCHEDULER_PID > scheduler.pid
echo $BOT_PID > telegram_bot.pid

echo ""
echo "✅ Все процессы запущены!"
echo ""
echo "📊 Проверка процессов:"
ps aux | grep -E "scheduler_main|telegram_bot" | grep -v grep
echo ""
echo "📝 Логи:"
echo "  Планировщик: tail -f scheduler.log"
echo "  Telegram бот: tail -f telegram_bot.log"
echo ""
echo "⏹️  Для остановки: ./stop.sh"
