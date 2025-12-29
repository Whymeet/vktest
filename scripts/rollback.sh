#!/bin/bash
set -e

# Скрипт для отката к предыдущей версии
# Использование: ./scripts/rollback.sh

PROJECT_DIR="/srv/vk-ads-parser/vktest"
BACKUP_COMMIT_FILE=".previous_commit"

echo "=== Starting rollback ==="

cd "$PROJECT_DIR"

if [ ! -f "$BACKUP_COMMIT_FILE" ]; then
    echo "Error: No previous commit file found!"
    exit 1
fi

PREVIOUS_COMMIT=$(cat "$BACKUP_COMMIT_FILE")
echo "Rolling back to: $PREVIOUS_COMMIT"

git reset --hard "$PREVIOUS_COMMIT"

echo "Rebuilding containers..."
docker compose down
docker compose up -d --build

echo "Waiting for services to start..."
sleep 30

if curl -sf http://localhost:8000/api/health > /dev/null; then
    echo "=== Rollback successful! ==="
else
    echo "=== Warning: Health check failed after rollback ==="
    exit 1
fi
