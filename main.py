import requests
import json
import time
import logging
import os
from datetime import date, timedelta, datetime

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
        
        logger.info("🎉 Анализ завершен!")

    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детали ошибки:")
        raise


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    main()