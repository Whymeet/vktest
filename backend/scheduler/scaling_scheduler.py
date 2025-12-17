"""
Auto-Scaling Scheduler
Запускает автомасштабирование по расписанию (в указанное время по МСК)
"""

import sys
import time
import schedule
from datetime import datetime
from pathlib import Path
from logging import getLogger

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from database import crud
from utils.vk_api import get_ad_groups_with_stats, duplicate_ad_group_full
from utils.logging_setup import setup_logging
from utils.time_utils import get_moscow_time

logger = getLogger("scaling_scheduler")


def run_scaling_config(config_id: int):
    """
    Запускает конфигурацию масштабирования
    """
    db = SessionLocal()
    
    try:
        config = crud.get_scaling_config_by_id(db, config_id)
        if not config:
            logger.error(f"❌ Конфигурация {config_id} не найдена")
            return
        
        if not config.enabled:
            logger.info(f"⏭️ Конфигурация '{config.name}' отключена, пропускаем")
            return
        
        logger.info(f"")
        logger.info(f"{'='*80}")
        logger.info(f"🚀 ЗАПУСК АВТОМАСШТАБИРОВАНИЯ: {config.name}")
        logger.info(f"{'='*80}")
        
        conditions = crud.get_scaling_conditions(db, config_id)
        if not conditions:
            logger.warning(f"⚠️ Нет условий для конфигурации '{config.name}', пропускаем")
            return
        
        # Получаем целевые аккаунты
        if config.account_id:
            accounts = [crud.get_account_by_id(db, config.account_id)]
            accounts = [a for a in accounts if a]
        else:
            accounts = crud.get_accounts(db, user_id=config.user_id)
        
        if not accounts:
            logger.warning(f"⚠️ Нет аккаунтов для обработки")
            return
        
        # Вычисляем период анализа
        from datetime import timedelta
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=config.lookback_days)).strftime("%Y-%m-%d")
        
        base_url = "https://ads.vk.com/api/v2"
        
        total_duplicated = 0
        total_skipped = 0
        total_errors = 0
        
        for account in accounts:
            logger.info(f"")
            logger.info(f"📁 Обработка кабинета: {account.name}")
            
            try:
                # Получаем группы со статистикой
                groups = get_ad_groups_with_stats(
                    token=account.api_token,
                    base_url=base_url,
                    date_from=date_from,
                    date_to=date_to
                )
                
                logger.info(f"   Найдено {len(groups)} активных групп")
                
                for group in groups:
                    group_id = group.get("id")
                    group_name = group.get("name", "Unknown")
                    stats = group.get("stats", {})
                    
                    # Проверяем условия
                    if crud.check_group_conditions(stats, conditions):
                        logger.info(f"   ✅ Группа '{group_name}' соответствует условиям")
                        logger.info(f"      Статистика: лиды={stats.get('goals', 0)}, расход={stats.get('spent', 0):.2f}₽, CPL={stats.get('cost_per_goal', 'N/A')}")
                        
                        try:
                            # Дублируем группу
                            result = duplicate_ad_group_full(
                                token=account.api_token,
                                base_url=base_url,
                                ad_group_id=group_id,
                                new_name=None,
                                new_budget=config.new_budget,
                                auto_activate=config.auto_activate,
                                rate_limit_delay=0.03
                            )
                            
                            # Логируем операцию
                            # Extract banner IDs for logging
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
                                duplicated_banner_ids=banner_ids_data
                            )
                            
                            if result.get("success"):
                                total_duplicated += 1
                                logger.info(f"      🎉 Создана копия: {result.get('new_group_name')} (ID: {result.get('new_group_id')})")
                            else:
                                total_errors += 1
                                logger.error(f"      ❌ Ошибка: {result.get('error', 'Unknown')}")
                                
                        except Exception as e:
                            total_errors += 1
                            logger.error(f"      ❌ Исключение при дублировании: {e}")
                            
                            crud.create_scaling_log(
                                db,
                                user_id=config.user_id,
                                config_id=config.id,
                                config_name=config.name,
                                account_name=account.name,
                                original_group_id=group_id,
                                original_group_name=group_name,
                                success=False,
                                error_message=str(e)
                            )
                    else:
                        total_skipped += 1
                        logger.debug(f"   ⏭️ Группа '{group_name}' не соответствует условиям")
                        
            except Exception as e:
                total_errors += 1
                logger.error(f"   ❌ Ошибка при обработке кабинета {account.name}: {e}")
        
        # Обновляем время последнего запуска
        crud.update_scaling_config_last_run(db, config_id)
        
        # Итоги
        logger.info(f"")
        logger.info(f"{'='*80}")
        logger.info(f"✅ АВТОМАСШТАБИРОВАНИЕ ЗАВЕРШЕНО: {config.name}")
        logger.info(f"{'='*80}")
        logger.info(f"   Продублировано групп: {total_duplicated}")
        logger.info(f"   Пропущено (не соответствуют): {total_skipped}")
        logger.info(f"   Ошибок: {total_errors}")
        logger.info(f"{'='*80}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при выполнении конфигурации {config_id}: {e}")
    finally:
        db.close()


def check_and_run_scheduled_configs():
    """
    Проверяет и запускает конфигурации по расписанию
    """
    db = SessionLocal()
    
    try:
        configs = crud.get_enabled_scaling_configs(db)
        current_time = get_moscow_time().strftime("%H:%M")
        
        for config in configs:
            if config.schedule_time == current_time:
                logger.info(f"⏰ Время запуска конфигурации: {config.name}")
                run_scaling_config(config.id)
                
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке расписания: {e}")
    finally:
        db.close()


def main():
    """
    Основной цикл планировщика автомасштабирования
    """
    setup_logging("scaling_scheduler")
    
    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"🚀 ЗАПУСК ПЛАНИРОВЩИКА АВТОМАСШТАБИРОВАНИЯ")
    logger.info(f"{'='*80}")
    logger.info(f"Время: {get_moscow_time().strftime('%Y-%m-%d %H:%M:%S')} МСК")
    logger.info(f"Проверка каждую минуту")
    logger.info(f"{'='*80}")
    
    # Запускаем проверку каждую минуту
    schedule.every(1).minutes.do(check_and_run_scheduled_configs)
    
    # Первая проверка сразу
    check_and_run_scheduled_configs()
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)  # Проверяем каждые 30 секунд
        except KeyboardInterrupt:
            logger.info("🛑 Остановка планировщика автомасштабирования")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
