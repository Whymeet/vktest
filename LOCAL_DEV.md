# Локальный запуск на Windows (без Docker)

## Требования

1. **Python 3.8+** - [скачать](https://www.python.org/downloads/)
2. **Node.js 18+** - [скачать](https://nodejs.org/)
3. **PostgreSQL 15** - [скачать](https://www.postgresql.org/download/windows/)

## Шаг 1: Установка PostgreSQL

1. Скачайте и установите PostgreSQL
2. Запомните пароль для пользователя `postgres`
3. После установки откройте **pgAdmin** или **psql**

### Создание базы данных

Откройте терминал PostgreSQL (psql) или pgAdmin и выполните:

```sql
-- Создать пользователя
CREATE USER vkads WITH PASSWORD 'vkads_password';

-- Создать базу данных
CREATE DATABASE vkads OWNER vkads;

-- Дать права
GRANT ALL PRIVILEGES ON DATABASE vkads TO vkads;
```

Или через командную строку:
```cmd
psql -U postgres -c "CREATE USER vkads WITH PASSWORD 'vkads_password';"
psql -U postgres -c "CREATE DATABASE vkads OWNER vkads;"
```

## Шаг 2: Запуск проекта

### Автоматический запуск (рекомендуется)

```cmd
start-local.bat
```

Скрипт автоматически:
- Установит все зависимости
- Запустит backend на порту 8000
- Запустит frontend на порту 5173
- Откроет браузер

### Ручной запуск

**Терминал 1 - Backend:**
```cmd
cd backend

:: Установка зависимостей (один раз)
pip install -r requirements.txt

:: Переменные окружения
set DATABASE_URL=postgresql://vkads:vkads_password@localhost:5432/vkads
set JWT_SECRET_KEY=local_dev_secret_key_32_chars_minimum
set ALLOWED_ORIGINS=    ,http://localhost:3000

:: Запуск
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Терминал 2 - Frontend:**
```cmd
cd frontend

:: Установка зависимостей (один раз)
npm install

:: Запуск
npm run dev
```

## Шаг 3: Создание администратора

После запуска backend выполните в **новом терминале**:

```cmd
cd backend

:: Установите переменные окружения
set DATABASE_URL=postgresql://vkads:vkads_password@localhost:5432/vkads

:: Интерактивный режим
python create_admin.py --interactive

:: Или сразу с данными
python create_admin.py --username admin --password admin123
```

## Шаг 4: Войти в систему

1. Откройте http://localhost:5173
2. Введите логин и пароль администратора
3. Готово!

## Адреса

| Сервис | URL |
|--------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Документация | http://localhost:8000/docs |

## Возможные проблемы

### PostgreSQL не запущен
```
Ошибка: connection refused
```
**Решение:** Откройте "Службы" Windows (services.msc) и запустите службу PostgreSQL

### Порт занят
```
Ошибка: address already in use
```
**Решение:**
```cmd
:: Найти процесс на порту 8000
netstat -ano | findstr :8000

:: Убить процесс по PID
taskkill /PID <PID> /F
```

### Ошибка подключения к БД
```
Ошибка: password authentication failed
```
**Решение:** Проверьте пароль в DATABASE_URL и убедитесь что пользователь `vkads` создан

### npm install падает
**Решение:**
```cmd
:: Очистить кэш
npm cache clean --force

:: Удалить node_modules и попробовать снова
rd /s /q node_modules
npm install
```

## Структура переменных окружения

Для локальной разработки используются:

```
DATABASE_URL=postgresql://vkads:vkads_password@localhost:5432/vkads
JWT_SECRET_KEY=local_dev_secret_key_32_chars_minimum
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

Эти переменные уже встроены в `start-local.bat`, менять их не нужно.
