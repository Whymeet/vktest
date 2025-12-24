import requests
from datetime import datetime
from utils.logging_setup import get_logger

logger = get_logger(service="telegram")

def send_telegram_message(config, message):
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enabled", False):
        logger.info("📱 Telegram уведомления отключены")
        return False
    
    bot_token = telegram_config.get("bot_token")
    chat_ids = telegram_config.get("chat_id")
    
    if not bot_token or not chat_ids:
        logger.warning("⚠️ Telegram не настроен: отсутствует bot_token или chat_id")
        return False
    
    # Поддержка как одного chat_id (строка), так и нескольких (список)
    if isinstance(chat_ids, str):
        chat_ids = [chat_ids]
    elif not isinstance(chat_ids, list):
        logger.error("❌ chat_id должен быть строкой или списком строк")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    success_count = 0
    
    for chat_id in chat_ids:
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info(f"📱 Сообщение отправлено в Telegram (chat_id: {chat_id})")
                success_count += 1
            else:
                logger.error(f"❌ Ошибка отправки в Telegram для {chat_id}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ Исключение при отправке в Telegram для {chat_id}: {str(e)}")
    
    if success_count > 0:
        logger.info(f"📱 Сообщения отправлены в {success_count} из {len(chat_ids)} чатов")
        return True
    else:
        logger.error("❌ Не удалось отправить сообщения ни в один чат")
        return False

def format_telegram_statistics(unprofitable_count, effective_count, testing_count, 
                              total_count, total_spent, total_goals, avg_cost, lookback_days, accounts_count=1):
    """Форматирует статистику для Telegram"""
    
    if accounts_count > 1:
        header = f"<b>Сводный анализ ({accounts_count} кабинетов)</b>"
    else:
        header = "<b>Анализ объявлений завершен</b>"
    
    message = f"""{header}

Всего активных объявлений: <b>{total_count}</b>
Убыточных объявлений: <b>{unprofitable_count}</b>
Объявления с резом: <b>{effective_count}</b>
Объявления без реза: <b>{testing_count}</b>

Общие расходы за {lookback_days} дн.: <b>{total_spent:.2f}₽</b>
Общие резы за {lookback_days} дн.: <b>{total_goals}</b>
Средняя стоимость реза: <b>{avg_cost:.2f}₽</b>

{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"""
    
    return message

def format_telegram_unprofitable_groups(unprofitable_groups):
    """Форматирует список убыточных объявлений для Telegram, разбивая на сообщения по 10 объявлений"""
    if not unprofitable_groups:
        return ["<b>Убыточных объявлений не найдено!</b>"]
    
    messages = []
    groups_per_message = 10
    total_groups = len(unprofitable_groups)
    
    # Разбиваем объявления на части по 10 штук
    for batch_start in range(0, total_groups, groups_per_message):
        batch_end = min(batch_start + groups_per_message, total_groups)
        batch_groups = unprofitable_groups[batch_start:batch_end]
        
        batch_num = (batch_start // groups_per_message) + 1
        total_batches = (total_groups + groups_per_message - 1) // groups_per_message
        
        # Заголовок для каждого сообщения
        if total_batches > 1:
            message = f"🔴 <b>Убыточные объявления (часть {batch_num}/{total_batches}):</b>\n\n"
        else:
            message = f"🔴 <b>Убыточные объявления ({total_groups} шт.):</b>\n\n"
        
        # Добавляем объявления в сообщение
        for i, group in enumerate(batch_groups, batch_start + 1):
            group_id = group.get("id", "N/A")
            group_name = group.get("name", "Без названия")[:30]  # Ограничиваем длину
            spent = group.get("spent", 0)
            goals = int(group.get("vk_goals", 0))  # Получаем количество результатов
            matched_rule = group.get("matched_rule", "Без результата")  # Получаем название правила

            message += f"{i}. <code>{group_id}</code> {group_name}\n"
            message += f"   Потрачено: <b>{spent:.2f}₽</b> | Резов: <b>{goals}</b>\n"
            message += f"   Правило: {matched_rule}\n\n"
        
        messages.append(message)
    
    return messages

def format_telegram_account_statistics(account_name, unprofitable_count, effective_count, testing_count, 
                                      total_count, total_spent, total_goals, avg_cost, lookback_days, disable_results=None, unprofitable_groups=None):
    """Форматирует статистику по отдельному кабинету для Telegram - ТОЛЬКО сообщения об отключении"""
    
    messages = []
    
    # ✅ ОТПРАВЛЯЕМ ТОЛЬКО если есть убыточные объявления для отключения
    if unprofitable_groups and len(unprofitable_groups) > 0:
        groups_per_message = 10
        total_groups = len(unprofitable_groups)
        
        # Разбиваем объявления на части по 10 штук
        for batch_start in range(0, total_groups, groups_per_message):
            batch_end = min(batch_start + groups_per_message, total_groups)
            batch_groups = unprofitable_groups[batch_start:batch_end]
            
            batch_num = (batch_start // groups_per_message) + 1
            total_batches = (total_groups + groups_per_message - 1) // groups_per_message
            
            # Заголовок для каждого сообщения с убыточными объявлениями
            # Заменяем пробелы и спецсимволы в названии кабинета для тега
            clean_account_name = account_name.replace(" ", "_").replace("-", "_")
            if total_batches > 1:
                groups_message = f"<b>#отключение_{clean_account_name}</b>\n\n🔴 <b>Убыточные объявления (часть {batch_num}/{total_batches}):</b>\n\n"
            else:
                groups_message = f"<b>#отключение_{clean_account_name}</b>\n\n🔴 <b>Убыточные объявления ({total_groups} шт.):</b>\n\n"
            
            # Добавляем объявления в сообщение
            for i, group in enumerate(batch_groups, batch_start + 1):
                group_id = group.get("id", "N/A")
                group_name = group.get("name", "Без названия")[:25]  # Ограничиваем длину
                spent = group.get("spent", 0)
                goals = int(group.get("vk_goals", 0))  # Получаем количество результатов
                matched_rule = group.get("matched_rule", "Без результата")  # Получаем название правила

                groups_message += f"{i}. <code>{group_id}</code> {group_name}\n"
                groups_message += f"   Потрачено: <b>{spent:.2f}₽</b> | Рез: <b>{goals}</b>\n"
                groups_message += f"   Правило: {matched_rule}\n\n"
            
            messages.append(groups_message)
    
    return messages

def format_telegram_disable_results(disable_results):
    """Форматирует результаты отключения объявлений для Telegram"""
    if not disable_results:
        return "<b>Отключение объявлений не выполнялось</b>"
    
    dry_run = disable_results.get("dry_run", True)
    disabled = disable_results.get("disabled", 0)
    failed = disable_results.get("failed", 0)
    total = disable_results.get("total", 0)
    
    if dry_run:
        message = f"<b>Режим тестирования (DRY RUN)</b>\n\n"
        message += f"Было бы отключено: <b>{disabled}</b> объявлений\n"
        message += f"Ошибок: <b>{failed}</b>\n"
        message += f"Всего обработано: <b>{total}</b>\n\n"
        message += f"Для реального отключения установите dry_run: false в config.json"
    else:
        message = f"<b>Отключение объявлений завершено</b>\n\n"
        message += f"Отключено: <b>{disabled}</b> объявлений\n"
        message += f"Ошибок: <b>{failed}</b>\n"
        message += f"Всего обработано: <b>{total}</b>"
    
    return message
