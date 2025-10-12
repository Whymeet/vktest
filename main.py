import requests
import json
import time
import logging
import os
from datetime import date, timedelta, datetime
from logging.handlers import TimedRotatingFileHandler

# ===================== НАСТРОЙКИ =====================

def load_config():
    """Загружает конфигурацию из data/config.json"""
    config_path = os.path.join("data", "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError("❌ Файл data/config.json не найден! Создайте файл с настройками API.")
    except json.JSONDecodeError as e:
        raise ValueError(f"❌ Ошибка в data/config.json: {e}")

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
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler для файла с ротацией по дням (DEBUG и выше)
    log_file = os.path.join(log_dir, "vk_ads_manager.log")
    file_handler = TimedRotatingFileHandler(
        log_file, 
        when='midnight', 
        interval=1, 
        backupCount=30,  # Храним логи за 30 дней
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"
    logger.addHandler(file_handler)
    
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

def get_ad_groups_stats_day(token: str, date_from: str, date_to: str, group_ids: list = None, metrics: str = "all"):
    """
    Эндпоинт: GET /statistics/ad_groups/day.json
    Возвращает JSON с массивом items, где по каждой группе есть rows по дням и агрегаты в total.*.
    """
    if group_ids:
        ids_str = ",".join(map(str, group_ids))
        logger.info(f"📊 Запрашиваем статистику за период {date_from} - {date_to} для {len(group_ids)} групп")
        logger.debug(f"ID групп: {ids_str[:100]}{'...' if len(ids_str) > 100 else ''}")
    else:
        logger.info(f"📊 Запрашиваем статистику за период {date_from} - {date_to} для ВСЕХ групп")
    
    url = f"{BASE_URL}/statistics/ad_groups/day.json"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metrics,
    }
    
    # Добавляем фильтр по ID групп если они указаны
    if group_ids:
        params["ids"] = ",".join(map(str, group_ids))
        logger.debug(f"🔧 Добавлен фильтр ids: {params['ids']}")
    
    try:
        logger.debug(f"🌐 Отправляем запрос к {url} с параметрами: {params}")
        r = requests.get(url, headers=_headers(token), params=params, timeout=30)
        
        if r.status_code != 200:
            logger.error(f"❌ Ошибка HTTP {r.status_code} при получении статистики: {r.text[:200]}")
            raise RuntimeError(f"[stats day] HTTP {r.status_code}: {r.text}")
        
        items = r.json().get("items", [])
        logger.info(f"✅ Получена статистика по {len(items)} группам")
        
        return items
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при получении статистики: {e}")
        raise


def aggregate_stats_by_group(items):
    """
    Сворачивает статистику к виду:
    { group_id: {"spent": float, "clicks": float, "shows": float} }
    """
    logger.info("🔢 Агрегируем статистику по группам")
    agg = {}

    for item in items:
        gid = item.get("id")
        rows = item.get("rows", []) or []
        if gid is None:
            continue

        spent_sum = 0.0
        clicks_sum = 0.0
        shows_sum = 0.0

        for row in rows:
            day_spent = _dget(row, "total.base.spent", 0.0)
            day_clicks = _dget(row, "total.base.clicks", 0.0)
            day_shows = _dget(row, "total.base.shows", 0.0)
            
            spent_sum  += day_spent
            clicks_sum += day_clicks
            shows_sum  += day_shows

        agg[gid] = {
            "spent": spent_sum,
            "clicks": clicks_sum,
            "shows": shows_sum,
        }

    logger.info(f"✅ Агрегировано {len(agg)} групп")
    return agg


# ===================== ОСНОВНАЯ ЛОГИКА =====================

def main():
    logger.info("🚀 Запуск VK Ads Manager — анализ активных групп и их расходов")
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
        items = get_ad_groups_stats_day(ACCESS_TOKEN, date_from, date_to, group_ids=group_ids, metrics="all")
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
            stats = stats_by_gid.get(gid, {"spent": 0.0, "clicks": 0.0, "shows": 0.0})
            spent = stats.get("spent", 0.0)
            clicks = stats.get("clicks", 0.0)
            shows = stats.get("shows", 0.0)
            
            # Категorizируем группы
            if spent > SPENT_LIMIT_RUB:
                over_limit.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"🔴 ПРЕВЫШЕН ЛИМИТ: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (>{SPENT_LIMIT_RUB}₽)")
                logger.info(f"    📊 Активность: {clicks} кликов, {shows} показов")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")
                
            elif spent > 0:
                under_limit.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"🟢 В ПРЕДЕЛАХ ЛИМИТА: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (<={SPENT_LIMIT_RUB}₽)")
                logger.info(f"    📊 Активность: {clicks} кликов, {shows} показов")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")
                
            else:
                no_activity.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id
                })
                logger.info(f"⚪ БЕЗ АКТИВНОСТИ: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: 0₽")
                logger.info(f"    🏷️ Статус: {status} | Доставка: {delivery_status} | Кампания: {ad_plan_id}")
                logger.info("")

        # Итоговая статистика
        logger.info("="*80)
        logger.info("📈 ИТОГОВАЯ СТАТИСТИКА:")
        logger.info("="*80)
        logger.info(f"🔴 Групп превысивших лимит ({SPENT_LIMIT_RUB}₽): {len(over_limit)}")
        logger.info(f"🟢 Групп в пределах лимита: {len(under_limit)}")
        logger.info(f"⚪ Групп без активности: {len(no_activity)}")
        logger.info(f"📊 Всего активных групп: {len(groups)}")
        
        # Считаем общие траты
        total_spent = sum(g["spent"] for g in over_limit + under_limit)
        logger.info(f"💰 Общие расходы за {LOOKBACK_DAYS} дней: {total_spent:.2f}₽")
        
        if over_limit:
            over_limit_spent = sum(g["spent"] for g in over_limit)  
            logger.info(f"🔴 Расходы групп над лимитом: {over_limit_spent:.2f}₽")
        
        # Сохраняем детальные результаты
        results = {
            "analysis_date": datetime.now().isoformat(),
            "period": f"{date_from} to {date_to}",
            "spent_limit_rub": SPENT_LIMIT_RUB,
            "summary": {
                "total_groups": len(groups),
                "over_limit": len(over_limit),
                "under_limit": len(under_limit),
                "no_activity": len(no_activity),
                "total_spent": total_spent
            },
            "groups": {
                "over_limit": over_limit,
                "under_limit": under_limit,
                "no_activity": no_activity
            }
        }
        
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        analysis_file = os.path.join("data", "vk_groups_analysis.json")
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Анализ сохранен в {analysis_file}")
        logger.info("🎉 Анализ завершен!")

    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детали ошибки:")
        raise


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    main()