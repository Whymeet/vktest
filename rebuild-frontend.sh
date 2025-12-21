#!/bin/bash
# ==============================================
# Rebuild Frontend with Production Config
# ==============================================

set -e

echo "==========================================="
echo "Rebuilding frontend..."
echo "==========================================="

# Rebuild only frontend container
docker compose build frontend

# Restart frontend and nginx
docker compose restart frontend nginx

echo "==========================================="
echo "Frontend rebuilt successfully!"
echo "==========================================="

# Show status
docker compose ps
