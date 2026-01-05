"""
Система логирования на Loguru с поддержкой фильтрации.

Фильтрация по:
- user_id: ID пользователя
- service: vk_api, database, telegram, scheduler, leadstech
- function: scaling, auto_disable, whitelist, api_request

Примеры использования:
    from utils.logging_setup import get_logger

    # Базовый логгер
    logger = get_logger()
    logger.info("Простое сообщение")

    # Логгер с контекстом
    logger = get_logger(service="vk_api", user_id=123)
    logger.info("Запрос к API")

    # Добавление функции в контекст
    logger = get_logger(service="scheduler", function="scaling", user_id=456)
    logger.info("Масштабирование запущено")
"""

import sys
from pathlib import Path
from loguru import logger
from contextvars import ContextVar
from utils.time_utils import get_moscow_time

# Контекстные переменные для передачи между функциями
_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
_current_service: ContextVar[str | None] = ContextVar("current_service", default=None)
_current_function: ContextVar[str | None] = ContextVar("current_function", default=None)

# Путь к логам
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Флаг инициализации
_initialized = False


def _format_record(record: dict) -> str:
    """Форматирование записи лога с контекстом."""
    # Получаем extra данные
    extra = record.get("extra", {})
    user_id = extra.get("user_id") or _current_user_id.get()
    service = extra.get("service") or _current_service.get() or "app"
    function = extra.get("function") or _current_function.get()

    # Формируем timestamp в московском времени
    moscow_time = get_moscow_time()
    timestamp = moscow_time.strftime("%Y-%m-%d %H:%M:%S")

    # Формируем контекст
    context_parts = [service]
    if function:
        context_parts.append(function)
    if user_id:
        context_parts.append(f"user:{user_id}")
    context = " | ".join(context_parts)

    level = record["level"].name
    # Используем {message} плейсхолдер loguru вместо прямой подстановки
    # Это позволяет loguru правильно обработать message без повторного парсинга
    return timestamp + " | " + f"{level:<8}" + " | " + context + " | {message}\n"


def _filter_by_service(service_name: str):
    """Создаёт фильтр для конкретного сервиса."""
    def filter_func(record):
        extra = record.get("extra", {})
        record_service = extra.get("service") or _current_service.get()
        return record_service == service_name
    return filter_func


def _filter_by_user(user_id: int):
    """Создаёт фильтр для конкретного пользователя."""
    def filter_func(record):
        extra = record.get("extra", {})
        record_user = extra.get("user_id") or _current_user_id.get()
        return record_user == user_id
    return filter_func


def _filter_by_function(function_name: str):
    """Создаёт фильтр для конкретной функции."""
    def filter_func(record):
        extra = record.get("extra", {})
        record_func = extra.get("function") or _current_function.get()
        return record_func == function_name
    return filter_func


def setup_logging():
    """
    Инициализация системы логирования.
    Вызывается один раз при старте приложения.
    """
    global _initialized
    if _initialized:
        return logger

    # Убеждаемся что директория для логов существует
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Удаляем стандартный handler
    logger.remove()

    # Консольный вывод (все логи)
    logger.add(
        sys.stdout,
        format=_format_record,
        level="DEBUG",
        colorize=True,
    )

    # Основной лог-файл (все логи)
    logger.add(
        LOG_DIR / "backend_all.log",
        format=_format_record,
        level="DEBUG",
        rotation="50 MB",
        retention="7 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,  # Асинхронная запись через очередь (потокобезопасно)
    )

    # Отдельный файл для ошибок
    logger.add(
        LOG_DIR / "backend_errors.log",
        format=_format_record,
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )

    # Файлы по сервисам
    services = ["vk_api", "database", "telegram", "scheduler", "leadstech", "scaling_engine", "roi_loader"]
    for service in services:
        logger.add(
            LOG_DIR / f"service_{service}.log",
            format=_format_record,
            level="DEBUG",
            filter=_filter_by_service(service),
            rotation="20 MB",
            retention="7 days",
            compression="gz",
            encoding="utf-8",
        )

    # Файлы по функциям
    functions = ["scaling", "auto_disable", "whitelist"]
    for func in functions:
        logger.add(
            LOG_DIR / f"function_{func}.log",
            format=_format_record,
            level="DEBUG",
            filter=_filter_by_function(func),
            rotation="20 MB",
            retention="7 days",
            compression="gz",
            encoding="utf-8",
        )

    _initialized = True
    logger.bind(service="app").info("Система логирования инициализирована")
    return logger


def get_logger(
    service: str | None = None,
    function: str | None = None,
    user_id: int | None = None,
):
    """
    Получить логгер с привязанным контекстом.

    Args:
        service: Имя сервиса (vk_api, database, telegram, scheduler, leadstech)
        function: Имя функции (scaling, auto_disable, whitelist)
        user_id: ID пользователя

    Returns:
        Логгер с привязанным контекстом

    Example:
        logger = get_logger(service="vk_api", user_id=123)
        logger.info("Запрос выполнен")
        # Вывод: 2024-01-15 12:00:00 | INFO     | vk_api | user:123 | Запрос выполнен
    """
    # Убеждаемся что логирование инициализировано
    if not _initialized:
        setup_logging()

    # Собираем контекст
    context = {}
    if service:
        context["service"] = service
    if function:
        context["function"] = function
    if user_id:
        context["user_id"] = user_id

    return logger.bind(**context)


def set_context(
    user_id: int | None = None,
    service: str | None = None,
    function: str | None = None,
):
    """
    Установить глобальный контекст для текущего потока/корутины.
    Полезно для установки user_id в начале обработки запроса.

    Example:
        set_context(user_id=123, service="scheduler")
        logger.info("Сообщение")  # автоматически добавит user_id и service
    """
    if user_id is not None:
        _current_user_id.set(user_id)
    if service is not None:
        _current_service.set(service)
    if function is not None:
        _current_function.set(function)


def clear_context():
    """Очистить глобальный контекст."""
    _current_user_id.set(None)
    _current_service.set(None)
    _current_function.set(None)


class _AutoCreateFileSink:
    """
    Кастомный sink для loguru, который автоматически пересоздаёт
    файл и папку если они были удалены.
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._file = None
        self._ensure_file()

    def _ensure_file(self):
        """Убедиться что файл и папка существуют."""
        # Создаём папку если удалена
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        # Открываем/создаём файл
        if self._file is None or self._file.closed:
            self._file = open(self.file_path, "a", encoding="utf-8")

    def write(self, message: str):
        """Записать сообщение, пересоздавая файл при необходимости."""
        # Проверяем существует ли файл
        if not self.file_path.exists():
            # Файл удалён - закрываем старый handle и создаём заново
            if self._file and not self._file.closed:
                try:
                    self._file.close()
                except Exception:
                    pass
            self._file = None
            self._ensure_file()

        try:
            self._file.write(message)
            self._file.flush()
        except Exception:
            # При любой ошибке пересоздаём файл
            self._file = None
            self._ensure_file()
            self._file.write(message)
            self._file.flush()

    def close(self):
        """Закрыть файл."""
        if self._file and not self._file.closed:
            self._file.close()


def add_user_log_file(user_id: int, function: str = "scaling"):
    """
    Добавить отдельный лог-файл для конкретного пользователя.
    Логи сохраняются в папку logs/user_{id}/.
    Файл автоматически пересоздаётся если был удалён.

    Args:
        user_id: ID пользователя
        function: Функция (scaling, auto_disable и т.д.)

    Returns:
        ID хендлера (для последующего удаления если нужно)
    """
    # Создаём папку для пользователя
    user_log_dir = LOG_DIR / f"user_{user_id}"
    user_log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = get_moscow_time().strftime("%Y%m%d_%H%M%S")
    log_file = user_log_dir / f"{function}_{timestamp}.log"

    # Используем кастомный sink для автопересоздания файла
    sink = _AutoCreateFileSink(log_file)

    handler_id = logger.add(
        sink,
        format=_format_record,
        level="DEBUG",
        filter=_filter_by_user(user_id),
    )

    logger.bind(service="app", user_id=user_id).info(
        f"Создан персональный лог-файл: user_{user_id}/{log_file.name}"
    )

    return handler_id


def remove_handler(handler_id: int):
    """Удалить хендлер по ID."""
    logger.remove(handler_id)


# Совместимость со старым API
def setup_scaling_logging(user_id: int):
    """
    Совместимость со старым API.
    Настраивает контекст и создаёт персональный лог-файл.
    """
    set_context(user_id=user_id, service="scheduler", function="scaling")
    add_user_log_file(user_id, "scaling")
    return get_logger(service="scheduler", function="scaling", user_id=user_id)


def get_scaling_logger():
    """Совместимость со старым API."""
    return get_logger(service="scheduler", function="scaling")
