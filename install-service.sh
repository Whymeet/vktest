#!/bin/bash
# Установка VK Ads Manager как системных сервисов

echo "🚀 Установка VK Ads Manager на сервер..."
echo ""

# Останавливаем текущие процессы
echo "⏹️  Остановка текущих процессов..."
./stop.sh 2>/dev/null

# Копируем сервисные файлы
echo "📝 Копирование сервисных файлов..."
sudo cp vk-ads-scheduler.service /etc/systemd/system/
sudo cp vk-ads-telegram-bot.service /etc/systemd/system/

# Перезагружаем systemd
echo "🔄 Перезагрузка systemd..."
sudo systemctl daemon-reload

# Включаем автозапуск
echo "✅ Включение автозапуска..."
sudo systemctl enable vk-ads-scheduler.service
sudo systemctl enable vk-ads-telegram-bot.service

# Запускаем сервисы
echo "▶️  Запуск сервисов..."
sudo systemctl start vk-ads-scheduler.service
sudo systemctl start vk-ads-telegram-bot.service

# Ждем 3 секунды
sleep 3

# Проверяем статус
echo ""
echo "📊 Статус сервисов:"
echo "===================="
sudo systemctl status vk-ads-scheduler.service --no-pager -l
echo ""
sudo systemctl status vk-ads-telegram-bot.service --no-pager -l

echo ""
echo "✅ Установка завершена!"
echo ""
echo "📝 Полезные команды:"
echo "  sudo systemctl status vk-ads-scheduler    - статус планировщика"
echo "  sudo systemctl status vk-ads-telegram-bot - статус бота"
echo "  sudo systemctl restart vk-ads-scheduler   - перезапуск планировщика"
echo "  sudo systemctl restart vk-ads-telegram-bot - перезапуск бота"
echo "  sudo systemctl stop vk-ads-scheduler      - остановка планировщика"
echo "  sudo systemctl stop vk-ads-telegram-bot   - остановка бота"
echo "  journalctl -u vk-ads-scheduler -f         - логи планировщика"
echo "  journalctl -u vk-ads-telegram-bot -f      - логи бота"
