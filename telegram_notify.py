import requests
from datetime import datetime
from logging import getLogger

logger = getLogger("vk_ads_manager")

def send_telegram_message(config, message):
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enabled", False):
        logger.info("📱 Telegram уведомления отключены")
        return False
    bot_token = telegram_config.get("bot_token")
    chat_id = telegram_config.get("chat_id")
    if not bot_token or not chat_id:
        logger.warning("⚠️ Telegram не настроен: отсутствует bot_token или chat_id")
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
            logger.info("📱 Сообщение отправлено в Telegram")
            return True
        else:
            logger.error(f"❌ Ошибка отправки в Telegram: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Исключение при отправке в Telegram: {str(e)}")
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
