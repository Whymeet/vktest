# Инструкция по деплою на сервер
**Домен:** https://kybyshka-dev.ru/
**IP:** 45.129.2.158

## Шаг 1: Подготовка сервера (через SSH)

```bash
# Подключиться по SSH
ssh root@45.129.2.158

# Установить Docker (если еще не установлен)
curl -fsSL https://get.docker.com | sh

# Проверить установку
docker --version
docker-compose --version
```

## Шаг 2: Перейти в директорию проекта

```bash
# Перейти в папку с проектом
cd /root/vktest2  # или где вы склонировали
```

## Шаг 3: Загрузить файл .env через WinSCP

**Файл для загрузки:** `.env.production`
**Куда загрузить:** `/root/vktest2/.env`
(переименовать `.env.production` → `.env`)

**ИЛИ создать через SSH:**
```bash
nano .env
# Скопировать содержимое из .env.production и вставить
# Ctrl+O (сохранить), Ctrl+X (выйти)
```

## Шаг 4: Создать необходимые директории

```bash
mkdir -p logs certbot/conf certbot/www nginx/conf.d
```

## Шаг 5: Запустить контейнеры (БЕЗ SSL сначала)

```bash
# Собрать и запустить
docker-compose up -d --build

# Проверить статус
docker-compose ps

# Проверить логи если что-то не работает
docker-compose logs backend
docker-compose logs frontend
```

## Шаг 6: Проверить работу через HTTP

Откройте в браузере: http://45.129.2.158:3000

Если работает - переходим к SSL.

## Шаг 7: Настроить DNS

**ВАЖНО!** Перед получением SSL сертификата настройте DNS:

1. Зайдите в панель управления доменом kybyshka-dev.ru
2. Создайте A-запись:
   - Имя: `@` (или пусто)
   - Тип: `A`
   - Значение: `45.129.2.158`
   - TTL: 300

3. Проверьте что домен резолвится:
```bash
ping kybyshka-dev.ru
# Должен показать 45.129.2.158
```

## Шаг 8: Получить SSL сертификат

```bash
# Дать права на выполнение скрипта
chmod +x init-ssl.sh

# Запустить получение сертификата
./init-ssl.sh
```

Если скрипт не работает, получите сертификат вручную:

```bash
# Остановить текущий nginx
docker-compose down

# Запустить временный nginx для certbot
docker run -d --name temp-nginx -p 80:80 -v $(pwd)/certbot/www:/var/www/certbot nginx:alpine

# Получить сертификат
docker run --rm \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/certbot/www:/var/www/certbot \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email admin@kybyshka-dev.ru \
  --agree-tos \
  --no-eff-email \
  -d kybyshka-dev.ru

# Удалить временный nginx
docker rm -f temp-nginx

# Запустить production конфиг с SSL
docker-compose -f docker-compose.prod.yml up -d --build
```

## Шаг 9: Проверить работу

Откройте: https://kybyshka-dev.ru

## Полезные команды

```bash
# Просмотр логов
docker-compose logs -f backend
docker-compose logs -f frontend

# Перезапуск
docker-compose restart

# Остановка
docker-compose down

# Полная пересборка
docker-compose down
docker-compose up -d --build --force-recreate

# Проверка статуса контейнеров
docker-compose ps

# Зайти внутрь контейнера
docker exec -it vkads-backend bash
```

## Troubleshooting

### Проблема: Backend unhealthy
```bash
docker-compose logs backend
# Проверить есть ли ошибки подключения к БД
```

### Проблема: Frontend не показывается
```bash
docker-compose logs frontend
# Проверить собрался ли frontend
```

### Проблема: SSL сертификат не получается
```bash
# Убедитесь что:
# 1. Домен резолвится на ваш IP
ping kybyshka-dev.ru

# 2. Порт 80 открыт
sudo ufw allow 80
sudo ufw allow 443

# 3. Нет других процессов на порту 80
sudo netstat -tulpn | grep :80
```

### Обновление кода
```bash
# Остановить контейнеры
docker-compose down

# Получить новый код из git
git pull

# Пересобрать и запустить
docker-compose up -d --build
```
