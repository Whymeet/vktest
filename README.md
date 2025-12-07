# VK Ads Manager

Система автоматизации управления рекламными кампаниями ВКонтакте с Telegram ботом и современным веб-интерфейсом.

## Структура проекта

```
vktest/
├── backend/                  # Python backend
│   ├── api/                  # FastAPI веб-сервер
│   │   └── main.py           # REST API endpoints
│   ├── bot/                  # Telegram бот
│   │   ├── telegram_bot.py   # Основной модуль бота
│   │   └── telegram_notify.py # Уведомления
│   ├── core/                 # Основная бизнес-логика
│   │   └── main.py           # Анализатор объявлений
│   ├── scheduler/            # Планировщик задач
│   │   ├── scheduler_main.py # Автозапуск анализа
│   │   └── logs/             # Логи планировщика
│   ├── utils/                # Утилиты
│   │   ├── config.py         # Работа с конфигурацией
│   │   ├── logging_setup.py  # Настройка логирования
│   │   └── vk_api_async.py   # Асинхронный VK API клиент
│   └── requirements.txt      # Python зависимости
├── frontend/                 # React веб-интерфейс
│   ├── src/
│   │   ├── api/              # API клиент
│   │   ├── components/       # React компоненты
│   │   └── pages/            # Страницы приложения
│   ├── package.json
│   └── ...
├── config/                   # Конфигурация
│   ├── config.json           # Основные настройки
│   └── whitelist.json        # Белый список объявлений
├── data/                     # Данные и кэш
├── logs/                     # Логи приложения
├── start-web.bat             # Запуск (Windows)
├── start-web.sh              # Запуск (Linux/Mac)
└── README.md
```

## Быстрый старт

### Установка

```bash
# 1. Установите Python зависимости
pip install -r backend/requirements.txt

# 2. Установите Node.js зависимости
cd frontend && npm install
```

### Запуск веб-интерфейса

**Windows:**
```cmd
start-web.bat
```

**Linux/macOS:**
```bash
chmod +x start-web.sh
./start-web.sh
```

После запуска откроются:
- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## Веб-интерфейс

### Разделы

| Раздел | Описание |
|--------|----------|
| **Dashboard** | Общая статистика, статус процессов |
| **Кабинеты** | Управление VK Ads кабинетами (CRUD) |
| **Настройки** | Анализ, Telegram, Планировщик |
| **Управление** | Запуск/остановка сервисов |
| **Логи** | Просмотр лог-файлов |
| **Whitelist** | Защита объявлений от отключения |

## Конфигурация

Основные настройки в `config/config.json`:

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
    "lookback_days": 10,
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
    "interval_minutes": 60
  }
}
```

## Технологии

### Backend
- **Python 3.8+**
- **FastAPI** - REST API
- **aiohttp** - асинхронные HTTP запросы
- **python-telegram-bot** - Telegram интеграция

### Frontend
- **React 18** + **TypeScript**
- **Vite** - сборка
- **TailwindCSS** - стили
- **React Query** - управление данными
- **React Router** - маршрутизация

## API Endpoints

### Основные

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/dashboard` | Данные дашборда |
| GET | `/api/accounts` | Список кабинетов |
| POST | `/api/accounts` | Создать кабинет |
| GET | `/api/settings` | Все настройки |
| GET | `/api/whitelist` | Белый список |
| GET | `/api/process/status` | Статус процессов |
| POST | `/api/process/scheduler/start` | Запустить планировщик |
| POST | `/api/process/analysis/start` | Запустить анализ |

Полная документация API: http://localhost:8000/docs
