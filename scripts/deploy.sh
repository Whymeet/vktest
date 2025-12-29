#!/bin/bash
set -e

# Скрипт для деплоя на сервере
# Использование: ./scripts/deploy.sh

PROJECT_DIR="/srv/vk-ads-parser/vktest"
BACKUP_COMMIT_FILE=".previous_commit"

echo "=== Starting deployment ==="

cd "$PROJECT_DIR"

# Сохраняем текущий коммит для возможности отката
git rev-parse HEAD > "$BACKUP_COMMIT_FILE"
echo "Current commit saved: $(cat $BACKUP_COMMIT_FILE)"

# Получаем последние изменения
echo "Fetching latest changes..."
git fetch origin main
git reset --hard origin/main

echo "Latest commit: $(git rev-parse HEAD)"

# Останавливаем и пересобираем контейнеры
echo "Rebuilding containers..."
docker compose down
docker compose up -d --build

# Ждем пока сервисы поднимутся
echo "Waiting for services to start..."
sleep 30

# Проверяем здоровье бэкенда
echo "Running health check..."
if curl -sf http://localhost:8000/api/health > /dev/null; then
    echo "=== Deployment successful! ==="
else
    echo "=== Health check failed! Rolling back... ==="
    git reset --hard "$(cat $BACKUP_COMMIT_FILE)"
    docker compose down
    docker compose up -d --build
    echo "Rolled back to: $(cat $BACKUP_COMMIT_FILE)"
    exit 1
fi
