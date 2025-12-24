"""
Redis client for caching API responses.
Used to reduce API calls to LeadsTech and VK Ads.
"""
import redis
import json
import os
from logging import getLogger
from typing import Any, Optional

logger = getLogger("vk_ads_manager")

# Настройки Redis из переменных окружения
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))

# Глобальный клиент (singleton)
_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """
    Получить Redis клиент (singleton).
    Возвращает None если Redis недоступен.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        # Проверяем подключение
        _redis_client.ping()
        logger.info(f"✅ Redis подключен: {REDIS_HOST}:{REDIS_PORT}")
        return _redis_client
    except redis.ConnectionError as e:
        logger.warning(f"⚠️ Redis недоступен: {e}. Кэширование отключено.")
        _redis_client = None
        return None
    except Exception as e:
        logger.warning(f"⚠️ Ошибка Redis: {e}. Кэширование отключено.")
        _redis_client = None
        return None


def cache_get(key: str) -> Optional[Any]:
    """
    Получить значение из кэша.
    Возвращает None если ключ не найден или Redis недоступен.
    """
    client = get_redis()
    if client is None:
        return None

    try:
        data = client.get(key)
        if data:
            return json.loads(data)
        return None
    except redis.ConnectionError:
        logger.warning(f"⚠️ Redis connection lost при GET {key}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Ошибка декодирования кэша {key}: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Redis GET error для {key}: {e}")
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """
    Сохранить значение в кэш с TTL.

    Args:
        key: Ключ кэша
        value: Значение (будет сериализовано в JSON)
        ttl_seconds: Время жизни в секундах (по умолчанию 5 минут)

    Returns:
        True если успешно, False если ошибка
    """
    client = get_redis()
    if client is None:
        return False

    try:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        client.setex(key, ttl_seconds, serialized)
        return True
    except redis.ConnectionError:
        logger.warning(f"⚠️ Redis connection lost при SET {key}")
        return False
    except (TypeError, ValueError) as e:
        logger.warning(f"⚠️ Ошибка сериализации для кэша {key}: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Redis SET error для {key}: {e}")
        return False


def cache_delete(key: str) -> bool:
    """Удалить ключ из кэша."""
    client = get_redis()
    if client is None:
        return False

    try:
        client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"⚠️ Redis DELETE error для {key}: {e}")
        return False


def cache_clear_pattern(pattern: str) -> int:
    """
    Удалить все ключи по паттерну.
    Например: cache_clear_pattern("lt:*") удалит все ключи LeadsTech.

    Returns:
        Количество удалённых ключей
    """
    client = get_redis()
    if client is None:
        return 0

    try:
        keys = client.keys(pattern)
        if keys:
            deleted = client.delete(*keys)
            logger.info(f"🗑️ Удалено {deleted} ключей по паттерну {pattern}")
            return deleted
        return 0
    except Exception as e:
        logger.warning(f"⚠️ Redis CLEAR error для паттерна {pattern}: {e}")
        return 0


def is_redis_available() -> bool:
    """Проверить доступность Redis."""
    client = get_redis()
    if client is None:
        return False

    try:
        client.ping()
        return True
    except Exception:
        return False
