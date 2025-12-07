# Быстрый старт

## 1. Запуск приложения

```bash
# Запустить все сервисы (PostgreSQL + Backend + Frontend)
docker-compose up --build -d

# Проверить статус
docker-compose ps
```

Приложение будет доступно:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **PostgreSQL**: localhost:5432

## 2. Миграция данных (первый запуск)

Если у вас есть данные в `config/config.json` и `config/whitelist.json`:

```bash
docker-compose exec backend python migrate_data_to_db.py
```

Это перенесет:
- ✅ Все аккаунты VK Ads
- ✅ Whitelist баннеров
- ✅ Настройки (analysis, telegram, scheduler)

## 3. Готово!

Откройте http://localhost:3000 и начните работу.

## Управление

```bash
# Остановить
docker-compose down

# Перезапустить
docker-compose restart

# Посмотреть логи
docker-compose logs -f backend

# Остановить и удалить данные
docker-compose down -v
```

## Подробная документация

См. [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md) для полной информации о БД и миграции.
