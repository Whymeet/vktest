# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Копирование package.json
COPY package*.json ./

# Установка зависимостей
RUN npm ci

# Копирование исходников
COPY . .

# Set production API URL
ENV VITE_API_URL=/api

# Сборка
RUN npm run build

# Production stage - nginx для статики
FROM nginx:alpine

# Копирование собранного приложения
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx конфиг для SPA
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
