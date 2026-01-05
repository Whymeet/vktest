# VK Ads Manager

Система автоматизации управления рекламными кампаниями ВКонтакте с анализом ROI, автоматическим отключением неэффективных баннеров, масштабированием бюджетов, Telegram-уведомлениями и современным веб-интерфейсом.

## Возможности

- **Автоматический анализ баннеров** — мониторинг эффективности рекламы по настраиваемым правилам
- **Auto-disable** — автоматическое отключение неэффективных баннеров
- **ROI-анализ** — интеграция с LeadsTech для анализа прибыльности
- **Автомасштабирование** — автоматическое увеличение бюджетов прибыльных кампаний
- **Telegram-уведомления** — мгновенные уведомления о действиях системы
- **Multi-tenant** — изолированные данные для каждого пользователя
- **REST API** — полноценный API с JWT-аутентификацией

## Структура проекта

```
vktest2/
├── backend/                    # Python FastAPI backend
│   ├── api/                    # REST API
│   │   ├── routers/           # Роуты (accounts, banners, settings...)
│   │   ├── schemas/           # Pydantic модели
│   │   ├── services/          # Бизнес-логика
│   │   └── app.py             # FastAPI приложение
│   ├── core/                   # Ядро системы
│   │   ├── analyzer.py        # Анализатор баннеров
│   │   └── config_loader.py   # Загрузка конфигурации
│   ├── database/               # База данных
│   │   ├── models.py          # SQLAlchemy модели
│   │   └── crud/              # CRUD операции
│   ├── scheduler/              # Планировщик задач
│   │   ├── scheduler_main.py  # Оркестратор
│   │   ├── analysis.py        # Анализ по расписанию
│   │   └── roi_reenable.py    # ROI-based reenable
│   ├── leadstech/              # LeadsTech интеграция
│   │   ├── leadstech_client.py # API клиент
│   │   └── roi_loader.py      # Загрузка ROI данных
│   ├── bot/                    # Telegram бот
│   │   ├── telegram_bot.py    # Обработчики команд
│   │   └── telegram_notify.py # Уведомления
│   ├── utils/                  # Утилиты
│   │   └── vk_api_async.py    # Асинхронный VK API клиент
│   └── requirements.txt
├── frontend/                   # React веб-интерфейс
│   ├── src/
│   │   ├── pages/             # Страницы приложения
│   │   ├── components/        # React компоненты
│   │   ├── api/               # API клиент (Axios)
│   │   └── hooks/             # React hooks
│   └── package.json
├── config/                     # Конфигурация
│   ├── config.json            # Основные настройки
│   └── whitelist.json         # Белый список баннеров
├── migrations/                 # Миграции базы данных (Alembic)
├── nginx/                      # Nginx конфигурация
├── docker-compose.yml          # Docker оркестрация
├── start-web.bat               # Запуск (Windows)
└── start-web.sh                # Запуск (Linux/Mac)
```

## Быстрый старт

### Локальная разработка

```bash
# 1. Установите Python зависимости
pip install -r backend/requirements.txt

# 2. Установите Node.js зависимости
cd frontend && npm install && cd ..

# 3. Запустите PostgreSQL (или используйте Docker)
docker run -d --name postgres -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:15-alpine

# 4. Запустите backend
cd backend && uvicorn api.app:app --reload --port 8000

# 5. Запустите frontend (в отдельном терминале)
cd frontend && npm run dev
```

### Docker (Production)

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f
```

### Скрипты запуска

**Windows:**
```cmd
start-web.bat
```

**Linux/macOS:**
```bash
chmod +x start-web.sh
./start-web.sh
```

После запуска:
- **Frontend:** http://localhost:5173 (dev) / http://localhost (prod)
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## Веб-интерфейс

| Раздел | Описание |
|--------|----------|
| **Dashboard** | Общая статистика, статус процессов |
| **Кабинеты** | Управление VK Ads кабинетами |
| **Правила отключения** | Настройка правил автоматического отключения баннеров |
| **Скейлинг** | Настройка автомасштабирования бюджетов |
| **Прибыльные объявления** | ROI-анализ (LeadsTech) |
| **Статистика** | История анализа и графики |
| **Whitelist** | Защита баннеров от отключения |
| **Настройки** | Анализ, Telegram, планировщик |
| **Управление** | Запуск/остановка сервисов |
| **Логи** | Просмотр лог-файлов |

## Конфигурация

### config/config.json

```json
{
  "vk_ads_api": {
    "base_url": "https://ads.vk.com/api/v2",
    "accounts": {
      "Название_кабинета": {
        "api": "Bearer_token",
        "spent_limit_rub": 100.0
      }
    }
  },
  "analysis_settings": {
    "lookback_days": 15,
    "spent_limit_rub": 100.0,
    "dry_run": false
  },
  "telegram": {
    "bot_token": "...",
    "chat_id": ["..."],
    "enabled": true
  },
  "scheduler": {
    "enabled": true,
    "interval_minutes": 1
  }
}
```

### Переменные окружения

```env
DATABASE_URL=postgresql://user:password@localhost:5432/vkads
SECRET_KEY=your-secret-key-for-jwt
```

## API Endpoints

### Аутентификация

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/auth/login` | Авторизация |
| POST | `/api/auth/refresh` | Обновление токена |
| GET | `/api/auth/me` | Текущий пользователь |

### Основные

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/dashboard` | Данные дашборда |
| GET/POST | `/api/accounts` | Управление кабинетами |
| GET | `/api/banners` | Список баннеров |
| GET | `/api/banners/stats` | Статистика баннеров |
| GET/POST | `/api/settings` | Настройки |
| GET/POST | `/api/whitelist` | Белый список |

### Правила и скейлинг

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET/POST | `/api/disable-rules` | Правила отключения |
| GET/POST | `/api/scaling` | Настройки масштабирования |
| GET/POST | `/api/leadstech` | LeadsTech конфигурация |

### Управление процессами

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/process/status` | Статус процессов |
| POST | `/api/process/scheduler/start` | Запустить планировщик |
| POST | `/api/process/scheduler/stop` | Остановить планировщик |
| POST | `/api/process/analysis/start` | Запустить анализ |

Полная документация API: http://localhost:8000/docs

## Технологии

### Backend
- **Python 3.8+**
- **FastAPI** — REST API
- **SQLAlchemy 2.0** — ORM
- **PostgreSQL 15** — база данных
- **aiohttp** — асинхронные HTTP запросы
- **python-telegram-bot** — Telegram интеграция
- **JWT** — аутентификация
- **Alembic** — миграции БД
- **Loguru** — логирование

### Frontend
- **React 19** + **TypeScript**
- **Vite** — сборка
- **TailwindCSS 4** — стили
- **TanStack Query** — управление данными
- **React Router 7** — маршрутизация
- **Axios** — HTTP клиент

### Инфраструктура
- **Docker** + **Docker Compose**
- **Nginx** — reverse proxy
- **Let's Encrypt** — SSL сертификаты
