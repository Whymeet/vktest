#!/bin/bash
# ==============================================
# Update to SSL Configuration
# ==============================================
# Run this after SSL certificate is obtained
# ==============================================

set -e

echo "==========================================="
echo "Updating to SSL configuration..."
echo "==========================================="

# Stop current containers
echo "[1/3] Stopping containers..."
docker compose down

# Copy SSL config to active config
echo "[2/3] Activating SSL configuration..."
cp nginx/conf.d/default.conf.ssl nginx/conf.d/default.conf

# Restart with SSL
echo "[3/3] Starting with SSL..."
docker compose up -d

echo "==========================================="
echo "✅ SSL configuration activated!"
echo "Site: https://kybyshka-dev.ru"
echo "==========================================="
