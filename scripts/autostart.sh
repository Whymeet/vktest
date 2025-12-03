#!/bin/bash
# Скрипт автозапуска VK Ads Manager при загрузке сервера

# Получаем директорию скрипта и переходим в корень проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
source .venv/bin/activate

# Ждем 30 секунд после загрузки системы
sleep 30

# Запускаем планировщик и бота
./scripts/start.sh

# Логируем запуск
echo "$(date): VK Ads Manager автозапуск выполнен" >> autostart.log