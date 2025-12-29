# CI/CD Setup Guide

## Обзор

Проект использует GitHub Actions для автоматического деплоя на сервер.

### Когда происходит деплой:
- Автоматически при push в ветку `main`
- Вручную через GitHub Actions (workflow_dispatch)

### Что происходит:
1. Запускаются тесты бэкенда (Python/pytest)
2. Запускается линтинг и сборка фронтенда (npm)
3. При успехе — деплой на сервер через SSH

---

## Настройка GitHub Secrets

Перейдите в репозиторий на GitHub:
**Settings → Secrets and variables → Actions → New repository secret**

Добавьте следующие секреты:

| Secret Name | Описание | Пример |
|-------------|----------|--------|
| `SERVER_HOST` | IP адрес или домен сервера | `123.45.67.89` |
| `SERVER_USER` | Пользователь для SSH | `root` |
| `SSH_PRIVATE_KEY` | Приватный SSH ключ | Содержимое `~/.ssh/id_rsa` |
| `SERVER_PORT` | SSH порт (опционально) | `22` |

### Как получить SSH ключ:

1. **Создайте ключ (если нет):**
   ```bash
   ssh-keygen -t ed25519 -C "github-actions-deploy"
   ```

2. **Добавьте публичный ключ на сервер:**
   ```bash
   ssh-copy-id -i ~/.ssh/id_ed25519.pub root@YOUR_SERVER_IP
   ```

3. **Скопируйте приватный ключ в GitHub Secret:**
   ```bash
   cat ~/.ssh/id_ed25519
   ```
   Скопируйте весь вывод (включая `-----BEGIN` и `-----END-----`)

---

## Ручной деплой

### Через GitHub Actions:
1. Перейдите в **Actions** → **Deploy to Production**
2. Нажмите **Run workflow**
3. Выберите ветку и нажмите **Run workflow**

### Через SSH на сервере:
```bash
ssh root@YOUR_SERVER
cd /srv/vk-ads-parser/vktest
./scripts/deploy.sh
```

---

## Откат

Если что-то пошло не так, выполните на сервере:
```bash
cd /srv/vk-ads-parser/vktest
./scripts/rollback.sh
```

---

## Структура файлов

```
.github/
  workflows/
    deploy.yml          # GitHub Actions workflow

scripts/
  deploy.sh             # Скрипт деплоя для сервера
  rollback.sh           # Скрипт отката
```

---

## Первоначальная настройка сервера

Перед первым деплоем убедитесь, что на сервере:

1. **Установлен Docker и Docker Compose:**
   ```bash
   docker --version
   docker compose version
   ```

2. **Склонирован репозиторий:**
   ```bash
   mkdir -p /srv/vk-ads-parser
   cd /srv/vk-ads-parser
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git vktest
   ```

3. **Настроен .env файл:**
   ```bash
   cd /srv/vk-ads-parser/vktest
   cp .env.example .env
   # Отредактируйте .env с нужными значениями
   ```

4. **Скрипты имеют права на выполнение:**
   ```bash
   chmod +x scripts/*.sh
   ```

---

## Troubleshooting

### Деплой не запускается
- Проверьте, что secrets настроены правильно
- Проверьте логи в GitHub Actions

### Health check падает
- Проверьте логи: `docker compose logs backend`
- Проверьте, что .env файл настроен на сервере

### SSH connection refused
- Проверьте, что публичный ключ добавлен в `~/.ssh/authorized_keys` на сервере
- Проверьте правильность `SERVER_HOST` и `SERVER_PORT`
