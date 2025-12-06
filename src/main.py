"""
VK Ads Manager - Асинхронная версия с параллельной обработкой кабинетов.
Использует asyncio + aiohttp для настоящей параллельности.
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


# ===================== НАСТРОЙКИ =====================

def load_config():
    """Загружает конфигурацию из cfg/config.json"""
    project_root = Path(__file__).parent.parent
    config_path = project_root / "cfg" / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError("❌ Файл cfg/config.json не найден! Создайте файл с настройками API.")
    except json.JSONDecodeError as e:
        raise ValueError(f"❌ Ошибка в cfg/config.json: {e}")


def load_whitelist():
    """Загружает белый список из отдельного файла cfg/whitelist.json."""
    project_root = Path(__file__).parent.parent
    wl_path = project_root / "cfg" / "whitelist.json"
    try:
        with open(wl_path, "r", encoding="utf-8") as f:
            wl = json.load(f)
            return wl if isinstance(wl, dict) else {}
    except FileNotFoundError:
        return {"banners_whitelist": []}


# Загружаем конфигурацию
config = load_config()

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

# Загружаем белый список
WHITELIST = load_whitelist()
logger.info(f"🔒 Загружен whitelist: {len(WHITELIST.get('banners_whitelist', []))} глобальных ID")


# ===================== ВСПОМОГАТЕЛЬНОЕ =====================

def _iso(d: date) -> str:
    return d.isoformat()


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
            logger.info(f"⚠️ Для кабинета {account_name} триггер не настроен - пропускаем обновление статистики")

        trigger_result = await trigger_statistics_refresh(session, access_token, BASE_URL, trigger_config)
        if not trigger_result.get("success") and not trigger_result.get("skipped"):
            logger.warning(f"⚠️ Триггер обновления статистики не сработал: {trigger_result.get('error')}")

        # Получаем индивидуальный лимит для кабинета или используем глобальный
        spent_limit = account_config.get("account_spent_limit", SPENT_LIMIT_RUB)

        # Определяем период анализа
        today = date.today()
        date_from = _iso(today - timedelta(days=LOOKBACK_DAYS))
        date_to = _iso(today)

        logger.info(f"🏢 Кабинет: {account_name}")
        logger.info(f"📅 Анализируем период: {date_from} — {date_to} ({LOOKBACK_DAYS} дней)")
        logger.info(f"💰 Лимит расходов: {spent_limit}₽")

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

            banner_data = {
                "id": bid, "name": name, "spent": spent, "clicks": clicks, "shows": shows, "vk_goals": vk_goals,
                "status": status, "delivery": delivery_status, "ad_group_id": ad_group_id,
                "moderation_status": moderation_status, "account": account_name
            }

            # Категоризируем объявления
            if spent >= spent_limit and vk_goals == 0:
                over_limit.append(banner_data)
                logger.info(f"🔴 [{account_name}] УБЫТОЧНОЕ: [{bid}] {name} (потрачено: {spent:.2f}₽)")

            elif vk_goals >= 1:
                under_limit.append(banner_data)
                logger.info(f"🟢 [{account_name}] ЭФФЕКТИВНОЕ: [{bid}] {name} ({int(vk_goals)} VK целей)")

            elif spent > 0:
                no_activity.append(banner_data)
                logger.info(f"⚠️ [{account_name}] ТЕСТИРУЕТСЯ: [{bid}] {name} ({spent:.2f}₽)")

            else:
                no_activity.append(banner_data)

        # Итоговая статистика
        logger.info("=" * 80)
        logger.info(f"📈 ИТОГОВАЯ СТАТИСТИКА ПО КАБИНЕТУ: {account_name}")
        logger.info(f"🔴 Убыточных: {len(over_limit)}")
        logger.info(f"🟢 Эффективных: {len(under_limit)}")
        logger.info(f"⚠️ Тестируемых/неактивных: {len(no_activity)}")
        logger.info(f"📊 Всего активных: {len(banners)}")

        total_spent = sum(b["spent"] for b in over_limit + under_limit)
        total_vk_goals = sum(b["vk_goals"] for b in over_limit + under_limit)

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
        return None


def _prepare_account_config(global_config: dict, account_config) -> dict:
    """Готовит конфиг для конкретного кабинета"""
    account_full_config = dict(global_config)

    if isinstance(account_config, dict):
        trigger_id = account_config.get("trigger")
        account_full_config["account_trigger_id"] = trigger_id if trigger_id else None

        if "spent_limit_rub" in account_config:
            account_full_config["account_spent_limit"] = account_config["spent_limit_rub"]
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
        # Загружаем конфигурацию
        config = load_config()

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
            config = load_config()
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
