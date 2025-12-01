
import requests
import json
import time
import logging
import os
import traceback
from datetime import date, timedelta, datetime

# Импортируем функции Telegram
from telegram_notify import send_telegram_message, format_telegram_account_statistics

# ===================== TELEGRAM ФУНКЦИИ =====================

def send_telegram_error(error_message):
    """Отправляет сообщение об ошибке в Telegram"""
    try:
        config = load_config()
        send_telegram_message(config, f"<b>Ошибка</b>\n\n{error_message}")
    except Exception as e:
        print(f"Не удалось отправить ошибку в Telegram: {e}")

# ===================== НАСТРОЙКИ =====================

def load_config():
    """Загружает конфигурацию из cfg/config.json"""
    config_path = os.path.join("cfg", "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError("❌ Файл cfg/config.json не найден! Создайте файл с настройками API.")
    except json.JSONDecodeError as e:
        raise ValueError(f"❌ Ошибка в cfg/config.json: {e}")


def load_whitelist():
    """Загружает белый список из отдельного файла cfg/whitelist.json.
    Формат ожидается:
    {
      "banners_whitelist": [123, 456]
    }
    Если файл не найден — пытаемся взять из `config` (ключ `banners_whitelist`) для совместимости.
    """
    wl_path = os.path.join("cfg", "whitelist.json")
    try:
        with open(wl_path, "r", encoding="utf-8") as f:
            wl = json.load(f)
            return wl if isinstance(wl, dict) else {}
    except FileNotFoundError:
        # Файл whitelist.json отсутствует — попробуем взять из основного конфига
        try:
            cfg = globals().get('config')
            if isinstance(cfg, dict):
                return {"banners_whitelist": cfg.get("banners_whitelist", [])}
        except Exception:
            pass
        return {"banners_whitelist": []}

# Загружаем конфигурацию
config = load_config()

# VK Ads API настройки
BASE_URL = config["vk_ads_api"]["base_url"]
ACCOUNTS = config["vk_ads_api"]["accounts"]

# Настройки анализа
LOOKBACK_DAYS = config["analysis_settings"]["lookback_days"]           # окно в днях
# Проверяем переменную окружения для дополнительных дней (используется планировщиком)
extra_days = int(os.environ.get('VK_EXTRA_LOOKBACK_DAYS', '0'))
if extra_days > 0:
    LOOKBACK_DAYS += extra_days
    
SPENT_LIMIT_RUB = config["analysis_settings"]["spent_limit_rub"]       # порог расходов по умолчанию (если не указан для кабинета)
DRY_RUN = config["analysis_settings"]["dry_run"]                       # True — только вывод без фактического отключения
SLEEP_BETWEEN_CALLS = config["analysis_settings"]["sleep_between_calls"] # Анти-RateLimit

RESULT_METRIC = "total.base.goals"  # что считаем "результатом" (можно заменить на свой путь)


# ===================== НАСТРОЙКА ЛОГИРОВАНИЯ =====================

def setup_logging():
    """Настройка логирования в консоль и файл с ротацией по дням"""
    
    # Создаем папку logs если её нет
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Настройка логгера
    logger = logging.getLogger("vk_ads_manager")
    logger.setLevel(logging.DEBUG)
    
    # Очищаем существующие handlers
    logger.handlers.clear()
    
    # Форматтер для сообщений
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler для консоли (INFO и выше)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler для файла с уникальным именем на каждый запуск
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"vk_ads_manager_{timestamp}.log")
    file_handler = logging.FileHandler(
        log_file, 
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Логируем информацию о файле лога
    logger.info(f"📝 Логирование в файл: {log_file}")
    
    return logger

# Инициализируем логгер
logger = setup_logging()
# Загружаем белый список (отдельный файл cfg/whitelist.json). Фоллбек к конфигу для совместимости.
WHITELIST = load_whitelist()
logger.info(f"🔒 Загружен whitelist: {len(WHITELIST.get('banners_whitelist', []) if isinstance(WHITELIST, dict) else 0)} глобальных ID")


# ===================== ВСПОМОГАТЕЛЬНОЕ =====================

def _headers(token: str):
    return {"Authorization": f"Bearer {token}"}

def _iso(d: date) -> str:
    return d.isoformat()

def _dget(dct: dict, dotted: str, default=0.0):
    """Безопасно берёт по 'точечному' пути (например, total.base.spent)."""
    cur = dct
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default

def _is_active_group(g: dict) -> bool:
    """
    У группы может быть status и/или delivery.status.
    Считаем активной, если хотя бы одно поле явно == 'active' (без учёта регистров).
    """
    status = (g.get("status") or "").lower()
    
    # Безопасно извлекаем delivery status
    delivery = g.get("delivery")
    if isinstance(delivery, dict):
        dstatus = (delivery.get("status") or "").lower()
    elif isinstance(delivery, str):
        dstatus = delivery.lower()
    else:
        dstatus = ""
    
    return status == "active" or dstatus == "active"


# ===================== ЗАГРУЗКА АКТИВНЫХ ОБЪЯВЛЕНИЙ =====================

def get_banners_active(token: str, base_url: str, fields: str = "id,name,status,delivery,ad_group_id,moderation_status", limit: int = 200):
    """
    Загружаем все активные объявления (banners) и фильтруем по активным.
    Эндпоинт: GET /banners.json?fields=...
    """
    logger.info("🔄 Начинаем загрузку рекламных объявлений (banners) из VK Ads API")
    logger.debug(f"Параметры: fields={fields}, limit={limit}")
    
    url = f"{base_url}/banners.json"
    offset = 0
    items_all = []
    page_num = 1

    while True:
        logger.debug(f"📥 Загружаем страницу {page_num} (offset={offset})")
        params = {
            "fields": fields, 
            "limit": limit, 
            "offset": offset,
            "_status": "active",  # Фильтруем только активные объявления
            "_ad_group_status": "active"  # И только из активных групп
        }
        
        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=20)
            if r.status_code != 200:
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке объявлений: {r.text[:200]}")
                raise RuntimeError(f"[banners] HTTP {r.status_code}: {r.text}")
            
            payload = r.json()
            items = payload.get("items", [])
            items_all.extend(items)
            
            logger.debug(f"✓ Страница {page_num}: получено {len(items)} объявлений")

            # пагинация
            if len(items) < limit:
                logger.debug(f"📄 Достигнута последняя страница ({len(items)} < {limit})")
                break
                
            offset += limit
            page_num += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
            
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка сети при загрузке объявлений: {e}")
            raise

    logger.info(f"✅ Загружено {len(items_all)} активных объявлений за {page_num} страниц")
    logger.info("ℹ️ Фильтрация выполнена на стороне сервера VK API (_status=active, _ad_group_status=active)")
    
    # Все загруженные объявления уже активные благодаря серверной фильтрации
    logger.debug("📋 Примеры загруженных активных объявлений:")
    for i, b in enumerate(items_all[:3]):  # Показываем первые 3
        logger.debug(f"  • [{b.get('id')}] {b.get('name', 'Unknown')} | status={b.get('status')} | ad_group_id={b.get('ad_group_id')}")
    
    return items_all


# ===================== ЗАГРУЗКА СТАТИСТИКИ =====================

def save_raw_statistics_json(payload: dict, date_from: str, date_to: str, group_ids: list = None):
    """Сохраняет сырой JSON ответ от API статистики для последующего анализа"""
    try:
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        # Формируем имя файла с временной меткой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if group_ids:
            ids_suffix = f"_ids_{len(group_ids)}"
        else:
            ids_suffix = "_all"
            
        filename = f"vk_statistics_raw_{date_from}_{date_to}{ids_suffix}_{timestamp}.json"
        filepath = os.path.join("data", filename)
        
        # Добавляем метаданные к JSON
        enriched_payload = {
            "metadata": {
                "request_timestamp": datetime.now().isoformat(),
                "date_from": date_from,
                "date_to": date_to,
                "requested_group_ids": group_ids,
                "groups_count": len(group_ids) if group_ids else "all"
            },
            "raw_response": payload
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(enriched_payload, f, ensure_ascii=False, indent=2)
            
        logger.debug(f"💾 Сохранен сырой JSON статистики: {filepath}")
        
    except Exception as e:
        logger.warning(f"⚠️ Не удалось сохранить сырой JSON: {e}")

def get_banners_stats_day(token: str, base_url: str, date_from: str, date_to: str, banner_ids: list = None, metrics: str = "base"):
    """
    GET /statistics/banners/day.json
    Возвращает items с rows по дням и total.* по объявлению.
    Использует правильный параметр id=123,456,789 (через запятую).
    """
    if banner_ids:
        ids_str = ",".join(map(str, banner_ids))
        logger.info(f"📊 Запрашиваем статистику за период {date_from} - {date_to} для {len(banner_ids)} объявлений")
        logger.debug(f"🆔 ID объявлений: {ids_str}")
    else:
        logger.info(f"📊 Запрашиваем статистику за период {date_from} - {date_to} для ВСЕХ объявлений")
    
    url = f"{base_url}/statistics/banners/day.json"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metrics,
    }
    
    # ✅ Правильный параметр: id (без s) через запятую
    if banner_ids:
        params["id"] = ",".join(map(str, banner_ids))
        logger.debug(f"🔧 Добавлен фильтр id: {params['id']}")

    try:
        logger.debug(f"🌐 Отправляем запрос к {url} с параметрами: {params}")
        r = requests.get(url, headers=_headers(token), params=params, timeout=30)
        
        if r.status_code != 200:
            logger.error(f"❌ Ошибка HTTP {r.status_code} при получении статистики: {r.text[:200]}")
            raise RuntimeError(f"[stats day] HTTP {r.status_code}: {r.text}")
        
        payload = r.json()
        items = payload.get("items", [])
        logger.info(f"✅ Получена статистика по {len(items)} объявлениям")
        
        # 💾 Сохраняем полный JSON ответ для анализа
        save_raw_statistics_json(payload, date_from, date_to, banner_ids)
        
        # Проверяем, что получили именно те объявления, которые запрашивали
        if banner_ids and items:
            received_ids = [item.get("id") for item in items if item.get("id")]
            logger.debug(f"📋 Получены ID: {received_ids}")
            
        return items
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при получении статистики: {e}")
        raise


def aggregate_stats_by_banner(items):
    """
    Извлекает статистику из готовых total данных (суммированных за весь период):
    { banner_id: {"spent": float, "clicks": float, "shows": float, "vk_goals": int} }
    """
    logger.info("🔢 Агрегируем статистику по объявлениям")
    agg = {}

    for item in items:
        bid = item.get("id")
        if bid is None:
            continue

        # ✅ Используем готовые total данные вместо суммирования rows
        total = item.get("total", {}).get("base", {})
        
        # Основные метрики из total.base
        spent = _dget(total, "spent", 0.0)
        clicks = _dget(total, "clicks", 0.0)
        shows = _dget(total, "shows", 0.0)
        
        # VK цели из total.base.vk.goals
        vk_goals = _dget(total, "vk.goals", 0.0)

        agg[bid] = {
            "spent": spent,
            "clicks": clicks,
            "shows": shows,
            "vk_goals": vk_goals,  # Только VK цели
        }
        
        logger.debug(f"📋 Объявление {bid}: spent={spent}₽, vk_goals={vk_goals}")

    logger.info(f"✅ Агрегировано {len(agg)} объявлений")
    return agg


# ===================== ОТКЛЮЧЕНИЕ ОБЪЯВЛЕНИЙ =====================

def disable_banner(token: str, base_url: str, banner_id: int, dry_run: bool = True):
    """
    Отключает рекламное объявление, изменяя статус с 'active' на 'blocked'
    POST /banners/{banner_id}.json с телом {"status": "blocked"}
    """
    if dry_run:
        logger.info(f"🔸 [DRY RUN] Объявление {banner_id} было бы отключено (active → blocked)")
        return {"success": True, "dry_run": True}
    
    url = f"{base_url}/banners/{banner_id}.json"
    data = {"status": "blocked"}
    
    try:
        logger.info(f"🔄 Отключаем объявление {banner_id} (active → blocked)")
        response = requests.post(
            url,
            headers=_headers(token),
            json=data,
            timeout=20
        )
        # VK API возвращает 204 No Content при успешном обновлении статуса
        if response.status_code in (200, 204):
            logger.info(f"✅ Объявление {banner_id} успешно отключено (HTTP {response.status_code})")
            # Если есть тело, возвращаем его, иначе просто success
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при отключении объявления {banner_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при отключении объявления {banner_id}: {error_msg}")
        return {"success": False, "error": error_msg}

def trigger_statistics_refresh(token: str, base_url: str, trigger_config: dict):
    """
    Запускает триггер для обновления статистики VK Ads:
    1. Включает специальную группу
    2. Ждет указанное время
    3. Отключает группу обратно
    
    Это заставляет VK пересчитать статистику для всех групп в кабинете
    """
    if not trigger_config.get("enabled", False):
        logger.debug("🔧 Триггер обновления статистики отключен")
        return {"success": True, "skipped": True}
    
    group_id = trigger_config.get("group_id")
    wait_seconds = trigger_config.get("wait_seconds", 20)
    
    if not group_id:
        logger.warning("⚠️ ID группы для триггера не настроен - пропускаем обновление статистики")
        return {"success": False, "error": "Не настроен group_id"}
    
    logger.info(f"🎯 ЗАПУСК ТРИГГЕРА ОБНОВЛЕНИЯ СТАТИСТИКИ VK (группа {group_id})")
    
    # Включаем группу
    result1 = toggle_ad_group_status(token, base_url, group_id, "active")
    if not result1.get("success"):
        logger.error(f"❌ Не удалось включить триггер группу {group_id}: {result1.get('error')}")
        return {"success": False, "error": f"Ошибка включения: {result1.get('error')}"}
    
    # Ждем
    logger.info(f"⏳ Ожидание {wait_seconds} сек. для обновления статистики VK...")
    time.sleep(wait_seconds)
    
    # Отключаем группу обратно
    result2 = toggle_ad_group_status(token, base_url, group_id, "blocked")
    if not result2.get("success"):
        logger.error(f"❌ Не удалось отключить триггер группу {group_id}: {result2.get('error')}")
        return {"success": False, "error": f"Ошибка отключения: {result2.get('error')}"}
    
    logger.info(f"✅ Триггер обновления статистики завершен (группа {group_id})")
    return {"success": True, "group_id": group_id, "wait_seconds": wait_seconds}

def toggle_ad_group_status(token: str, base_url: str, group_id: int, status: str):
    """
    Изменяет статус рекламной группы
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Неверный статус '{status}'. Допустимые значения: 'active', 'blocked'"
        logger.error(f"❌ {error_msg}")
        return {"success": False, "error": error_msg}
    
    url = f"{base_url}/ad_groups/{group_id}.json"
    data = {"status": status}
    
    try:
        status_emoji = "▶️" if status == "active" else "⏸️"
        action = "включаем" if status == "active" else "блокируем"
        logger.info(f"{status_emoji} {action.capitalize()} триггер группу {group_id} (→ {status})")
        
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        
        if response.status_code in (200, 204):
            logger.info(f"✅ Группа {group_id} успешно изменена на '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при изменении статуса группы {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при изменении статуса группы {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}

def disable_unprofitable_banners(token: str, base_url: str, unprofitable_banners: list, dry_run: bool = True):
    """
    Отключает все убыточные объявления с задержкой между запросами
    """
    if not unprofitable_banners:
        logger.info("✅ Нет убыточных объявлений для отключения")
        return {"disabled": 0, "failed": 0, "results": []}

    logger.info(f"🎯 {'[DRY RUN] ' if dry_run else ''}Начинаем отключение {len(unprofitable_banners)} убыточных объявлений")

    # Загружаем белый список из отдельного файла (cfg/whitelist.json)
    whitelist_raw = WHITELIST.get("banners_whitelist", []) if isinstance(WHITELIST, dict) else []
    whitelist_set = set()
    for v in whitelist_raw:
        try:
            whitelist_set.add(int(v))
        except Exception:
            # Игнорируем нечисловые значения
            continue

    disabled_count = 0
    failed_count = 0
    results = []

    for i, banner in enumerate(unprofitable_banners, 1):
        banner_id = banner.get("id")
        banner_name = banner.get("name", "Unknown")
        spent = banner.get("spent", 0)
        ad_group_id = banner.get("ad_group_id", "N/A")

        logger.info(f"📋 [{i}/{len(unprofitable_banners)}] Объявление {banner_id}: {banner_name} (группа {ad_group_id}, потрачено: {spent:.2f}₽)")

        # Проверяем белый список
        if banner_id in whitelist_set:
            logger.info(f"⏳ Пропускаем объявление {banner_id} — находится в белом списке (не трогаем)")
            results.append({
                "banner_id": banner_id,
                "banner_name": banner_name,
                "ad_group_id": ad_group_id,
                "spent": spent,
                "success": False,
                "skipped": True,
                "error": "skipped (whitelisted)"
            })
        else:
            # Отключаем объявление
            result = disable_banner(token, base_url, banner_id, dry_run)

            if result.get("success"):
                disabled_count += 1
                logger.info(f"✅ Объявление {banner_id} {'[DRY RUN] ' if dry_run else ''}отключено")
            else:
                failed_count += 1
                logger.error(f"❌ Не удалось отключить объявление {banner_id}: {result.get('error', 'Unknown error')}")

            results.append({
                "banner_id": banner_id,
                "banner_name": banner_name,
                "ad_group_id": ad_group_id,
                "spent": spent,
                "success": result.get("success", False),
                "skipped": False,
                "error": result.get("error") if not result.get("success") else None
            })

        # Пауза между запросами для соблюдения rate limits
        if i < len(unprofitable_banners):  # Не делаем паузу после последнего объявления
            time.sleep(SLEEP_BETWEEN_CALLS)
    
    logger.info("="*80)
    logger.info(f"🎯 {'[DRY RUN] ' if dry_run else ''}Итоги отключения объявлений:")
    logger.info(f"✅ {'Было бы отключено' if dry_run else 'Отключено'}: {disabled_count}")
    logger.info(f"❌ Ошибок: {failed_count}")
    logger.info(f"📊 Всего обработано: {len(unprofitable_banners)}")
    logger.info("="*80)
    
    return {
        "disabled": disabled_count,
        "failed": failed_count,
        "total": len(unprofitable_banners),
        "results": results,
        "dry_run": dry_run
    }

# ===================== ОСНОВНАЯ ЛОГИКА =====================

def analyze_account(account_name: str, access_token: str, config: dict):
    """Анализирует один кабинет VK Ads"""
    
    logger.info("="*100)
    logger.info(f"📊 НАЧИНАЕМ АНАЛИЗ КАБИНЕТА: {account_name}")
    logger.info("="*100)
    
    try:
        # Запускаем триггер обновления статистики перед анализом
        trigger_config = config.get("statistics_trigger", {}).copy()
        account_trigger_id = config.get("account_trigger_id")
        
        if account_trigger_id:
            trigger_config["group_id"] = account_trigger_id
            logger.info(f"🎯 Используем индивидуальный триггер для кабинета {account_name}: группа {account_trigger_id}")
        else:
            trigger_config["enabled"] = False
            logger.info(f"⚠️ Для кабинета {account_name} триггер не настроен - пропускаем обновление статистики")
            
        trigger_result = trigger_statistics_refresh(access_token, BASE_URL, trigger_config)
        if not trigger_result.get("success") and not trigger_result.get("skipped"):
            logger.warning(f"⚠️ Триггер обновления статистики не сработал: {trigger_result.get('error')}")
            logger.info("🔄 Продолжаем анализ без триггера...")
        
        # Получаем индивидуальный лимит для кабинета или используем глобальный
        spent_limit = config.get("account_spent_limit", SPENT_LIMIT_RUB)
        
        # Определяем период анализа
        today = date.today()
        date_from = _iso(today - timedelta(days=LOOKBACK_DAYS))
        date_to = _iso(today)
        
        logger.info(f"🏢 Кабинет: {account_name}")
        logger.info(f"📅 Анализируем период: {date_from} — {date_to} ({LOOKBACK_DAYS} дней)")
        logger.info(f"💰 Лимит расходов: {spent_limit}₽")
        
        # Загружаем активные объявления (фильтрация на сервере)
        banners = get_banners_active(access_token, BASE_URL)
        logger.info(f"✅ [{account_name}] Получено активных объявлений с сервера: {len(banners)}")
        
        # Извлекаем ID активных объявлений для фильтрации статистики
        banner_ids = [b.get("id") for b in banners if b.get("id")]
        logger.info(f"🎯 [{account_name}] Будем запрашивать статистику только для {len(banner_ids)} активных объявлений")
        
        # Загружаем статистику только для активных объявлений
        items = get_banners_stats_day(access_token, BASE_URL, date_from, date_to, banner_ids=banner_ids, metrics="base")
        stats_by_bid = aggregate_stats_by_banner(items)
        
        # Подготовка белого списка (глобальный) — берем из отдельного файла
        whitelist_raw = WHITELIST.get("banners_whitelist", []) if isinstance(WHITELIST, dict) else []
        whitelist_set = set()
        for v in (whitelist_raw or []):
            try:
                whitelist_set.add(int(v))
            except Exception:
                continue

        # Анализируем объявления
        logger.info(f"📊 АНАЛИЗ РАСХОДОВ ПО АКТИВНЫМ ОБЪЯВЛЕНИЯМ КАБИНЕТА: {account_name}")
        logger.info("="*80)

        over_limit = []
        under_limit = []
        no_activity = []
        whitelisted = []
        
        for b in banners:
            bid = b.get("id")
            name = b.get("name", "Unknown")
            status = b.get("status", "N/A")
            ad_group_id = b.get("ad_group_id", "N/A")
            moderation_status = b.get("moderation_status", "N/A")

            # delivery.status берём безопасно  
            delivery = b.get("delivery")
            if isinstance(delivery, dict):
                delivery_status = delivery.get("status", "N/A")
            elif isinstance(delivery, str):
                delivery_status = delivery
            else:
                delivery_status = "N/A"

            # Проверяем белый список: если ID в whitelist — пропускаем анализ и не считаем убыточным
            if bid in whitelist_set:
                whitelisted.append({
                    "id": bid, "name": name, "spent":  stats_by_bid.get(bid, {}).get('spent', 0.0),
                    "clicks": stats_by_bid.get(bid, {}).get('clicks', 0.0), "shows": stats_by_bid.get(bid, {}).get('shows', 0.0),
                    "vk_goals": stats_by_bid.get(bid, {}).get('vk_goals', 0.0),
                    "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id,
                    "moderation_status": moderation_status, "account": account_name
                })
                logger.info(f"🔔 [{account_name}] Пропускаем объявление {bid} — в белом списке")
                continue

            # Получаем статистику по объявлению
            stats = stats_by_bid.get(bid, {"spent": 0.0, "clicks": 0.0, "shows": 0.0, "vk_goals": 0.0})
            spent = stats.get("spent", 0.0)
            clicks = stats.get("clicks", 0.0)
            shows = stats.get("shows", 0.0)
            vk_goals = stats.get("vk_goals", 0.0)
            
            # Категоризируем объявления по новой логике
            if spent >= spent_limit and vk_goals == 0:
                # Убыточное объявление: потратило >= лимита но не дало результата
                over_limit.append({
                    "id": bid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id, 
                    "moderation_status": moderation_status, "account": account_name
                })
                logger.info(f"🔴 [{account_name}] УБЫТОЧНОЕ ОБЪЯВЛЕНИЕ: [{bid}] {name} (группа {ad_group_id})")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (>={spent_limit}₽) без результата")
                
            elif vk_goals >= 1:
                # Эффективное объявление: дало результат (неважно сколько потратило)
                under_limit.append({
                    "id": bid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id,
                    "moderation_status": moderation_status, "account": account_name
                })
                logger.info(f"🟢 [{account_name}] ЭФФЕКТИВНОЕ ОБЪЯВЛЕНИЕ: [{bid}] {name} (группа {ad_group_id})")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ → {int(vk_goals)} VK целей ✅")
                
            elif spent > 0:
                # Объявление с тратами но без результата (< лимита)
                no_activity.append({
                    "id": bid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id,
                    "moderation_status": moderation_status, "account": account_name
                })
                logger.info(f"⚠️ [{account_name}] ТЕСТИРУЕТСЯ: [{bid}] {name} (группа {ad_group_id})")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (< {spent_limit}₽) без результата пока")
                
            else:
                # Объявления без трат
                no_activity.append({
                    "id": bid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id,
                    "moderation_status": moderation_status, "account": account_name
                })

        # Итоговая статистика по кабинету
        logger.info("="*80)
        logger.info(f"📈 ИТОГОВАЯ СТАТИСТИКА ПО КАБИНЕТУ: {account_name}")
        logger.info("="*80)
        logger.info(f"🔴 Убыточных объявлений (>={spent_limit}₽ без результата): {len(over_limit)}")
        logger.info(f"🟢 Эффективных объявлений (с VK целями): {len(under_limit)}")
        logger.info(f"⚠️ Тестируемых/неактивных объявлений: {len(no_activity)}")
        logger.info(f"📊 Всего активных объявлений: {len(banners)}")
        
        # Считаем общие траты и VK цели
        total_spent = sum(b["spent"] for b in over_limit + under_limit)
        total_vk_goals = sum(b["vk_goals"] for b in over_limit + under_limit)
        
        logger.info(f"💰 [{account_name}] Общие расходы за {LOOKBACK_DAYS} дней: {total_spent:.2f}₽")
        logger.info(f"🎯 [{account_name}] Общие VK цели за {LOOKBACK_DAYS} дней: {int(total_vk_goals)}")
        
        if over_limit:
            over_limit_spent = sum(b["spent"] for b in over_limit)
            logger.info(f"🔴 [{account_name}] Расходы убыточных объявлений: {over_limit_spent:.2f}₽ (потрачено впустую)")
        
        if under_limit:
            under_limit_spent = sum(b["spent"] for b in under_limit)
            under_limit_vk_goals = sum(b["vk_goals"] for b in under_limit)
            avg_cost_per_goal = under_limit_spent / under_limit_vk_goals if under_limit_vk_goals > 0 else 0
            logger.info(f"🟢 [{account_name}] Расходы эффективных объявлений: {under_limit_spent:.2f}₽ → {int(under_limit_vk_goals)} целей")
            logger.info(f"🟢 [{account_name}] Средняя стоимость VK цели: {avg_cost_per_goal:.2f}₽")

        # Отключаем убыточные объявления
        disable_results = None
        if over_limit:
            logger.info(f"🛠 ОТКЛЮЧЕНИЕ УБЫТОЧНЫХ ОБЪЯВЛЕНИЙ КАБИНЕТА: {account_name}")
            logger.info("="*80)
            
            disable_results = disable_unprofitable_banners(access_token, BASE_URL, over_limit, DRY_RUN)
        
        # Отправляем уведомления об отключении в Telegram (ТОЛЬКО если есть убыточные объявления)
        try:
            if over_limit:  # ✅ ОТПРАВЛЯЕМ ТОЛЬКО если есть убыточные объявления
                avg_cost_per_goal = total_spent / total_vk_goals if total_vk_goals > 0 else 0
                account_messages = format_telegram_account_statistics(
                    account_name=account_name,
                    unprofitable_count=len(over_limit),
                    effective_count=len(under_limit),
                    testing_count=len(no_activity),
                    total_count=len(banners),
                    total_spent=total_spent,
                    total_goals=int(total_vk_goals),
                    avg_cost=avg_cost_per_goal,
                    lookback_days=LOOKBACK_DAYS,
                    disable_results=disable_results,
                    unprofitable_groups=over_limit  # Оставляем имя параметра для совместимости с telegram_notify
                )
                
                # Отправляем каждое сообщение отдельно
                for i, message in enumerate(account_messages):
                    send_telegram_message(config, message)
                    # Небольшая пауза между сообщениями чтобы не флудить (кроме последнего)
                    if i < len(account_messages) - 1:
                        time.sleep(1)
            else:
                logger.info(f"✅ [{account_name}] Убыточных объявлений нет - уведомления не отправляются")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления по кабинету {account_name}: {e}")
            
        logger.info(f"✅ [{account_name}] Анализ кабинета завершен!")
        
        return {
            "account_name": account_name,
            "over_limit": over_limit,
            "under_limit": under_limit,
            "no_activity": no_activity,
            "total_spent": total_spent,
            "total_vk_goals": int(total_vk_goals),
            "spent_limit": spent_limit,
            "disable_results": disable_results,
            "date_from": date_from,
            "date_to": date_to
        }
        
    except Exception as e:
        logger.error(f"💥 [{account_name}] ОШИБКА АНАЛИЗА КАБИНЕТА: {e}")
        logger.exception("Детали ошибки:")
        raise

def main():
    # Загружаем конфигурацию
    config = load_config()
    
    # Определяем тип анализа
    extra_days = int(os.environ.get('VK_EXTRA_LOOKBACK_DAYS', '0'))
    base_lookback = config["analysis_settings"]["lookback_days"]
    
    if extra_days > 0:
        analysis_type = f"🔍 РАСШИРЕННЫЙ АНАЛИЗ (+{extra_days} дней к базовым {base_lookback})"
        logger.info(analysis_type)
    else:
        analysis_type = "📊 СТАНДАРТНЫЙ АНАЛИЗ"
        logger.info(analysis_type)
    
    logger.info("📊 Запуск VK Ads Manager — анализ активных объявлений для нескольких кабинетов")
    logger.info(f"📋 Найдено кабинетов для анализа: {len(ACCOUNTS)}")
    
    for account_name, account_config in ACCOUNTS.items():
        if isinstance(account_config, dict):
            trigger_info = f" (триггер: {account_config.get('trigger', 'не настроен')})" if account_config.get('trigger') else " (без триггера)"
            logger.info(f"  • {account_name}{trigger_info}")
        else:
            logger.info(f"  • {account_name} (старый формат конфига)")
    
    # Загружаем конфигурацию для Telegram
    config = load_config()
    
    # ❌ УБРАЛИ: Не отправляем уведомление о начале анализа
    # Оставляем только оповещения об отключении компаний
    
    # Результаты по всем кабинетам
    all_results = []
    total_unprofitable = 0
    total_effective = 0
    total_testing = 0
    total_spent_all = 0
    total_goals_all = 0
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Отправляем уведомление о начале анализа (только одно сообщение)
    # Не отправляем дополнительное сообщение о стандартном анализе
    
    try:
        # Анализируем каждый кабинет
        for account_name, account_config in ACCOUNTS.items():
            try:
                # Извлекаем API токен из новой структуры
                access_token = account_config.get("api") if isinstance(account_config, dict) else account_config
                
                # Добавляем информацию о триггере и лимите в общий конфиг для конкретного кабинета
                account_full_config = config.copy()
                if isinstance(account_config, dict):
                    if account_config.get("trigger"):
                        account_full_config["account_trigger_id"] = account_config["trigger"]
                    else:
                        account_full_config["account_trigger_id"] = None
                    
                    # Добавляем индивидуальный лимит для кабинета, если указан
                    if "spent_limit_rub" in account_config:
                        account_full_config["account_spent_limit"] = account_config["spent_limit_rub"]
                else:
                    account_full_config["account_trigger_id"] = None
                    
                account_results = analyze_account(account_name, access_token, account_full_config)
                all_results.append(account_results)
                logger.info(f"✅ [{account_name}] Анализ кабинета завершен!")
                
                # Суммируем статистику
                total_unprofitable += len(account_results["over_limit"])
                total_effective += len(account_results["under_limit"])
                total_testing += len(account_results["no_activity"])
                total_spent_all += account_results["total_spent"]
                total_goals_all += account_results["total_vk_goals"]
            except Exception as e:
                logger.error(f"💥 ОШИБКА В КАБИНЕТЕ [{account_name}]: {e}")
                logger.error("Детали ошибки:")
                logger.error(traceback.format_exc())
                send_telegram_error(f"Ошибка в кабинете '{account_name}': {e}\n\nПродолжаем анализ остальных кабинетов...")
                # Не останавливаем выполнение, продолжаем с другими кабинетами
        
        # Сохраняем сводные результаты по всем кабинетам
        logger.info("="*100)
        logger.info("📊 СВОДНАЯ СТАТИСТИКА ПО ВСЕМ КАБИНЕТАМ:")
        logger.info("="*100)
        
        logger.info(f"🏢 Проанализировано кабинетов: {len(ACCOUNTS)}")
        logger.info(f"🔴 Всего убыточных объявлений: {total_unprofitable}")
        logger.info(f"🟢 Всего эффективных объявлений: {total_effective}")
        logger.info(f"⚠️ Всего тестируемых/неактивных объявлений: {total_testing}")
        logger.info(f"💰 Общие расходы по всем кабинетам: {total_spent_all:.2f}₽")
        logger.info(f"🎯 Общие VK цели по всем кабинетам: {total_goals_all}")
        
        if total_goals_all > 0:
            avg_cost_all = total_spent_all / total_goals_all
            logger.info(f"💎 Средняя стоимость VK цели по всем кабинетам: {avg_cost_all:.2f}₽")
        
        # Создаем сводный файл результатов
        summary_results = {
            "analysis_date": datetime.now().isoformat(),
            "period": f"{all_results[0]['date_from']} to {all_results[0]['date_to']}",
            "spent_limit_rub_default": SPENT_LIMIT_RUB,
            "total_accounts": len(ACCOUNTS),
            "summary": {
                "total_unprofitable_banners": total_unprofitable,
                "total_effective_banners": total_effective,
                "total_testing_banners": total_testing,
                "total_spent": total_spent_all,
                "total_vk_goals": total_goals_all,
                "avg_cost_per_goal": total_spent_all / total_goals_all if total_goals_all > 0 else 0
            },
            "accounts": {}
        }
        
        # Собираем все убыточные объявления
        all_unprofitable = []
        
        for result in all_results:
            account_name = result["account_name"]
            summary_results["accounts"][account_name] = {
                "unprofitable_banners": len(result["over_limit"]),
                "effective_banners": len(result["under_limit"]),
                "testing_banners": len(result["no_activity"]),
                "spent": result["total_spent"],
                "vk_goals": result["total_vk_goals"],
                "spent_limit_rub": result.get("spent_limit", SPENT_LIMIT_RUB)
            }
            all_unprofitable.extend(result["over_limit"])
        
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        # Сохраняем сводный анализ
        summary_file = os.path.join("data", "vk_summary_analysis.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_results, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Сводный анализ сохранен в {summary_file}")
        
        # Сохраняем все убыточные объявления
        if all_unprofitable:
            # Собираем информацию о лимитах для каждого кабинета
            account_limits = {}
            for acc_name, acc_cfg in ACCOUNTS.items():
                if isinstance(acc_cfg, dict) and "spent_limit_rub" in acc_cfg:
                    account_limits[acc_name] = acc_cfg["spent_limit_rub"]
                else:
                    account_limits[acc_name] = SPENT_LIMIT_RUB
            
            unprofitable_data = {
                "analysis_date": datetime.now().isoformat(),
                "period": f"{all_results[0]['date_from']} to {all_results[0]['date_to']}",
                "spent_limits_by_account": account_limits,
                "spent_limit_rub_default": SPENT_LIMIT_RUB,
                "criteria": "spent >= limit AND vk_goals = 0",
                "total_accounts": len(ACCOUNTS),
                "total_unprofitable_banners": len(all_unprofitable),
                "total_wasted_budget": sum(banner.get('spent', 0) for banner in all_unprofitable),
                "banners_to_disable": all_unprofitable
            }
            
            unprofitable_file = os.path.join("data", "vk_all_unprofitable_banners.json")
            with open(unprofitable_file, "w", encoding="utf-8") as f:
                json.dump(unprofitable_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"🔴 Все убыточные объявления сохранены в {unprofitable_file} ({len(all_unprofitable)} шт.)")
            logger.info(f"💸 Общий размер потерянного бюджета: {sum(banner.get('spent', 0) for banner in all_unprofitable):.2f}₽")
        
        logger.info("🎉 Анализ всех кабинетов завершен!")

    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детали ошибки:")
        
        # Отправляем уведомление об ошибке в Telegram
        try:
            config = load_config()
            error_message = f"<b>ОШИБКА</b>\n\n{str(e)}\n{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            send_telegram_message(config, error_message)
        except:
            pass  # Игнорируем ошибки отправки уведомлений об ошибках
        
        raise


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    main()