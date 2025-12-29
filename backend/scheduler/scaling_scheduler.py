"""
Auto-Scaling Scheduler
Запускает автомасштабирование по расписанию (в указанное время по МСК)

Использует систему ScalingTask для трекинга прогресса, чтобы UI
мог показывать уведомления о завершении.
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from database import crud
from utils.vk_api import get_ad_groups_with_stats, duplicate_ad_group_full
from utils.time_utils import get_moscow_time
from utils.logging_setup import get_logger, setup_logging, add_user_log_file, set_context
from leadstech.roi_enricher import get_banners_by_ad_group, enrich_groups_with_roi
from services.scaling_engine import BannerScalingEngine

# Инициализируем логирование
setup_logging()
logger = get_logger(service="scheduler", function="scaling")

# Get user_id from environment variable (set by API when starting the scheduler)
USER_ID = os.environ.get("VK_ADS_USER_ID")
if USER_ID:
    USER_ID = int(USER_ID)

# Track running tasks to prevent duplicates
running_config_ids = set()
running_lock = threading.Lock()


def run_scaling_config_with_tracking(config_id: int):
    """
    Запускает конфигурацию масштабирования с трекингом через ScalingTask.
    Это позволяет UI отслеживать прогресс и показывать уведомления.
    """
    db = SessionLocal()

    try:
        config = crud.get_scaling_config_by_id(db, config_id)
        if not config:
            logger.error(f"❌ Конфигурация {config_id} не найдена")
            return

        if not config.scheduled_enabled:
            logger.info(f"⏭️ Конфигурация '{config.name}' отключена для расписания, пропускаем")
            return

        # Check if already running
        with running_lock:
            if config_id in running_config_ids:
                logger.info(f"⏭️ Конфигурация '{config.name}' уже выполняется, пропускаем")
                return
            running_config_ids.add(config_id)

        try:
            _execute_scaling_config(db, config)
        finally:
            with running_lock:
                running_config_ids.discard(config_id)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при выполнении конфигурации {config_id}: {e}")
    finally:
        db.close()


def _execute_scaling_config(db, config):
    """
    Внутренняя функция выполнения конфигурации с полным трекингом.
    Использует новый BannerScalingEngine для анализа на уровне объявлений.
    """

    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"🚀 ЗАПУСК BANNER-LEVEL АВТОМАСШТАБИРОВАНИЯ: {config.name}")
    logger.info(f"{'='*80}")

    conditions = crud.get_scaling_conditions(db, config.id)
    if not conditions:
        logger.warning(f"⚠️ Нет условий для конфигурации '{config.name}', пропускаем")
        return

    # Получаем целевые аккаунты
    account_ids = crud.get_scaling_config_account_ids(db, config.id)

    if account_ids:
        all_accounts = crud.get_accounts(db, user_id=config.user_id)
        accounts = [a for a in all_accounts if a.id in account_ids]
    elif config.account_id:
        accounts = [crud.get_account_by_id(db, config.account_id)]
        accounts = [a for a in accounts if a]
    else:
        accounts = crud.get_accounts(db, user_id=config.user_id)

    if not accounts:
        logger.warning(f"⚠️ Нет аккаунтов для обработки")
        return

    # Создаём задачу для трекинга
    task = crud.create_scaling_task(
        db,
        user_id=config.user_id,
        task_type='auto',
        config_id=config.id,
        config_name=config.name,
        account_name=", ".join([a.name for a in accounts]),
        total_operations=0  # Обновим позже
    )

    task_id = task.id
    logger.info(f"📋 Создана задача #{task_id} для отслеживания")

    # Стартуем задачу
    crud.start_scaling_task(db, task_id)

    # Проверяем есть ли ручные группы для масштабирования
    manual_group_ids = crud.get_manual_scaling_groups(db, config.id)

    if manual_group_ids:
        # Ручное масштабирование - используем старую логику
        _execute_manual_scaling(db, config, accounts, task_id, manual_group_ids)
    else:
        # Автомасштабирование - используем новый BannerScalingEngine
        _execute_banner_scaling(db, config, accounts, task_id)

    # Обновляем время последнего запуска
    crud.update_scaling_config_last_run(db, config.id)


def _execute_banner_scaling(db, config, accounts, task_id):
    """
    Выполняет banner-level масштабирование через новый движок.
    Анализирует каждое объявление отдельно, классифицирует на позитивные/негативные.
    """
    logger.info(f"📊 Режим: Banner-Level Scaling")
    logger.info(f"   Аккаунтов: {len(accounts)}")
    logger.info(f"   Настройки: activate_positive={getattr(config, 'activate_positive_banners', True)}, "
                f"duplicate_negative={getattr(config, 'duplicate_negative_banners', True)}, "
                f"activate_negative={getattr(config, 'activate_negative_banners', False)}")

    try:
        # Создаём и запускаем движок
        engine = BannerScalingEngine(
            config_id=config.id,
            user_id=config.user_id,
            task_id=task_id,
            db_session=db
        )

        result = engine.run(accounts)

        # Завершаем задачу
        if result.failed_duplications == 0:
            final_status = 'completed'
        elif result.successful_duplications == 0:
            final_status = 'failed'
        else:
            final_status = 'completed'

        crud.complete_scaling_task(db, task_id, status=final_status)

        # Итоги
        logger.info(f"")
        logger.info(f"{'='*80}")
        logger.info(f"✅ BANNER-LEVEL МАСШТАБИРОВАНИЕ ЗАВЕРШЕНО: {config.name}")
        logger.info(f"{'='*80}")
        logger.info(f"   Проанализировано баннеров: {result.total_banners_analyzed}")
        logger.info(f"   Позитивных: {result.positive_banners}")
        logger.info(f"   Негативных: {result.negative_banners}")
        logger.info(f"   Групп для дублирования: {result.groups_found}")
        logger.info(f"   Успешно скопировано: {result.successful_duplications}")
        logger.info(f"   Ошибок: {result.failed_duplications}")
        logger.info(f"   Задача #{task_id} завершена со статусом: {final_status}")
        logger.info(f"{'='*80}")

    except Exception as e:
        logger.error(f"❌ Ошибка в BannerScalingEngine: {e}")
        crud.update_scaling_task_progress(db, task_id, last_error=str(e))
        crud.complete_scaling_task(db, task_id, status='failed')


def _execute_manual_scaling(db, config, accounts, task_id, manual_group_ids):
    """
    Выполняет ручное масштабирование указанных групп.
    Использует старую логику - дублирует указанные группы целиком.
    """
    logger.info(f"📋 Режим ручного масштабирования: {len(manual_group_ids)} групп")

    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=config.lookback_days)).strftime("%Y-%m-%d")
    base_url = "https://ads.vk.com/api/v2"

    completed = 0
    successful = 0
    failed = 0
    duplicates_count = config.duplicates_count or 1
    new_name = getattr(config, 'new_name', None)

    # Собираем группы для обработки
    groups_to_process = []

    for account in accounts:
        logger.info(f"📁 Поиск групп в кабинете: {account.name}")

        try:
            groups = get_ad_groups_with_stats(
                token=account.api_token,
                base_url=base_url,
                date_from=date_from,
                date_to=date_to
            )

            for group in groups:
                group_id = group.get("id")
                if group_id in manual_group_ids:
                    group_name = group.get("name", "Unknown")
                    stats = group.get("stats", {})
                    logger.info(f"   ✅ Найдена группа '{group_name}' (ID: {group_id})")
                    groups_to_process.append({
                        'account': account,
                        'group_id': group_id,
                        'group_name': group_name,
                        'stats': stats
                    })

        except Exception as e:
            logger.error(f"   ❌ Ошибка при сканировании кабинета {account.name}: {e}")
            crud.update_scaling_task_progress(
                db, task_id,
                last_error=f"Ошибка сканирования {account.name}: {str(e)}"
            )

    # Обновляем общее количество операций
    total_operations = len(groups_to_process) * duplicates_count
    if total_operations > 0:
        task_obj = crud.get_scaling_task(db, task_id)
        if task_obj:
            task_obj.total_operations = total_operations
            db.commit()

    logger.info(f"📊 Всего к обработке: {len(groups_to_process)} групп x {duplicates_count} копий = {total_operations} операций")

    if total_operations == 0:
        logger.info(f"ℹ️ Нет групп для дублирования")
        crud.complete_scaling_task(db, task_id, status='completed')
        return

    cancelled = False

    # Обрабатываем группы
    for item in groups_to_process:
        if cancelled:
            break

        account = item['account']
        group_id = item['group_id']
        group_name = item['group_name']
        stats = item['stats']

        logger.info(f"")
        logger.info(f"🔄 Обработка группы: {group_name} (ID: {group_id})")
        logger.info(f"   Статистика: лиды={stats.get('goals', 0)}, расход={stats.get('spent', 0):.2f}₽, CPL={stats.get('cost_per_goal', 'N/A')}")

        for dup_num in range(1, duplicates_count + 1):
            # Проверяем не отменена ли задача
            task_check = crud.get_scaling_task(db, task_id)
            if task_check and task_check.status == 'cancelled':
                logger.warning(f"⛔ Задача #{task_id} отменена пользователем, останавливаем")
                cancelled = True
                break

            try:
                crud.update_scaling_task_progress(
                    db, task_id,
                    current_group_id=group_id,
                    current_group_name=f"{group_name} (копия {dup_num}/{duplicates_count})"
                )

                result = duplicate_ad_group_full(
                    token=account.api_token,
                    base_url=base_url,
                    ad_group_id=group_id,
                    new_name=new_name,
                    new_budget=config.new_budget,
                    auto_activate=config.auto_activate,
                    rate_limit_delay=0.03
                )

                banner_ids_data = None
                if result.get("duplicated_banners"):
                    banner_ids_data = [
                        {
                            "original_id": b.get("original_id"),
                            "new_id": b.get("new_id"),
                            "name": b.get("name")
                        }
                        for b in result.get("duplicated_banners", [])
                    ]

                crud.create_scaling_log(
                    db,
                    user_id=config.user_id,
                    config_id=config.id,
                    config_name=config.name,
                    account_name=account.name,
                    original_group_id=group_id,
                    original_group_name=group_name,
                    new_group_id=result.get("new_group_id"),
                    new_group_name=result.get("new_group_name"),
                    stats_snapshot=stats,
                    success=result.get("success", False),
                    error_message=result.get("error"),
                    total_banners=result.get("total_banners", 0),
                    duplicated_banners=len(result.get("duplicated_banners", [])),
                    duplicated_banner_ids=banner_ids_data,
                    requested_name=new_name
                )

                if result.get("success"):
                    successful += 1
                    logger.info(f"   ✅ Копия {dup_num}/{duplicates_count}: {result.get('new_group_name')} (ID: {result.get('new_group_id')})")
                else:
                    failed += 1
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"   ❌ Копия {dup_num}/{duplicates_count}: {error_msg}")
                    crud.update_scaling_task_progress(db, task_id, last_error=error_msg)

            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(f"   ❌ Исключение при создании копии {dup_num}/{duplicates_count}: {error_msg}")

                crud.create_scaling_log(
                    db,
                    user_id=config.user_id,
                    config_id=config.id,
                    config_name=config.name,
                    account_name=account.name,
                    original_group_id=group_id,
                    original_group_name=group_name,
                    success=False,
                    error_message=error_msg
                )

                crud.update_scaling_task_progress(db, task_id, last_error=error_msg)

            completed += 1
            crud.update_scaling_task_progress(
                db, task_id,
                completed=completed,
                successful=successful,
                failed=failed
            )

    # Завершаем задачу
    if not cancelled:
        final_status = 'completed' if failed == 0 else ('failed' if successful == 0 else 'completed')
        crud.complete_scaling_task(db, task_id, status=final_status)

    # Итоги
    logger.info(f"")
    logger.info(f"{'='*80}")
    if cancelled:
        logger.info(f"⛔ РУЧНОЕ МАСШТАБИРОВАНИЕ ОТМЕНЕНО: {config.name}")
    else:
        logger.info(f"✅ РУЧНОЕ МАСШТАБИРОВАНИЕ ЗАВЕРШЕНО: {config.name}")
    logger.info(f"{'='*80}")
    logger.info(f"   Успешно: {successful}")
    logger.info(f"   Ошибок: {failed}")
    if cancelled:
        logger.info(f"   Задача #{task_id} отменена пользователем")
    else:
        logger.info(f"   Задача #{task_id} завершена со статусом: {final_status}")
    logger.info(f"{'='*80}")


def check_and_run_scheduled_configs():
    """
    Проверяет и запускает конфигурации по расписанию.
    Каждый запуск выполняется в отдельном потоке для неблокирующего выполнения.
    """
    db = SessionLocal()

    try:
        configs = crud.get_enabled_scaling_configs(db, user_id=USER_ID)
        current_time = get_moscow_time().strftime("%H:%M")

        if configs:
            logger.info(f"📋 Проверка расписания: {current_time} МСК, найдено {len(configs)} активных конфигураций")
            for c in configs:
                logger.debug(f"   - '{c.name}' (schedule: {c.schedule_time})")

        for config in configs:
            if config.schedule_time == current_time:
                logger.info(f"⏰ Время запуска конфигурации: {config.name} (schedule: {config.schedule_time})")

                # Запускаем в отдельном потоке
                thread = threading.Thread(
                    target=run_scaling_config_with_tracking,
                    args=(config.id,),
                    name=f"scaling_config_{config.id}"
                )
                thread.daemon = True
                thread.start()

    except Exception as e:
        logger.error(f"❌ Ошибка при проверке расписания: {e}")
    finally:
        db.close()


def main():
    """
    Основной цикл планировщика автомасштабирования
    """
    global logger

    # Устанавливаем контекст для логирования
    user_id = USER_ID if USER_ID else 0
    set_context(user_id=user_id, service="scheduler", function="scaling")

    # Создаём персональный лог-файл для пользователя
    if user_id:
        add_user_log_file(user_id, "scaling")

    # Получаем логгер с контекстом
    logger = get_logger(service="scheduler", function="scaling", user_id=user_id)

    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"🚀 ЗАПУСК ПЛАНИРОВЩИКА АВТОМАСШТАБИРОВАНИЯ")
    logger.info(f"{'='*80}")
    logger.info(f"Время: {get_moscow_time().strftime('%Y-%m-%d %H:%M:%S')} МСК")
    logger.info(f"User ID: {USER_ID if USER_ID else 'All users'}")
    logger.info(f"Проверка каждую минуту")
    logger.info(f"С трекингом через ScalingTask для UI-уведомлений")
    logger.info(f"{'='*80}")

    # Трекинг последней проверенной минуты чтобы не пропустить
    last_checked_minute = None

    while True:
        try:
            current_minute = get_moscow_time().strftime("%H:%M")

            # Проверяем только если минута изменилась (чтобы не дублировать)
            if current_minute != last_checked_minute:
                check_and_run_scheduled_configs()
                last_checked_minute = current_minute

            time.sleep(10)  # Проверяем каждые 10 секунд
        except KeyboardInterrupt:
            logger.info("🛑 Остановка планировщика автомасштабирования")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
