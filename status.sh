#!/bin/bash
# Проверка статуса процессов VK Ads Manager

cd /home/trouble/dev/vktest

echo "📊 Статус процессов VK Ads Manager"
echo "=================================="
echo ""

# Проверяем планировщик
if pgrep -f "python.*scheduler_main.py" > /dev/null; then
    echo "✅ Планировщик: РАБОТАЕТ"
    ps aux | grep "scheduler_main.py" | grep -v grep | awk '{print "   PID: "$2" | Время: "$9" | CPU: "$3"% | RAM: "$4"%"}'
else
    echo "❌ Планировщик: ОСТАНОВЛЕН"
fi

echo ""

# Проверяем Telegram бота
if pgrep -f "python.*telegram_bot.py" > /dev/null; then
    echo "✅ Telegram бот: РАБОТАЕТ"
    ps aux | grep "telegram_bot.py" | grep -v grep | awk '{print "   PID: "$2" | Время: "$9" | CPU: "$3"% | RAM: "$4"%"}'
else
    echo "❌ Telegram бот: ОСТАНОВЛЕН"
fi

echo ""
echo "📝 Последние строки логов:"
echo ""

if [ -f scheduler.log ]; then
    echo "⏰ Планировщик (последние 5 строк):"
    tail -5 scheduler.log | sed 's/^/   /'
    echo ""
fi

if [ -f telegram_bot.log ]; then
    echo "🤖 Telegram бот (последние 5 строк):"
    tail -5 telegram_bot.log | sed 's/^/   /'
fi
