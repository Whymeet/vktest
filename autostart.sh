#!/bin/bash
# Скрипт автозапуска VK Ads Manager при загрузке сервера

cd /home/trouble/dev/vktest
source .venv/bin/activate

# Ждем 30 секунд после загрузки системы
sleep 30

# Запускаем планировщик и бота
./start.sh

# Логируем запуск
echo "$(date): VK Ads Manager автозапуск выполнен" >> autostart.log