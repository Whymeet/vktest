import requests
import json
import time
import logging
import os
from datetime import date, timedelta, datetime

# ===================== TELEGRAM ФУНКЦИИ =====================

def send_telegram_message(config, message):
    """Отправляет сообщение в Telegram"""
    telegram_config = config.get("telegram", {})
    
    if not telegram_config.get("enabled", False):
        logging.info("📱 Telegram уведомления отключены")
        return False
        
    bot_token = telegram_config.get("bot_token")
    chat_id = telegram_config.get("chat_id")
    
    if not bot_token or not chat_id:
        logging.warning("⚠️ Telegram не настроен: отсутствует bot_token или chat_id")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            logging.info("📱 Сообщение отправлено в Telegram")
            return True
        else:
            logging.error(f"❌ Ошибка отправки в Telegram: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ Исключение при отправке в Telegram: {str(e)}")
        return False

def format_telegram_statistics(unprofitable_count, effective_count, testing_count, 
                              total_count, total_spent, total_goals, avg_cost, lookback_days):
    """Форматирует статистику для Telegram"""
    message = f"""📊 <b>VK Ads - Анализ групп завершен</b>

🔴 Убыточных групп (≥40₽ без результата): <b>{unprofitable_count}</b>
🟢 Эффективных групп (с VK целями): <b>{effective_count}</b>
⚠️ Тестируемых/неактивных групп: <b>{testing_count}</b>
📈 Всего активных групп: <b>{total_count}</b>

💰 Общие расходы за {lookback_days} дн.: <b>{total_spent:.2f}₽</b>
🎯 Общие VK цели за {lookback_days} дн.: <b>{total_goals}</b>
💡 Средняя стоимость VK цели: <b>{avg_cost:.2f}₽</b>

⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"""
    
    return message

def format_telegram_unprofitable_groups(unprofitable_groups):
    """Форматирует список убыточных групп для Telegram, разбивая на сообщения по 10 групп"""
    if not unprofitable_groups:
        return ["✅ <b>Убыточных групп не найдено!</b>"]
    
    messages = []
    groups_per_message = 10
    total_groups = len(unprofitable_groups)
    
    # Разбиваем группы на части по 10 штук
    for batch_start in range(0, total_groups, groups_per_message):
        batch_end = min(batch_start + groups_per_message, total_groups)
        batch_groups = unprofitable_groups[batch_start:batch_end]
        
        batch_num = (batch_start // groups_per_message) + 1
        total_batches = (total_groups + groups_per_message - 1) // groups_per_message
        
        # Заголовок для каждого сообщения
        if total_batches > 1:
            message = f"🔴 <b>Убыточные группы (часть {batch_num}/{total_batches}):</b>\n\n"
        else:
            message = f"🔴 <b>Убыточные группы ({total_groups} шт.):</b>\n\n"
        
        # Добавляем группы в сообщение
        for i, group in enumerate(batch_groups, batch_start + 1):
            group_id = group.get("id", "N/A")
            group_name = group.get("name", "Без названия")[:30]  # Ограничиваем длину
            spent = group.get("spent", 0)
            
            message += f"{i}. 🆔 <code>{group_id}</code> {group_name}\n"
            message += f"   💸 Потрачено: <b>{spent:.2f}₽</b>\n\n"
        
        messages.append(message)
    
    return messages

def format_telegram_disable_results(disable_results):
    """Форматирует результаты отключения групп для Telegram"""
    if not disable_results:
        return "ℹ️ <b>Отключение групп не выполнялось</b>"
    
    dry_run = disable_results.get("dry_run", True)
    disabled = disable_results.get("disabled", 0)
    failed = disable_results.get("failed", 0)
    total = disable_results.get("total", 0)
    
    if dry_run:
        message = f"🔸 <b>Режим тестирования (DRY RUN)</b>\n\n"
        message += f"✅ Было бы отключено: <b>{disabled}</b> групп\n"
        message += f"❌ Ошибок: <b>{failed}</b>\n"
        message += f"📊 Всего обработано: <b>{total}</b>\n\n"
        message += f"💡 Для реального отключения установите dry_run: false в config.json"
    else:
        message = f"🔄 <b>Отключение групп завершено</b>\n\n"
        message += f"✅ Отключено: <b>{disabled}</b> групп\n"
        message += f"❌ Ошибок: <b>{failed}</b>\n"
        message += f"📊 Всего обработано: <b>{total}</b>"
    
    return message

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

# Загружаем конфигурацию
config = load_config()

# VK Ads API настройки
ACCESS_TOKEN = config["vk_ads_api"]["access_token"]
BASE_URL = config["vk_ads_api"]["base_url"]

# Настройки анализа
LOOKBACK_DAYS = config["analysis_settings"]["lookback_days"]           # окно в днях
SPENT_LIMIT_RUB = config["analysis_settings"]["spent_limit_rub"]       # порог расходов в рублях
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


# ===================== ЗАГРУЗКА АКТИВНЫХ ГРУПП =====================

def get_ad_groups_active(token: str, fields: str = "id,name,status,delivery,ad_plan_id", limit: int = 200):
    """
    Грузим все группы и фильтруем по активным.
    Эндпоинт: GET /ad_groups.json?fields=...
    """
    logger.info("🔄 Начинаем загрузку рекламных групп из VK Ads API")
    logger.debug(f"Параметры: fields={fields}, limit={limit}")
    
    url = f"{BASE_URL}/ad_groups.json"
    offset = 0
    items_all = []
    page_num = 1

    while True:
        logger.debug(f"📥 Загружаем страницу {page_num} (offset={offset})")
        params = {
            "fields": fields, 
            "limit": limit, 
            "offset": offset,
            "_status": "active"  # Фильтруем только активные группы на стороне сервера
        }
        
        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=20)
            if r.status_code != 200:
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке групп: {r.text[:200]}")
                raise RuntimeError(f"[ad_groups] HTTP {r.status_code}: {r.text}")
            
            payload = r.json()
            items = payload.get("items", [])
            items_all.extend(items)
            
            logger.debug(f"✓ Страница {page_num}: получено {len(items)} групп")

            # пагинация
            if len(items) < limit:
                logger.debug(f"📄 Достигнута последняя страница ({len(items)} < {limit})")
                break
                
            offset += limit
            page_num += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
            
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка сети при загрузке групп: {e}")
            raise

    logger.info(f"✅ Загружено {len(items_all)} активных групп за {page_num} страниц")
    logger.info("ℹ️ Фильтрация выполнена на стороне сервера VK API (_status=active)")
    
    # Все загруженные группы уже активные благодаря серверной фильтрации
    logger.debug("📋 Примеры загруженных активных групп:")
    for i, g in enumerate(items_all[:3]):  # Показываем первые 3
        logger.debug(f"  • [{g.get('id')}] {g.get('name', 'Unknown')} | status={g.get('status')}")
    
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

def get_ad_groups_stats_day(token: str, date_from: str, date_to: str, group_ids: list = None, metrics: str = "base"):
    """
    GET /statistics/ad_groups/day.json
    Возвращает items с rows по дням и total.* по группе.
    Использует правильный параметр id=123,456,789 (через запятую).
    """
    if group_ids:
        ids_str = ",".join(map(str, group_ids))
        logger.info(f"📊 Запрашиваем статистику за период {date_from} - {date_to} для {len(group_ids)} групп")
        logger.debug(f"🆔 ID групп: {ids_str}")
    else:
        logger.info(f"📊 Запрашиваем статистику за период {date_from} - {date_to} для ВСЕХ групп")
    
    url = f"{BASE_URL}/statistics/ad_groups/day.json"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metrics,
    }
    
    # ✅ Правильный параметр: id (без s) через запятую
    if group_ids:
        params["id"] = ",".join(map(str, group_ids))
        logger.debug(f"🔧 Добавлен фильтр id: {params['id']}")

    try:
        logger.debug(f"🌐 Отправляем запрос к {url} с параметрами: {params}")
        r = requests.get(url, headers=_headers(token), params=params, timeout=30)
        
        if r.status_code != 200:
            logger.error(f"❌ Ошибка HTTP {r.status_code} при получении статистики: {r.text[:200]}")
            raise RuntimeError(f"[stats day] HTTP {r.status_code}: {r.text}")
        
        payload = r.json()
        items = payload.get("items", [])
        logger.info(f"✅ Получена статистика по {len(items)} группам")
        
        # 💾 Сохраняем полный JSON ответ для анализа
        save_raw_statistics_json(payload, date_from, date_to, group_ids)
        
        # Проверяем, что получили именно те группы, которые запрашивали
        if group_ids and items:
            received_ids = [item.get("id") for item in items if item.get("id")]
            logger.debug(f"📋 Получены ID: {received_ids}")
            
        return items
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при получении статистики: {e}")
        raise


def aggregate_stats_by_group(items):
    """
    Извлекает статистику из готовых total данных (суммированных за весь период):
    { group_id: {"spent": float, "clicks": float, "shows": float, "vk_goals": int} }
    """
    logger.info("🔢 Агрегируем статистику по группам")
    agg = {}

    for item in items:
        gid = item.get("id")
        if gid is None:
            continue

        # ✅ Используем готовые total данные вместо суммирования rows
        total = item.get("total", {}).get("base", {})
        
        # Основные метрики из total.base
        spent = _dget(total, "spent", 0.0)
        clicks = _dget(total, "clicks", 0.0)
        shows = _dget(total, "shows", 0.0)
        
        # VK цели из total.base.vk.goals
        vk_goals = _dget(total, "vk.goals", 0.0)

        agg[gid] = {
            "spent": spent,
            "clicks": clicks,
            "shows": shows,
            "vk_goals": vk_goals,  # Только VK цели
        }
        
        logger.debug(f"📋 Группа {gid}: spent={spent}₽, vk_goals={vk_goals}")

    logger.info(f"✅ Агрегировано {len(agg)} групп")
    return agg


# ===================== ОТКЛЮЧЕНИЕ ГРУПП =====================

def disable_ad_group(token: str, group_id: int, dry_run: bool = True):
    """
    Отключает рекламную группу, изменяя статус с 'active' на 'blocked'
    POST /ad_groups/{group_id}.json с телом {"status": "blocked"}
    """
    if dry_run:
        logger.info(f"🔸 [DRY RUN] Группа {group_id} была бы отключена (active → blocked)")
        return {"success": True, "dry_run": True}
    
    url = f"{BASE_URL}/ad_groups/{group_id}.json"
    data = {"status": "blocked"}
    
    try:
        logger.info(f"🔄 Отключаем группу {group_id} (active → blocked)")
        response = requests.post(
            url,
            headers=_headers(token),
            json=data,
            timeout=20
        )
        # VK API возвращает 204 No Content при успешном обновлении статуса
        if response.status_code in (200, 204):
            logger.info(f"✅ Группа {group_id} успешно отключена (HTTP {response.status_code})")
            # Если есть тело, возвращаем его, иначе просто success
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при отключении группы {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при отключении группы {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}

def disable_unprofitable_groups(token: str, unprofitable_groups: list, dry_run: bool = True):
    """
    Отключает все убыточные группы с задержкой между запросами
    """
    if not unprofitable_groups:
        logger.info("✅ Нет убыточных групп для отключения")
        return {"disabled": 0, "failed": 0, "results": []}
    
    logger.info(f"🎯 {'[DRY RUN] ' if dry_run else ''}Начинаем отключение {len(unprofitable_groups)} убыточных групп")
    
    disabled_count = 0
    failed_count = 0
    results = []
    
    for i, group in enumerate(unprofitable_groups, 1):
        group_id = group.get("id")
        group_name = group.get("name", "Unknown")
        spent = group.get("spent", 0)
        
        logger.info(f"📋 [{i}/{len(unprofitable_groups)}] Группа {group_id}: {group_name} (потрачено: {spent:.2f}₽)")
        
        # Отключаем группу
        result = disable_ad_group(token, group_id, dry_run)
        
        if result["success"]:
            disabled_count += 1
            logger.info(f"✅ Группа {group_id} {'[DRY RUN] ' if dry_run else ''}отключена")
        else:
            failed_count += 1
            logger.error(f"❌ Не удалось отключить группу {group_id}: {result.get('error', 'Unknown error')}")
        
        results.append({
            "group_id": group_id,
            "group_name": group_name,
            "spent": spent,
            "success": result["success"],
            "error": result.get("error") if not result["success"] else None
        })
        
        # Пауза между запросами для соблюдения rate limits
        if i < len(unprofitable_groups):  # Не делаем паузу после последней группы
            time.sleep(SLEEP_BETWEEN_CALLS)
    
    logger.info("="*80)
    logger.info(f"🎯 {'[DRY RUN] ' if dry_run else ''}Итоги отключения групп:")
    logger.info(f"✅ {'Было бы отключено' if dry_run else 'Отключено'}: {disabled_count}")
    logger.info(f"❌ Ошибок: {failed_count}")
    logger.info(f"📊 Всего обработано: {len(unprofitable_groups)}")
    logger.info("="*80)
    
    return {
        "disabled": disabled_count,
        "failed": failed_count,
        "total": len(unprofitable_groups),
        "results": results,
        "dry_run": dry_run
    }

# ===================== ОСНОВНАЯ ЛОГИКА =====================

def main():
    logger.info("🚀 Запуск VK Ads Manager — анализ активных групп и их расходов")
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Отправляем уведомление о начале анализа
    start_message = f"🚀 <b>VK Ads - Начало анализа</b>\n\n📅 Период: {LOOKBACK_DAYS} дн.\n💰 Лимит: {SPENT_LIMIT_RUB}₽\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    send_telegram_message(config, start_message)
    
    try:
        # Определяем период анализа
        today = date.today()
        date_from = _iso(today - timedelta(days=LOOKBACK_DAYS))
        date_to = _iso(today)
        
        logger.info(f"📅 Анализируем период: {date_from} — {date_to} ({LOOKBACK_DAYS} дней)")
        logger.info(f"💰 Лимит расходов: {SPENT_LIMIT_RUB}₽")
        
        # Загружаем активные группы (фильтрация на сервере)
        groups = get_ad_groups_active(ACCESS_TOKEN)
        logger.info(f"✅ Получено активных групп с сервера: {len(groups)}")
        
        # Извлекаем ID активных групп для фильтрации статистики
        group_ids = [g.get("id") for g in groups if g.get("id")]
        logger.info(f"🎯 Будем запрашивать статистику только для {len(group_ids)} активных групп")
        logger.debug(f"🆔 ID активных групп: {group_ids[:5]}..." if len(group_ids) > 5 else f"🆔 ID активных групп: {group_ids}")
        
        # Загружаем статистику только для активных групп
        items = get_ad_groups_stats_day(ACCESS_TOKEN, date_from, date_to, group_ids=group_ids, metrics="base")
        stats_by_gid = aggregate_stats_by_group(items)
        
        # Анализируем группы
        logger.info("\n" + "="*80)
        logger.info("📊 АНАЛИЗ РАСХОДОВ ПО АКТИВНЫМ ГРУППАМ:")
        logger.info("="*80)
        
        over_limit = []
        under_limit = []
        no_activity = []
        
        for g in groups:
            gid = g.get("id")
            name = g.get("name", "Unknown")
            status = g.get("status", "N/A")
            ad_plan_id = g.get("ad_plan_id", "N/A")

            # delivery.status берём безопасно  
            delivery = g.get("delivery")
            if isinstance(delivery, dict):
                delivery_status = delivery.get("status", "N/A")
            elif isinstance(delivery, str):
                delivery_status = delivery
            else:
                delivery_status = "N/A"

            # Получаем статистику по группе
            stats = stats_by_gid.get(gid, {"spent": 0.0, "clicks": 0.0, "shows": 0.0, "vk_goals": 0.0})
            spent = stats.get("spent", 0.0)
            clicks = stats.get("clicks", 0.0)
            shows = stats.get("shows", 0.0)
            vk_goals = stats.get("vk_goals", 0.0)
            
            # Категorizируем группы по новой логике
            if spent >= SPENT_LIMIT_RUB and vk_goals == 0:
                # Убыточная группа: потратила >= 40₽ но не дала результата
                over_limit.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"🔴 УБЫТОЧНАЯ ГРУППА: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (>={SPENT_LIMIT_RUB}₽) без результата")
                logger.info(f"    📊 Активность: {clicks} кликов, {shows} показов, {int(vk_goals)} VK целей")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")
                
            elif vk_goals >= 1:
                # Эффективная группа: дала результат (неважно сколько потратила)
                under_limit.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"🟢 ЭФФЕКТИВНАЯ ГРУППА: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ → {int(vk_goals)} VK целей ✅")
                logger.info(f"    📊 Активность: {clicks} кликов, {shows} показов")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")
                
            elif spent > 0:
                # Группа с тратами но без результата (< 40₽)
                no_activity.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"⚠️ ТЕСТИРУЕТСЯ: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (< {SPENT_LIMIT_RUB}₽) без результата пока")
                logger.info(f"    📊 Активность: {clicks} кликов, {shows} показов, {int(vk_goals)} VK целей")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")
                
            else:
                # Группы без трат
                no_activity.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"⚪ БЕЗ АКТИВНОСТИ: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: 0₽")
                logger.info(f"    📊 Активность: {clicks} кликов, {shows} показов, {int(vk_goals)} VK целей")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")

        # Итоговая статистика
        logger.info("="*80)
        logger.info("📈 ИТОГОВАЯ СТАТИСТИКА:")
        logger.info("="*80)
        logger.info(f"🔴 Убыточных групп (>={SPENT_LIMIT_RUB}₽ без результата): {len(over_limit)}")
        logger.info(f"🟢 Эффективных групп (с VK целями): {len(under_limit)}")
        logger.info(f"⚠️ Тестируемых/неактивных групп: {len(no_activity)}")
        logger.info(f"📊 Всего активных групп: {len(groups)}")
        
        # Считаем общие траты и VK цели
        total_spent = sum(g["spent"] for g in over_limit + under_limit)
        total_vk_goals = sum(g["vk_goals"] for g in over_limit + under_limit)
        
        logger.info(f"💰 Общие расходы за {LOOKBACK_DAYS} дней: {total_spent:.2f}₽")
        logger.info(f"🎯 Общие VK цели за {LOOKBACK_DAYS} дней: {int(total_vk_goals)}")
        
        if over_limit:
            over_limit_spent = sum(g["spent"] for g in over_limit)
            over_limit_vk_goals = sum(g["vk_goals"] for g in over_limit)
            logger.info(f"🔴 Расходы убыточных групп: {over_limit_spent:.2f}₽ (потрачено впустую)")
            logger.info(f"🔴 VK цели убыточных групп: {int(over_limit_vk_goals)} (должно быть 0)")
        
        if under_limit:
            under_limit_spent = sum(g["spent"] for g in under_limit)
            under_limit_vk_goals = sum(g["vk_goals"] for g in under_limit)
            avg_cost_per_goal = under_limit_spent / under_limit_vk_goals if under_limit_vk_goals > 0 else 0
            logger.info(f"🟢 Расходы эффективных групп: {under_limit_spent:.2f}₽ → {int(under_limit_vk_goals)} целей")
            logger.info(f"🟢 Средняя стоимость VK цели: {avg_cost_per_goal:.2f}₽")
        
        # Сохраняем детальные результаты
        results = {
            "analysis_date": datetime.now().isoformat(),
            "period": f"{date_from} to {date_to}",
            "spent_limit_rub": SPENT_LIMIT_RUB,
            "summary": {
                "total_groups": len(groups),
                "unprofitable_groups": len(over_limit),  # Убыточные группы 
                "effective_groups": len(under_limit),     # Эффективные группы
                "testing_inactive_groups": len(no_activity),  # Тестируемые/неактивные
                "total_spent": total_spent,
                "total_vk_goals": int(total_vk_goals)
            },
            "groups": {
                "unprofitable": over_limit,      # Убыточные группы (>=40₽ без результата)
                "effective": under_limit,        # Эффективные группы (с VK целями)
                "testing_inactive": no_activity  # Тестируемые/неактивные группы
            }
        }
        
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        analysis_file = os.path.join("data", "vk_groups_analysis.json")
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Анализ сохранен в {analysis_file}")
        
        # Сохранение убыточных групп отдельно для удобного управления
        if over_limit:
            unprofitable_data = {
                "analysis_date": datetime.now().isoformat(),
                "period": f"{date_from} to {date_to}",
                "spent_limit_rub": SPENT_LIMIT_RUB,
                "criteria": "spent >= limit AND vk_goals = 0",
                "total_unprofitable_groups": len(over_limit),
                "total_wasted_budget": sum(group.get('spent', 0) for group in over_limit),
                "groups_to_disable": over_limit
            }
            
            unprofitable_file = os.path.join("data", "vk_unprofitable_groups.json")
            with open(unprofitable_file, "w", encoding="utf-8") as f:
                json.dump(unprofitable_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"🔴 Убыточные группы сохранены в {unprofitable_file} ({len(over_limit)} шт.)")
            logger.info(f"💸 Общий размер потерянного бюджета: {sum(group.get('spent', 0) for group in over_limit):.2f}₽")
        
        # Отключаем убыточные группы
        disable_results = None
        if over_limit:
            logger.info("\n" + "="*80)
            logger.info("🔄 ОТКЛЮЧЕНИЕ УБЫТОЧНЫХ ГРУПП:")
            logger.info("="*80)
            
            disable_results = disable_unprofitable_groups(ACCESS_TOKEN, over_limit, DRY_RUN)
            
            # Сохраняем результаты отключения
            if disable_results:
                disable_file = os.path.join("data", "vk_disable_results.json")
                disable_data = {
                    "disable_date": datetime.now().isoformat(),
                    "dry_run": DRY_RUN,
                    "summary": {
                        "total_groups": disable_results["total"],
                        "disabled_groups": disable_results["disabled"],
                        "failed_groups": disable_results["failed"]
                    },
                    "results": disable_results["results"]
                }
                
                with open(disable_file, "w", encoding="utf-8") as f:
                    json.dump(disable_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"💾 Результаты отключения сохранены в {disable_file}")
        
        logger.info("🎉 Анализ завершен!")
        
        # Отправляем финальную статистику в Telegram
        if under_limit:
            under_limit_spent = sum(g["spent"] for g in under_limit)
            under_limit_vk_goals = sum(g["vk_goals"] for g in under_limit)
            avg_cost_per_goal = under_limit_spent / under_limit_vk_goals if under_limit_vk_goals > 0 else 0
        else:
            avg_cost_per_goal = 0
            
        stats_message = format_telegram_statistics(
            unprofitable_count=len(over_limit),
            effective_count=len(under_limit),
            testing_count=len(no_activity),
            total_count=len(groups),
            total_spent=total_spent,
            total_goals=int(total_vk_goals),
            avg_cost=avg_cost_per_goal,
            lookback_days=LOOKBACK_DAYS
        )
        send_telegram_message(config, stats_message)
        
        # Отправляем список убыточных групп, если они есть
        if over_limit:
            unprofitable_messages = format_telegram_unprofitable_groups(over_limit)
            for message in unprofitable_messages:
                send_telegram_message(config, message)
                # Небольшая пауза между сообщениями чтобы не спамить
                time.sleep(1)
        
        # Отправляем результаты отключения групп
        if disable_results:
            disable_message = format_telegram_disable_results(disable_results)
            send_telegram_message(config, disable_message)

    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детали ошибки:")
        
        # Отправляем уведомление об ошибке в Telegram
        try:
            config = load_config()
            error_message = f"❌ <b>VK Ads - ОШИБКА</b>\n\n💥 {str(e)}\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            send_telegram_message(config, error_message)
        except:
            pass  # Игнорируем ошибки отправки уведомлений об ошибках
        
        raise


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    main()