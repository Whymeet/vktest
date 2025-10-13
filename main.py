
import requests
import json
import time
import logging
import os
from datetime import date, timedelta, datetime

# Импортируем функции Telegram
from telegram_notify import send_telegram_message, format_telegram_account_statistics

# ===================== TELEGRAM ФУНКЦИИ =====================


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
BASE_URL = config["vk_ads_api"]["base_url"]
ACCOUNTS = config["vk_ads_api"]["accounts"]

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

def get_ad_groups_active(token: str, base_url: str, fields: str = "id,name,status,delivery,ad_plan_id", limit: int = 200):
    """
    Грузим все группы и фильтруем по активным.
    Эндпоинт: GET /ad_groups.json?fields=...
    """
    logger.info("🔄 Начинаем загрузку рекламных групп из VK Ads API")
    logger.debug(f"Параметры: fields={fields}, limit={limit}")
    
    url = f"{base_url}/ad_groups.json"
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

def get_ad_groups_stats_day(token: str, base_url: str, date_from: str, date_to: str, group_ids: list = None, metrics: str = "base"):
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
    
    url = f"{base_url}/statistics/ad_groups/day.json"
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

def disable_ad_group(token: str, base_url: str, group_id: int, dry_run: bool = True):
    """
    Отключает рекламную группу, изменяя статус с 'active' на 'blocked'
    POST /ad_groups/{group_id}.json с телом {"status": "blocked"}
    """
    if dry_run:
        logger.info(f"🔸 [DRY RUN] Группа {group_id} была бы отключена (active → blocked)")
        return {"success": True, "dry_run": True}
    
    url = f"{base_url}/ad_groups/{group_id}.json"
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

def disable_unprofitable_groups(token: str, base_url: str, unprofitable_groups: list, dry_run: bool = True):
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
        result = disable_ad_group(token, base_url, group_id, dry_run)
        
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

def analyze_account(account_name: str, access_token: str, config: dict):
    """Анализирует один кабинет VK Ads"""
    
    logger.info("="*100)
    logger.info(f"📊 НАЧИНАЕМ АНАЛИЗ КАБИНЕТА: {account_name}")
    logger.info("="*100)
    
    try:
        # Определяем период анализа
        today = date.today()
        date_from = _iso(today - timedelta(days=LOOKBACK_DAYS))
        date_to = _iso(today)
        
        logger.info(f"🏢 Кабинет: {account_name}")
        logger.info(f"📅 Анализируем период: {date_from} — {date_to} ({LOOKBACK_DAYS} дней)")
        logger.info(f"💰 Лимит расходов: {SPENT_LIMIT_RUB}₽")
        
        # Загружаем активные группы (фильтрация на сервере)
        groups = get_ad_groups_active(access_token, BASE_URL)
        logger.info(f"✅ [{account_name}] Получено активных групп с сервера: {len(groups)}")
        
        # Извлекаем ID активных групп для фильтрации статистики
        group_ids = [g.get("id") for g in groups if g.get("id")]
        logger.info(f"🎯 [{account_name}] Будем запрашивать статистику только для {len(group_ids)} активных групп")
        
        # Загружаем статистику только для активных групп
        items = get_ad_groups_stats_day(access_token, BASE_URL, date_from, date_to, group_ids=group_ids, metrics="base")
        stats_by_gid = aggregate_stats_by_group(items)
        
        # Анализируем группы
        logger.info(f"📊 АНАЛИЗ РАСХОДОВ ПО АКТИВНЫМ ГРУППАМ КАБИНЕТА: {account_name}")
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
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id, "account": account_name
                })
                logger.info(f"🔴 [{account_name}] УБЫТОЧНАЯ ГРУППА: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (>={SPENT_LIMIT_RUB}₽) без результата")
                
            elif vk_goals >= 1:
                # Эффективная группа: дала результат (неважно сколько потратила)
                under_limit.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id, "account": account_name
                })
                logger.info(f"🟢 [{account_name}] ЭФФЕКТИВНАЯ ГРУППА: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ → {int(vk_goals)} VK целей ✅")
                
            elif spent > 0:
                # Группа с тратами но без результата (< 40₽)
                no_activity.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id, "account": account_name
                })
                logger.info(f"⚠️ [{account_name}] ТЕСТИРУЕТСЯ: [{gid}] {name}")
                logger.info(f"    💰 Потрачено: {spent:.2f}₽ (< {SPENT_LIMIT_RUB}₽) без результата пока")
                
            else:
                # Группы без трат
                no_activity.append({
                    "id": gid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                    "status": status, "delivery": delivery_status, "ad_plan_id": ad_plan_id, "account": account_name
                })

        # Итоговая статистика по кабинету
        logger.info("="*80)
        logger.info(f"📈 ИТОГОВАЯ СТАТИСТИКА ПО КАБИНЕТУ: {account_name}")
        logger.info("="*80)
        logger.info(f"🔴 Убыточных групп (>={SPENT_LIMIT_RUB}₽ без результата): {len(over_limit)}")
        logger.info(f"🟢 Эффективных групп (с VK целями): {len(under_limit)}")
        logger.info(f"⚠️ Тестируемых/неактивных групп: {len(no_activity)}")
        logger.info(f"📊 Всего активных групп: {len(groups)}")
        
        # Считаем общие траты и VK цели
        total_spent = sum(g["spent"] for g in over_limit + under_limit)
        total_vk_goals = sum(g["vk_goals"] for g in over_limit + under_limit)
        
        logger.info(f"💰 [{account_name}] Общие расходы за {LOOKBACK_DAYS} дней: {total_spent:.2f}₽")
        logger.info(f"🎯 [{account_name}] Общие VK цели за {LOOKBACK_DAYS} дней: {int(total_vk_goals)}")
        
        if over_limit:
            over_limit_spent = sum(g["spent"] for g in over_limit)
            logger.info(f"🔴 [{account_name}] Расходы убыточных групп: {over_limit_spent:.2f}₽ (потрачено впустую)")
        
        if under_limit:
            under_limit_spent = sum(g["spent"] for g in under_limit)
            under_limit_vk_goals = sum(g["vk_goals"] for g in under_limit)
            avg_cost_per_goal = under_limit_spent / under_limit_vk_goals if under_limit_vk_goals > 0 else 0
            logger.info(f"🟢 [{account_name}] Расходы эффективных групп: {under_limit_spent:.2f}₽ → {int(under_limit_vk_goals)} целей")
            logger.info(f"🟢 [{account_name}] Средняя стоимость VK цели: {avg_cost_per_goal:.2f}₽")

        # Отключаем убыточные группы
        disable_results = None
        if over_limit:
            logger.info(f"🛠 ОТКЛЮЧЕНИЕ УБЫТОЧНЫХ ГРУПП КАБИНЕТА: {account_name}")
            logger.info("="*80)
            
            disable_results = disable_unprofitable_groups(access_token, BASE_URL, over_limit, DRY_RUN)
        
        # Отправляем уведомление по этому кабинету в Telegram
        try:
            avg_cost_per_goal = total_spent / total_vk_goals if total_vk_goals > 0 else 0
            account_message = format_telegram_account_statistics(
                account_name=account_name,
                unprofitable_count=len(over_limit),
                effective_count=len(under_limit),
                testing_count=len(no_activity),
                total_count=len(groups),
                total_spent=total_spent,
                total_goals=int(total_vk_goals),
                avg_cost=avg_cost_per_goal,
                lookback_days=LOOKBACK_DAYS,
                disable_results=disable_results
            )
            send_telegram_message(config, account_message)
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
            "disable_results": disable_results,
            "date_from": date_from,
            "date_to": date_to
        }
        
    except Exception as e:
        logger.error(f"💥 [{account_name}] ОШИБКА АНАЛИЗА КАБИНЕТА: {e}")
        logger.exception("Детали ошибки:")
        raise

def main():
    logger.info(" Запуск VK Ads Manager — анализ активных групп для нескольких кабинетов")
    logger.info(f"📋 Найдено кабинетов для анализа: {len(ACCOUNTS)}")
    
    for account_name in ACCOUNTS.keys():
        logger.info(f"  • {account_name}")
    
    # Загружаем конфигурацию для Telegram
    config = load_config()
    
    # Отправляем уведомление о начале анализа
    accounts_list = ", ".join(ACCOUNTS.keys())
    start_message = f"🚀 <b>VK Ads - Начало анализа</b>\n\n🏢 Кабинеты: {accounts_list}\n📅 Период: {LOOKBACK_DAYS} дн.\n💰 Лимит: {SPENT_LIMIT_RUB}₽\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    send_telegram_message(config, start_message)
    
    # Результаты по всем кабинетам
    all_results = []
    total_unprofitable = 0
    total_effective = 0
    total_testing = 0
    total_spent_all = 0
    total_goals_all = 0
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Отправляем уведомление о начале анализа
    start_message = f"🚀 <b>VK Ads - Начало анализа</b>\n\n📅 Период: {LOOKBACK_DAYS} дн.\n💰 Лимит: {SPENT_LIMIT_RUB}₽\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    send_telegram_message(config, start_message)
    
    try:
        # Анализируем каждый кабинет
        for account_name, access_token in ACCOUNTS.items():
            account_results = analyze_account(account_name, access_token, config)
            all_results.append(account_results)
            
            # Суммируем статистику
            total_unprofitable += len(account_results["over_limit"])
            total_effective += len(account_results["under_limit"])
            total_testing += len(account_results["no_activity"])
            total_spent_all += account_results["total_spent"]
            total_goals_all += account_results["total_vk_goals"]
        
        # Сохраняем сводные результаты по всем кабинетам
        logger.info("="*100)
        logger.info("� СВОДНАЯ СТАТИСТИКА ПО ВСЕМ КАБИНЕТАМ:")
        logger.info("="*100)
        
        logger.info(f"🏢 Проанализировано кабинетов: {len(ACCOUNTS)}")
        logger.info(f"🔴 Всего убыточных групп: {total_unprofitable}")
        logger.info(f"🟢 Всего эффективных групп: {total_effective}")
        logger.info(f"⚠️ Всего тестируемых/неактивных групп: {total_testing}")
        logger.info(f"💰 Общие расходы по всем кабинетам: {total_spent_all:.2f}₽")
        logger.info(f"🎯 Общие VK цели по всем кабинетам: {total_goals_all}")
        
        if total_goals_all > 0:
            avg_cost_all = total_spent_all / total_goals_all
            logger.info(f"� Средняя стоимость VK цели по всем кабинетам: {avg_cost_all:.2f}₽")
        
        # Создаем сводный файл результатов
        summary_results = {
            "analysis_date": datetime.now().isoformat(),
            "period": f"{all_results[0]['date_from']} to {all_results[0]['date_to']}",
            "spent_limit_rub": SPENT_LIMIT_RUB,
            "total_accounts": len(ACCOUNTS),
            "summary": {
                "total_unprofitable_groups": total_unprofitable,
                "total_effective_groups": total_effective,
                "total_testing_groups": total_testing,
                "total_spent": total_spent_all,
                "total_vk_goals": total_goals_all,
                "avg_cost_per_goal": total_spent_all / total_goals_all if total_goals_all > 0 else 0
            },
            "accounts": {}
        }
        
        # Собираем все убыточные группы
        all_unprofitable = []
        
        for result in all_results:
            account_name = result["account_name"]
            summary_results["accounts"][account_name] = {
                "unprofitable_groups": len(result["over_limit"]),
                "effective_groups": len(result["under_limit"]),
                "testing_groups": len(result["no_activity"]),
                "spent": result["total_spent"],
                "vk_goals": result["total_vk_goals"]
            }
            all_unprofitable.extend(result["over_limit"])
        
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        # Сохраняем сводный анализ
        summary_file = os.path.join("data", "vk_summary_analysis.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_results, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Сводный анализ сохранен в {summary_file}")
        
        # Сохраняем все убыточные группы
        if all_unprofitable:
            unprofitable_data = {
                "analysis_date": datetime.now().isoformat(),
                "period": f"{all_results[0]['date_from']} to {all_results[0]['date_to']}",
                "spent_limit_rub": SPENT_LIMIT_RUB,
                "criteria": "spent >= limit AND vk_goals = 0",
                "total_accounts": len(ACCOUNTS),
                "total_unprofitable_groups": len(all_unprofitable),
                "total_wasted_budget": sum(group.get('spent', 0) for group in all_unprofitable),
                "groups_to_disable": all_unprofitable
            }
            
            unprofitable_file = os.path.join("data", "vk_all_unprofitable_groups.json")
            with open(unprofitable_file, "w", encoding="utf-8") as f:
                json.dump(unprofitable_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"🔴 Все убыточные группы сохранены в {unprofitable_file} ({len(all_unprofitable)} шт.)")
            logger.info(f"💸 Общий размер потерянного бюджета: {sum(group.get('spent', 0) for group in all_unprofitable):.2f}₽")
        
        logger.info("🎉 Анализ всех кабинетов завершен!")

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