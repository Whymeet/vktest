"""
Budget Rules Scheduler
Запускает правила изменения бюджета по расписанию (в указанное время по МСК)

Аналогично scaling_scheduler.py - проверяет каждую минуту, совпадает ли
текущее время с schedule_time у правил, и запускает их.
"""

import os
import sys
import time
import threading
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from database import crud
from core.budget_changer import process_budget_rules_for_account
from utils.time_utils import get_moscow_time
from utils.logging_setup import get_logger, setup_logging, add_user_log_file, set_context

# Инициализируем логирование
setup_logging()
logger = get_logger(service="scheduler", function="budget_rules")

# Get user_id from environment variable
USER_ID = os.environ.get("VK_ADS_USER_ID")
if USER_ID:
    USER_ID = int(USER_ID)

# Track running rules to prevent duplicates
running_rule_ids = set()
running_lock = threading.Lock()


def run_budget_rule_with_tracking(rule_id: int):
    """
    Запускает правило бюджета с трекингом.
    Выполняется в отдельном потоке.
    """
    db = SessionLocal()
    
    try:
        rule = crud.get_budget_rule_by_id(db, rule_id)
        if not rule:
            logger.error(f"❌ Правило бюджета {rule_id} не найдено")
            return
        
        if not rule.scheduled_enabled:
            logger.info(f"⏭️ Правило '{rule.name}' отключено для расписания, пропускаем")
            return
        
        # Check if already running
        with running_lock:
            if rule_id in running_rule_ids:
                logger.info(f"⏭️ Правило '{rule.name}' уже выполняется, пропускаем")
                return
            running_rule_ids.add(rule_id)
        
        try:
            _execute_budget_rule(db, rule)
        finally:
            with running_lock:
                running_rule_ids.discard(rule_id)
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при выполнении правила {rule_id}: {e}")
    finally:
        db.close()


def _execute_budget_rule(db, rule):
    """
    Внутренняя функция выполнения правила бюджета.
    """
    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"🚀 ЗАПУСК ПРАВИЛА БЮДЖЕТА: {rule.name}")
    logger.info(f"{'='*80}")
    logger.info(f"   Изменение: {rule.change_direction} на {rule.change_percent}%")
    logger.info(f"   Период анализа: {rule.lookback_days} дней")
    
    # Получаем аккаунты для этого правила
    accounts = crud.get_budget_rule_accounts(db, rule.id)
    
    if not accounts:
        logger.warning(f"⚠️ Нет аккаунтов для правила '{rule.name}', пропускаем")
        return
    
    logger.info(f"   Аккаунтов: {len(accounts)}")
    for acc in accounts:
        logger.info(f"      - {acc.name}")
    
    # Получаем whitelist (returns List[int] of banner IDs)
    whitelist = set(crud.get_whitelist(db, user_id=rule.user_id))
    
    base_url = "https://ads.vk.com/api/v2"
    
    # Запускаем асинхронную обработку
    asyncio.run(_process_accounts_async(accounts, rule, whitelist, base_url))
    
    # Обновляем время последнего запуска
    crud.update_budget_rule_last_run(db, rule.id)
    
    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"✅ ПРАВИЛО БЮДЖЕТА ЗАВЕРШЕНО: {rule.name}")
    logger.info(f"{'='*80}")


async def _process_accounts_async(accounts, rule, whitelist, base_url):
    """
    Асинхронная обработка аккаунтов для правила бюджета.
    """
    async with aiohttp.ClientSession() as session:
        for account in accounts:
            try:
                logger.info(f"📁 Обработка аккаунта: {account.name}")
                
                result = await process_budget_rules_for_account(
                    session=session,
                    account_name=account.name,
                    access_token=account.api_token,
                    base_url=base_url,
                    user_id=rule.user_id,
                    dry_run=False,  # Реальное выполнение по расписанию
                    whitelist=whitelist
                )
                
                total_changes = result.get("total_changes", 0)
                successful = result.get("successful", 0)
                failed = result.get("failed", 0)
                
                logger.info(f"   ✅ {account.name}: {total_changes} изменений ({successful} успешно, {failed} ошибок)")
                
            except Exception as e:
                logger.error(f"   ❌ Ошибка при обработке {account.name}: {e}")


def check_and_run_scheduled_rules():
    """
    Проверяет и запускает правила бюджета по расписанию.
    Каждый запуск выполняется в отдельном потоке.
    """
    db = SessionLocal()
    
    try:
        rules = crud.get_scheduled_budget_rules(db, user_id=USER_ID)
        current_time = get_moscow_time().strftime("%H:%M")
        
        if rules:
            logger.debug(f"📋 Проверка расписания: {current_time} МСК, найдено {len(rules)} запланированных правил")
            for r in rules:
                logger.debug(f"   - '{r.name}' (schedule: {r.schedule_time})")
        
        for rule in rules:
            if rule.schedule_time == current_time:
                logger.info(f"⏰ Время запуска правила бюджета: {rule.name} (schedule: {rule.schedule_time})")
                
                # Запускаем в отдельном потоке
                thread = threading.Thread(
                    target=run_budget_rule_with_tracking,
                    args=(rule.id,),
                    name=f"budget_rule_{rule.id}"
                )
                thread.daemon = True
                thread.start()
    
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке расписания: {e}")
    finally:
        db.close()


def main():
    """
    Основной цикл планировщика правил бюджета
    """
    global logger
    
    # Устанавливаем контекст для логирования
    user_id = USER_ID if USER_ID else 0
    set_context(user_id=user_id, service="scheduler", function="budget_rules")
    
    # Создаём персональный лог-файл для пользователя
    if user_id:
        add_user_log_file(user_id, "budget_rules")
    
    # Получаем логгер с контекстом
    logger = get_logger(service="scheduler", function="budget_rules", user_id=user_id)
    
    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"🚀 ЗАПУСК ПЛАНИРОВЩИКА ПРАВИЛ БЮДЖЕТА")
    logger.info(f"{'='*80}")
    logger.info(f"Время: {get_moscow_time().strftime('%Y-%m-%d %H:%M:%S')} МСК")
    logger.info(f"User ID: {USER_ID if USER_ID else 'All users'}")
    logger.info(f"Проверка каждую минуту")
    logger.info(f"{'='*80}")
    
    # Трекинг последней проверенной минуты
    last_checked_minute = None
    
    while True:
        try:
            current_minute = get_moscow_time().strftime("%H:%M")
            
            # Проверяем только если минута изменилась
            if current_minute != last_checked_minute:
                check_and_run_scheduled_rules()
                last_checked_minute = current_minute
            
            time.sleep(10)  # Проверяем каждые 10 секунд
        except KeyboardInterrupt:
            logger.info("🛑 Остановка планировщика правил бюджета")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
