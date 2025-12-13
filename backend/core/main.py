"""
VK Ads Manager - Асинхронная версия с параллельной обработкой кабинетов.
Использует asyncio + aiohttp для настоящей параллельности.
Версия с PostgreSQL базой данных.
"""
import asyncio
import aiohttp
import json
import logging
import os
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent.parent))

# Импортируем асинхронные функции VK API
from utils.vk_api_async import (
    get_banners_active,
    get_banners_stats_day,
    disable_banners_batch,
    trigger_statistics_refresh,
)

# Импортируем функции Telegram
from bot.telegram_notify import send_telegram_message, format_telegram_account_statistics

# Импортируем работу с БД
from database import SessionLocal, init_db
from database import crud
from database.models import DisableRule

# Импортируем Leadstech для получения дохода
from leadstech.analyzer import LeadstechClient, LeadstechClientConfig, aggregate_leadstech_by_banner


# ===================== НАСТРОЙКИ ИЗ БД =====================

def load_config_from_db():
    """Загружает конфигурацию из PostgreSQL"""
    db = SessionLocal()
    try:
        # Получаем настройки
        all_settings = crud.get_all_settings(db)
        analysis_settings = all_settings.get('analysis_settings', {})
        telegram_settings = all_settings.get('telegram', {})
        statistics_trigger = all_settings.get('statistics_trigger', {})

        # Получаем аккаунты
        accounts_db = crud.get_accounts(db)
        accounts = {}
        for acc in accounts_db:
            accounts[acc.name] = {
                "api": acc.api_token,
                "trigger": acc.client_id,
                "spent_limit_rub": 100.0  # Default, можно потом добавить в модель
            }

        config = {
            "vk_ads_api": {
                "base_url": "https://ads.vk.com/api/v2",
                "accounts": accounts
            },
            "analysis_settings": {
                "lookback_days": analysis_settings.get("lookback_days", 10),
                "spent_limit_rub": analysis_settings.get("spent_limit_rub", 100.0),
                "dry_run": analysis_settings.get("dry_run", False),
                "sleep_between_calls": analysis_settings.get("sleep_between_calls", 3.0)
            },
            "telegram": {
                "bot_token": telegram_settings.get("bot_token", ""),
                "chat_id": telegram_settings.get("chat_id", []),
                "enabled": telegram_settings.get("enabled", False)
            },
            "statistics_trigger": {
                "enabled": statistics_trigger.get("enabled", False),
                "wait_seconds": statistics_trigger.get("wait_seconds", 10)
            }
        }
        return config
    finally:
        db.close()


def load_whitelist_from_db():
    """Загружает белый список из БД"""
    db = SessionLocal()
    try:
        banner_ids = crud.get_whitelist(db)
        return {"banners_whitelist": banner_ids}
    finally:
        db.close()


# Инициализируем БД
init_db()

# Загружаем конфигурацию
config = load_config_from_db()

BASE_URL = config["vk_ads_api"]["base_url"]
ACCOUNTS = config["vk_ads_api"]["accounts"]

analysis_settings = config.get("analysis_settings", {})

LOOKBACK_DAYS = analysis_settings.get("lookback_days", 10)
# поддержка расширенного анализа через переменную окружения
extra_days_env = int(os.environ.get("VK_EXTRA_LOOKBACK_DAYS", "0"))
if extra_days_env > 0:
    LOOKBACK_DAYS += extra_days_env

SPENT_LIMIT_RUB = analysis_settings.get("spent_limit_rub", 50.0)
DRY_RUN = analysis_settings.get("dry_run", True)
SLEEP_BETWEEN_CALLS = analysis_settings.get("sleep_between_calls", 0.25)


# ===================== НАСТРОЙКА ЛОГИРОВАНИЯ =====================

def setup_logging():
    """Настройка логирования в консоль и файл"""
    project_root = Path(__file__).parent.parent
    log_dir = project_root / "logs"
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("vk_ads_manager")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"vk_ads_manager_{timestamp}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(f"📝 Логирование в файл: {log_file}")
    return logger


# Инициализируем логгер
logger = setup_logging()

# Загружаем белый список из БД
WHITELIST = load_whitelist_from_db()
logger.info(f"🔒 Загружен whitelist из БД: {len(WHITELIST.get('banners_whitelist', []))} глобальных ID")


# ===================== ВСПОМОГАТЕЛЬНОЕ =====================

def _iso(d: date) -> str:
    return d.isoformat()


async def log_disabled_banners_to_db(
    over_limit: list,
    disable_results: dict | None,
    account_name: str,
    lookback_days: int,
    date_from: str,
    date_to: str,
    is_dry_run: bool = False
):
    """
    Логирует все отключённые баннеры в базу данных.
    Выполняется асинхронно в отдельном потоке чтобы не блокировать event loop.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _log_to_db():
        db = SessionLocal()
        try:
            logged_count = 0
            for banner_data in over_limit:
                banner_id = banner_data.get("id")

                # Проверяем результат отключения
                disable_success = True
                if disable_results and isinstance(disable_results, dict):
                    result = disable_results.get(str(banner_id)) or disable_results.get(banner_id)
                    if result:
                        disable_success = result.get("success", True)

                # Получаем причину отключения (название правила)
                matched_rule = banner_data.get("matched_rule", "Правило не указано")

                try:
                    crud.log_disabled_banner(
                        db=db,
                        banner_data=banner_data,
                        account_name=account_name,
                        lookback_days=lookback_days,
                        date_from=date_from,
                        date_to=date_to,
                        is_dry_run=is_dry_run,
                        disable_success=disable_success,
                        reason=f"Сработало правило: {matched_rule}"
                    )
                    logged_count += 1
                except Exception as e:
                    logger.error(f"❌ Ошибка записи в БД для баннера {banner_id}: {e}")

            logger.info(f"💾 [{account_name}] Записано в БД: {logged_count} отключённых баннеров")
        except Exception as e:
            logger.error(f"❌ Ошибка при логировании в БД: {e}")
        finally:
            db.close()

    # Выполняем запись в БД в thread pool чтобы не блокировать async
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, _log_to_db)


async def save_account_stats_to_db(
    account_name: str,
    stats_date: str,
    over_limit: list,
    under_limit: list,
    no_activity: list,
    total_spent: float,
    total_conversions: int,
    lookback_days: int,
    vk_account_id: int = None
):
    """
    Сохраняет статистику по кабинету в БД.
    Выполняется асинхронно в отдельном потоке.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _save_stats():
        db = SessionLocal()
        try:
            # Подсчитываем статистику
            total_clicks = sum(b.get("clicks", 0) for b in over_limit + under_limit + no_activity)
            total_shows = sum(b.get("shows", 0) for b in over_limit + under_limit + no_activity)

            crud.save_account_stats(
                db=db,
                account_name=account_name,
                stats_date=stats_date,
                active_banners=len(over_limit) + len(under_limit) + len(no_activity),
                disabled_banners=len(over_limit),
                over_limit_banners=len(over_limit),
                under_limit_banners=len(under_limit),
                no_activity_banners=len(no_activity),
                total_spend=total_spent,
                total_clicks=int(total_clicks),
                total_shows=int(total_shows),
                total_conversions=total_conversions,
                lookback_days=lookback_days,
                vk_account_id=vk_account_id
            )
            logger.info(f"📊 [{account_name}] Статистика сохранена в БД")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения статистики в БД: {e}")
        finally:
            db.close()

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, _save_stats)


def _prepare_whitelist_set() -> set:
    """Подготавливает set из whitelist для быстрой проверки"""
    whitelist_raw = WHITELIST.get("banners_whitelist", []) if isinstance(WHITELIST, dict) else []
    whitelist_set = set()
    for v in whitelist_raw:
        try:
            whitelist_set.add(int(v))
        except Exception:
            continue
    return whitelist_set


# ===================== АНАЛИЗ ОДНОГО КАБИНЕТА =====================

async def analyze_account(
    session: aiohttp.ClientSession,
    account_name: str,
    access_token: str,
    account_config: dict,
) -> dict | None:
    """Анализирует один кабинет VK Ads асинхронно"""

    logger.info("=" * 100)
    logger.info(f"📊 НАЧИНАЕМ АНАЛИЗ КАБИНЕТА: {account_name}")
    logger.info("=" * 100)

    try:
        # Запускаем триггер обновления статистики
        trigger_config = account_config.get("statistics_trigger", {}).copy()
        account_trigger_id = account_config.get("account_trigger_id")

        if account_trigger_id:
            trigger_config["group_id"] = account_trigger_id
            trigger_config["enabled"] = True
            logger.info(f"🎯 Используем индивидуальный триггер для кабинета {account_name}: группа {account_trigger_id}")
        else:
            trigger_config["enabled"] = False
            logger.info(f"⚠️ Для кабинета {account_name} триггер не настроен — пропускаем обновление статистики")

        trigger_result = await trigger_statistics_refresh(session, access_token, BASE_URL, trigger_config)
        if not trigger_result.get("success") and not trigger_result.get("skipped"):
            logger.warning(f"⚠️ Триггер обновления статистики не сработал: {trigger_result.get('error')}")

        # Загружаем правила для этого кабинета из БД
        db = SessionLocal()
        try:
            account_rules = crud.get_rules_for_account_by_name(db, account_name, enabled_only=True)
            logger.info(f"📋 [{account_name}] Загружено правил отключения: {len(account_rules)}")
            for rule in account_rules:
                conditions_str = ", ".join([
                    f"{c.metric} {c.operator} {c.value}" for c in rule.conditions
                ])
                logger.info(f"   📌 Правило \"{rule.name}\": {conditions_str}")
            
            # Получаем конфигурацию Leadstech и кабинет для получения дохода
            from database.models import Account
            lt_config = crud.get_leadstech_config(db)
            lt_cabinet = None
            if lt_config:
                account_obj = db.query(Account).filter(Account.name == account_name).first()
                if account_obj:
                    lt_cabinet = crud.get_leadstech_cabinet_by_account(db, account_obj.id)
        finally:
            db.close()

        # Если нет правил для этого кабинета, пропускаем его
        if not account_rules:
            logger.warning(f"⚠️ [{account_name}] Нет активных правил отключения — кабинет пропущен")
            return {
                "account_name": account_name,
                "over_limit": [],
                "under_limit": [],
                "no_activity": [],
                "total_spent": 0.0,
                "total_vk_goals": 0,
                "matched_rules": [],
                "disable_results": None,
                "date_from": _iso(date.today() - timedelta(days=LOOKBACK_DAYS)),
                "date_to": _iso(date.today()),
                "skipped": True
            }

        # Определяем период анализа
        today = date.today()
        date_from = _iso(today - timedelta(days=LOOKBACK_DAYS))
        date_to = _iso(today)

        logger.info(f"🏢 Кабинет: {account_name}")
        logger.info(f"📅 Анализируем период: {date_from} — {date_to} ({LOOKBACK_DAYS} дней)")

        # Загружаем активные объявления
        banners = await get_banners_active(
            session, access_token, BASE_URL,
            sleep_between_calls=SLEEP_BETWEEN_CALLS
        )
        logger.info(f"✅ [{account_name}] Получено активных объявлений: {len(banners)}")

        if len(banners) == 0:
            logger.warning(f"⚠️ [{account_name}] Не найдено активных объявлений!")

        # Извлекаем ID активных объявлений
        banner_ids = [b.get("id") for b in banners if b.get("id")]

        # Загружаем статистику параллельно
        stats_by_bid = await get_banners_stats_day(
            session, access_token, BASE_URL, date_from, date_to,
            banner_ids=banner_ids, metrics="base",
            sleep_between_calls=SLEEP_BETWEEN_CALLS
        )

        # Получаем доход из Leadstech для расчета ROI
        revenue_by_bid = {}
        if lt_config and lt_cabinet and lt_cabinet.enabled:
            try:
                logger.info(f"💰 [{account_name}] Получаем доход из Leadstech (label={lt_cabinet.leadstech_label})...")
                lt_client_cfg = LeadstechClientConfig(
                    base_url=lt_config.base_url,
                    login=lt_config.login,
                    password=lt_config.password
                )
                lt_client = LeadstechClient(lt_client_cfg)
                
                # Получаем данные из Leadstech
                date_from_obj = date.fromisoformat(date_from)
                date_to_obj = date.fromisoformat(date_to)
                lt_rows = lt_client.get_stat_by_subid(
                    date_from=date_from_obj,
                    date_to=date_to_obj,
                    sub1_value=lt_cabinet.leadstech_label,
                    subs_field=lt_config.banner_sub_field or "sub4"
                )
                
                # Агрегируем по баннерам
                lt_by_banner = aggregate_leadstech_by_banner(lt_rows, lt_config.banner_sub_field or "sub4")
                
                # Создаем словарь revenue_by_bid
                for banner_id, lt_data in lt_by_banner.items():
                    revenue_by_bid[banner_id] = float(lt_data.get("lt_revenue", 0.0))
                
                logger.info(f"💰 [{account_name}] Получен доход для {len(revenue_by_bid)} баннеров из Leadstech")
            except Exception as e:
                logger.warning(f"⚠️ [{account_name}] Ошибка получения дохода из Leadstech: {e}")
                revenue_by_bid = {}

        # Подготовка белого списка
        whitelist_set = _prepare_whitelist_set()

        # Анализируем объявления
        logger.info(f"📊 АНАЛИЗ РАСХОДОВ ПО АКТИВНЫМ ОБЪЯВЛЕНИЯМ КАБИНЕТА: {account_name}")
        logger.info("=" * 80)

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

            delivery = b.get("delivery")
            if isinstance(delivery, dict):
                delivery_status = delivery.get("status", "N/A")
            elif isinstance(delivery, str):
                delivery_status = delivery
            else:
                delivery_status = "N/A"

            # Проверяем белый список
            if bid in whitelist_set:
                whitelisted.append({
                    "id": bid, "name": name, "spent": stats_by_bid.get(bid, {}).get('spent', 0.0),
                    "clicks": stats_by_bid.get(bid, {}).get('clicks', 0.0),
                    "shows": stats_by_bid.get(bid, {}).get('shows', 0.0),
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
            
            # Получаем доход из Leadstech (если есть)
            revenue = revenue_by_bid.get(bid, 0.0)
            
            # Рассчитываем ROI: (доход - потрачено) / потрачено * 100
            # Если дохода нет или объявление не в Leadstech - ROI = 0
            roi = 0.0
            if spent > 0:
                roi = ((revenue - spent) / spent) * 100.0
            elif revenue == 0:
                # Если дохода нет и не потрачено - ROI = 0
                roi = 0.0

            banner_data = {
                "id": bid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                "revenue": revenue, "roi": roi,
                "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id,
                "moderation_status": moderation_status, "account": account_name
            }

            # Категоризируем объявления с помощью системы правил
            # Подготавливаем stats для проверки правил (нормализуем поля)
            rule_stats = {
                "goals": vk_goals,
                "vk_goals": vk_goals,
                "spent": spent,
                "clicks": clicks,
                "shows": shows,
                "ctr": (clicks / shows * 100) if shows > 0 else 0,
                "cpc": (spent / clicks) if clicks > 0 else float('inf'),
                "cost_per_goal": (spent / vk_goals) if vk_goals > 0 else float('inf'),
                "roi": roi,  # ROI в процентах
            }
            
            # Проверяем соответствие правилам отключения
            matched_rule = crud.check_banner_against_rules(rule_stats, account_rules)
            
            if matched_rule:
                # Объявление подпадает под правило отключения
                banner_data["matched_rule"] = matched_rule.name
                banner_data["matched_rule_id"] = matched_rule.id
                over_limit.append(banner_data)
                reason = crud.format_rule_match_reason(matched_rule, rule_stats)
                logger.info(f"🔴 [{account_name}] УБЫТОЧНОЕ: [{bid}] {name}")
                logger.info(f"   {reason.replace(chr(10), chr(10) + '   ')}")

            elif vk_goals >= 1:
                under_limit.append(banner_data)
                logger.info(f"🟢 [{account_name}] ЭФФЕКТИВНОЕ: [{bid}] {name} ({int(vk_goals)} VK целей)")

            elif spent > 0:
                no_activity.append(banner_data)
                # Логируем почему не подпало под правило
                logger.debug(f"⚠️ [{account_name}] ТЕСТИРУЕТСЯ: [{bid}] {name}")
                logger.debug(f"   spent={spent:.2f}₽, goals={vk_goals}, clicks={clicks}, shows={shows}")
                logger.info(f"⚠️ [{account_name}] ТЕСТИРУЕТСЯ: [{bid}] {name} ({spent:.2f}₽)")

            else:
                no_activity.append(banner_data)

        # Итоговая статистика
        logger.info("=" * 80)
        logger.info(f"📈 ИТОГОВАЯ СТАТИСТИКА ПО КАБИНЕТУ: {account_name}")
        logger.info(f"🔴 Убыточных (по правилам): {len(over_limit)}")
        logger.info(f"🟢 Эффективных: {len(under_limit)}")
        logger.info(f"⚠️ Тестируемых/неактивных: {len(no_activity)}")
        logger.info(f"📊 Всего активных: {len(banners)}")

        total_spent = sum(b["spent"] for b in over_limit + under_limit + no_activity)
        total_vk_goals = sum(b["vk_goals"] for b in over_limit + under_limit + no_activity)

        logger.info(f"💰 [{account_name}] Общие расходы: {total_spent:.2f}₽")
        logger.info(f"🎯 [{account_name}] Общие VK цели: {int(total_vk_goals)}")

        # Отключаем убыточные объявления ПАРАЛЛЕЛЬНО
        disable_results = None
        if over_limit:
            logger.info(f"🛠 ОТКЛЮЧЕНИЕ УБЫТОЧНЫХ ОБЪЯВЛЕНИЙ КАБИНЕТА: {account_name}")
            logger.info("=" * 80)

            disable_results = await disable_banners_batch(
                session, access_token, BASE_URL, over_limit,
                dry_run=DRY_RUN,
                whitelist_ids=whitelist_set,
                concurrency=5  # До 5 параллельных отключений
            )

            # Логируем отключённые баннеры в БД
            await log_disabled_banners_to_db(
                over_limit=over_limit,
                disable_results=disable_results,
                account_name=account_name,
                lookback_days=LOOKBACK_DAYS,
                date_from=date_from,
                date_to=date_to,
                is_dry_run=DRY_RUN
            )

        # Сохраняем статистику по кабинету в БД
        await save_account_stats_to_db(
            account_name=account_name,
            stats_date=date_to,  # Дата = последний день периода
            over_limit=over_limit,
            under_limit=under_limit,
            no_activity=no_activity,
            total_spent=total_spent,
            total_conversions=int(total_vk_goals),
            lookback_days=LOOKBACK_DAYS
        )

        logger.info(f"✅ [{account_name}] Анализ кабинета завершен!")

        return {
            "account_name": account_name,
            "over_limit": over_limit,
            "under_limit": under_limit,
            "no_activity": no_activity,
            "total_spent": total_spent,
            "total_vk_goals": int(total_vk_goals),
            "rules_count": len(account_rules),
            "disable_results": disable_results,
            "date_from": date_from,
            "date_to": date_to
        }

    except Exception as e:
        logger.error(f"💥 [{account_name}] ОШИБКА АНАЛИЗА КАБИНЕТА: {e}")
        logger.exception("Детали ошибки:")
        return None


def _prepare_account_config(global_config: dict, account_config) -> dict:
    """Готовит конфиг для конкретного кабинета"""
    account_full_config = dict(global_config)

    if isinstance(account_config, dict):
        trigger_id = account_config.get("trigger")
        account_full_config["account_trigger_id"] = trigger_id if trigger_id else None
    else:
        account_full_config["account_trigger_id"] = None

    return account_full_config


# ===================== TELEGRAM УВЕДОМЛЕНИЯ =====================

async def send_telegram_notifications_async(config: dict, all_results: list[dict]):
    """
    Отправляет все уведомления в Telegram В КОНЦЕ после обработки всех кабинетов.
    """
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enabled", False):
        logger.info("📱 Telegram уведомления отключены")
        return

    # Собираем все сообщения для отправки
    all_messages = []

    for result in all_results:
        if not result:
            continue

        over_limit = result.get("over_limit", [])
        if not over_limit:
            continue  # Отправляем только если есть убыточные

        account_name = result["account_name"]
        under_limit = result.get("under_limit", [])
        no_activity = result.get("no_activity", [])
        total_spent = result.get("total_spent", 0)
        total_vk_goals = result.get("total_vk_goals", 0)
        disable_results = result.get("disable_results")

        avg_cost = total_spent / total_vk_goals if total_vk_goals > 0 else 0

        # Формируем сообщения для этого кабинета
        account_messages = format_telegram_account_statistics(
            account_name=account_name,
            unprofitable_count=len(over_limit),
            effective_count=len(under_limit),
            testing_count=len(no_activity),
            total_count=len(over_limit) + len(under_limit) + len(no_activity),
            total_spent=total_spent,
            total_goals=int(total_vk_goals),
            avg_cost=avg_cost,
            lookback_days=LOOKBACK_DAYS,
            disable_results=disable_results,
            unprofitable_groups=over_limit
        )

        all_messages.extend(account_messages)

    if not all_messages:
        logger.info("📱 Нет убыточных объявлений — уведомления не отправляются")
        return

    logger.info(f"📨 Отправляем {len(all_messages)} сообщений в Telegram...")

    # Отправляем все сообщения с небольшой задержкой между ними
    for i, message in enumerate(all_messages, 1):
        try:
            send_telegram_message(config, message)
            logger.info(f"📨 Отправлено сообщение {i}/{len(all_messages)}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения {i}: {e}")

        # Задержка между сообщениями чтобы не флудить
        if i < len(all_messages):
            await asyncio.sleep(1)

    logger.info("✅ Все Telegram сообщения отправлены")


async def send_telegram_error_async(config: dict, error_message: str):
    """Отправляет сообщение об ошибке в Telegram"""
    try:
        send_telegram_message(config, f"<b>Ошибка</b>\n\n{error_message}")
    except Exception as e:
        logger.error(f"❌ Не удалось отправить ошибку в Telegram: {e}")


# ===================== ОСНОВНАЯ ЛОГИКА =====================

async def main_async():
    """Главная асинхронная функция"""
    try:
        # Загружаем конфигурацию из БД
        config = load_config_from_db()

        # Определяем тип анализа
        extra_days = int(os.environ.get("VK_EXTRA_LOOKBACK_DAYS", "0"))
        base_lookback = config.get("analysis_settings", {}).get("lookback_days", LOOKBACK_DAYS)

        if extra_days > 0:
            analysis_type = f"🔍 РАСШИРЕННЫЙ АНАЛИЗ (+{extra_days} дней к базовым {base_lookback})"
        else:
            analysis_type = "📊 СТАНДАРТНЫЙ АНАЛИЗ"

        logger.info(analysis_type)
        logger.info("📊 Запуск VK Ads Manager — АСИНХРОННАЯ ВЕРСИЯ")

        accounts = config["vk_ads_api"]["accounts"]
        logger.info(f"📊 Загружено кабинетов: {len(accounts)}")
        logger.info(f"📊 Список кабинетов: {list(accounts.keys())}")

        # Создаем aiohttp сессию для всех запросов
        connector = aiohttp.TCPConnector(limit=20)  # Лимит одновременных соединений
        async with aiohttp.ClientSession(connector=connector) as session:

            # Создаем задачи для ВСЕХ кабинетов
            tasks = []
            for account_name, account_cfg in accounts.items():
                access_token = (
                    account_cfg.get("api")
                    if isinstance(account_cfg, dict)
                    else account_cfg
                )
                if not access_token:
                    logger.error(f"❌ Не настроен api-токен для кабинета {account_name}")
                    continue

                account_full_config = _prepare_account_config(config, account_cfg)

                # Создаем задачу для анализа кабинета
                task = asyncio.create_task(
                    analyze_account(session, account_name, access_token, account_full_config),
                    name=f"analyze_{account_name}"
                )
                tasks.append(task)

            logger.info(f"🚀 Запускаем {len(tasks)} кабинетов ПАРАЛЛЕЛЬНО")
            logger.info("=" * 80)

            # Запускаем ВСЕ кабинеты параллельно и ждем завершения
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Обрабатываем результаты
            all_results: list[dict] = []
            total_unprofitable = total_effective = total_testing = 0
            total_spent_all = total_goals_all = 0.0

            for i, result in enumerate(results):
                task_name = tasks[i].get_name()

                if isinstance(result, Exception):
                    logger.error(f"💥 Ошибка в задаче {task_name}: {result}")
                    continue

                if not result:
                    logger.warning(f"⚠️ Задача {task_name} вернула пустой результат")
                    continue

                all_results.append(result)
                total_unprofitable += len(result.get("over_limit", []))
                total_effective += len(result.get("under_limit", []))
                total_testing += len(result.get("no_activity", []))
                total_spent_all += result.get("total_spent", 0.0)
                total_goals_all += result.get("total_vk_goals", 0.0)

                logger.info(
                    f"📊 Завершён кабинет '{result['account_name']}': "
                    f"{len(result.get('over_limit', []))} убыточных, "
                    f"{len(result.get('under_limit', []))} эффективных"
                )

        if not all_results:
            logger.error("❌ Ни один кабинет не был успешно проанализирован")
            await send_telegram_error_async(config, "❌ Анализ не выполнен: все кабинеты вернули ошибки")
            return

        # Итоговая статистика
        logger.info("=" * 80)
        logger.info("📈 ИТОГОВАЯ СВОДКА ПО ВСЕМ КАБИНЕТАМ:")
        logger.info(f"🔴 Всего убыточных объявлений: {total_unprofitable}")
        logger.info(f"🟢 Всего эффективных объявлений: {total_effective}")
        logger.info(f"⚠️ Всего тестируемых/неактивных: {total_testing}")
        logger.info(f"💰 Общие расходы: {total_spent_all:.2f}₽")
        logger.info(f"🎯 Общие VK цели: {int(total_goals_all)}")
        if total_goals_all > 0:
            logger.info(f"📊 Средняя стоимость цели: {total_spent_all / total_goals_all:.2f}₽")
        logger.info("=" * 80)

        # Формируем сводный JSON
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
                "total_vk_goals": int(total_goals_all),
                "avg_cost_per_goal": (
                    total_spent_all / total_goals_all if total_goals_all > 0 else 0
                ),
            },
            "accounts": {},
        }

        # Собираем все убыточные объявления
        all_unprofitable: list[dict] = []

        for result in all_results:
            account_name = result["account_name"]
            summary_results["accounts"][account_name] = {
                "unprofitable_banners": len(result.get("over_limit", [])),
                "effective_banners": len(result.get("under_limit", [])),
                "testing_banners": len(result.get("no_activity", [])),
                "spent": result.get("total_spent", 0.0),
                "vk_goals": int(result.get("total_vk_goals", 0.0)),
                "spent_limit_rub": result.get("spent_limit", SPENT_LIMIT_RUB),
            }
            all_unprofitable.extend(result.get("over_limit", []))

        # Сохраняем файлы
        project_root = Path(__file__).parent.parent
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        summary_path = data_dir / "vk_summary_analysis.json"
        unprofitable_path = data_dir / "vk_all_unprofitable_banners.json"

        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_results, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Сводка анализа сохранена в {summary_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сводки: {e}")

        try:
            with open(unprofitable_path, "w", encoding="utf-8") as f:
                json.dump(all_unprofitable, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Убыточные объявления сохранены в {unprofitable_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения списка убыточных: {e}")

        # Отправляем ВСЕ уведомления в Telegram В КОНЦЕ
        logger.info("=" * 80)
        logger.info("📨 ОТПРАВКА УВЕДОМЛЕНИЙ В TELEGRAM")
        logger.info("=" * 80)
        await send_telegram_notifications_async(config, all_results)

        logger.info("=" * 80)
        logger.info("✅ АНАЛИЗ ЗАВЕРШЕН УСПЕШНО")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.warning("🛑 Получено прерывание от пользователя (Ctrl+C)")
        logger.info("👋 Работа завершена по запросу пользователя")
    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.exception("Детали ошибки:")
        try:
            config = load_config_from_db()
            await send_telegram_error_async(config, f"Критическая ошибка: {e}")
        except Exception:
            pass
        raise


def main():
    """Точка входа — запускает асинхронный main"""
    asyncio.run(main_async())


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    main()
