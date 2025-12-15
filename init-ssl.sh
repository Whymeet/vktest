#!/bin/bash
# ==============================================
# SSL Certificate Initialization Script
# ==============================================
# This script obtains Let's Encrypt SSL certificates
# Run this ONCE on first deployment
# ==============================================

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check required variables
if [ -z "$DOMAIN" ] || [ -z "$CERTBOT_EMAIL" ]; then
    echo "ERROR: DOMAIN and CERTBOT_EMAIL must be set in .env file"
    exit 1
fi

echo "==================================="
echo "SSL Certificate Initialization"
echo "Domain: $DOMAIN"
echo "Email: $CERTBOT_EMAIL"
echo "==================================="

# Create required directories
mkdir -p certbot/conf certbot/www

# Step 1: Use initial nginx config (HTTP only)
echo "[1/4] Setting up initial nginx config..."
cp nginx/conf.d/default.conf.initial nginx/conf.d/default.conf

# Step 2: Start nginx with HTTP only (frontend builds inside Docker)
echo "[2/4] Starting nginx..."
docker compose -f docker-compose.prod.yml up -d nginx backend

# Wait for nginx to start
sleep 5

# Step 3: Get SSL certificate
echo "[3/4] Obtaining SSL certificate..."
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email $CERTBOT_EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN

# Step 4: Switch to SSL config
echo "[4/4] Switching to SSL configuration..."

# Create SSL config from template
cat > nginx/conf.d/default.conf << EOF
# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://backend:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/auth/ {
        limit_req zone=login_limit burst=5 nodelay;
        proxy_pass http://backend:8000/api/auth/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/health {
        proxy_pass http://backend:8000/api/health;
    }
}
EOF

# Restart nginx with SSL
docker compose -f docker-compose.prod.yml restart nginx

echo "==================================="
echo "SSL Certificate obtained successfully!"
echo "Your site is now available at: https://$DOMAIN"
echo "==================================="
