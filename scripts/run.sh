#!/bin/bash
# Скрипт для запуска VK Ads Manager

# Получаем директорию скрипта и переходим в корень проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
source .venv/bin/activate

case "$1" in
    "main")
        echo "🚀 Запуск основного анализа..."
        python src/main.py
        ;;
    "bot")
        echo "🤖 Запуск Telegram бота..."
        python bot/telegram_bot.py
        ;;
    "scheduler")
        echo "⏰ Запуск планировщика..."
        python scheduler/scheduler_main.py
        ;;
    "status")
        echo "📊 Проверка статуса планировщика..."
        python scheduler/scheduler_main.py --status
        ;;
    *)
        echo "Использование: ./run.sh [main|bot|scheduler|status]"
        echo ""
        echo "Команды:"
        echo "  main      - Запуск основного анализа"
        echo "  bot       - Запуск Telegram бота"  
        echo "  scheduler - Запуск планировщика"
        echo "  status    - Статус планировщика"
        ;;
esac