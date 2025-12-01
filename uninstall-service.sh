#!/bin/bash
# Удаление VK Ads Manager сервисов

echo "⏹️  Удаление VK Ads Manager сервисов..."
echo ""

# Останавливаем сервисы
echo "🛑 Остановка сервисов..."
sudo systemctl stop vk-ads-scheduler.service
sudo systemctl stop vk-ads-telegram-bot.service

# Отключаем автозапуск
echo "❌ Отключение автозапуска..."
sudo systemctl disable vk-ads-scheduler.service
sudo systemctl disable vk-ads-telegram-bot.service

# Удаляем файлы сервисов
echo "🗑️  Удаление файлов сервисов..."
sudo rm /etc/systemd/system/vk-ads-scheduler.service
sudo rm /etc/systemd/system/vk-ads-telegram-bot.service

# Перезагружаем systemd
echo "🔄 Перезагрузка systemd..."
sudo systemctl daemon-reload

echo ""
echo "✅ Сервисы удалены!"
