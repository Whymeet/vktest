# VK Ads Manager

Система автоматизации управления рекламными кампаниями ВКонтакте с Telegram ботом и веб-интерфейсом.

## Структура проекта

```
vktest/
├── bot/                    # Telegram бот
│   ├── telegram_bot.py     # Основной модуль бота
│   ├── telegram_notify.py  # Уведомления через Telegram
│   └── __init__.py
├── cfg/                    # Конфигурация
│   ├── config.json         # Основные настройки
│   └── whitelist.json      # Белый список пользователей
├── requirements/           # Зависимости
│   └── requirements_admin.txt
├── scheduler/              # Планировщик задач
│   ├── scheduler_main.py   # Основной модуль планировщика
│   ├── scheduler_service.bat
│   ├── scheduler_service.sh
│   └── logs/
├── scripts/               # Скрипты управления
│   ├── start.sh           # Запуск сервисов
│   ├── stop.sh            # Остановка сервисов
│   ├── status.sh          # Статус сервисов
│   ├── run.sh             # Запуск отдельных компонентов
│   ├── autostart.sh       # Автозапуск при загрузке
│   └── *.sh, *.bat        # Остальные скрипты
├── src/                   # Основной код приложения
│   ├── main.py            # Главный модуль анализа
│   └── __init__.py
├── utils/                 # Утилиты
│   ├── config.py          # Работа с конфигурацией
│   ├── logging_setup.py   # Настройка логирования
│   ├── vk_api.py          # API для работы с ВК
│   └── __init__.py
├── web/                   # Веб-интерфейс
│   ├── admin_panel.py     # Административная панель
│   └── templates/         # HTML шаблоны
│       ├── base.html
│       ├── dashboard.html
│       └── ...
└── __init__.py
```

## Запуск

### Основные команды

```bash
# Запуск всех сервисов
./scripts/start.sh

# Остановка всех сервисов  
./scripts/stop.sh

# Проверка статуса
./scripts/status.sh

# Запуск отдельных компонентов
./scripts/run.sh main        # Основной анализ
./scripts/run.sh bot         # Telegram бот
./scripts/run.sh scheduler   # Планировщик
```

### Windows

```cmd
# Запуск админ панели
scripts\start_admin.bat
```

## Установка

1. Клонируйте репозиторий
2. Создайте виртуальное окружение: `python -m venv .venv`
3. Активируйте окружение: `source .venv/bin/activate` (Linux) или `.venv\Scripts\activate` (Windows)
4. Установите зависимости: `pip install -r requirements/requirements_admin.txt`
5. Настройте конфигурацию в `cfg/config.json`

## Конфигурация

Основные настройки в `cfg/config.json`:
- API токены ВКонтакте
- Настройки Telegram бота
- Параметры планировщика
- Настройки логирования