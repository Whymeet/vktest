#!/bin/bash
# ==============================================
# Скрипт быстрого запуска в production
# ==============================================

set -e

echo "=========================================="
echo "VK Ads Manager - Production Setup"
echo "Domain: kybyshka-dev.ru"
echo "=========================================="

# Проверка .env файла
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found!"
    echo "Please create .env file from .env.production"
    echo "Run: cp .env.production .env"
    exit 1
fi

echo "✅ .env file found"

# Создать необходимые директории
echo "📁 Creating directories..."
mkdir -p logs certbot/conf certbot/www nginx/conf.d

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo "Install with: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

echo "✅ Docker is installed"

# Остановить старые контейнеры если есть
echo "🛑 Stopping old containers..."
docker compose down 2>/dev/null || true

# Запуск контейнеров
echo "🚀 Building and starting containers..."
docker compose up -d --build

# Ожидание запуска
echo "⏳ Waiting for services to start..."
sleep 10

# Проверка статуса
echo ""
echo "=========================================="
echo "Container Status:"
echo "=========================================="
docker compose ps

echo ""
echo "=========================================="
echo "✅ Services started!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Check HTTP: http://45.129.2.158:3000"
echo "2. Setup DNS: kybyshka-dev.ru -> 45.129.2.158"
echo "3. Get SSL: ./init-ssl.sh"
echo ""
echo "View logs:"
echo "  docker compose logs -f backend"
echo "  docker compose logs -f frontend"
echo ""
