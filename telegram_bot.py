"""
Telegram бот для управления VK Ads кабинетами
Команды:
- /stop_cab [Name_Cab] - Отключить все активные группы в указанном кабинете
- /start - Приветствие и список доступных команд
- /accounts - Список доступных кабинетов
"""

import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from vk_api import get_ad_groups_active, disable_ad_group
from logging_setup import setup_logging

# Настройка логирования
setup_logging()
logger = logging.getLogger("telegram_bot")


def load_config():
    """Загрузка конфигурации"""
    try:
        with open("cfg/config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    message = (
        "🤖 <b>VK Ads Manager Bot</b>\n\n"
        "Доступные команды:\n"
        "📋 /accounts - Список кабинетов\n"
        "🛑 /stop_cab [Name_Cab] - Отключить все группы в кабинете\n\n"
        "Пример: /stop_cab Кокос 1"
    )
    await update.message.reply_text(message, parse_mode="HTML")


async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /accounts - список доступных кабинетов"""
    config = load_config()
    if not config:
        await update.message.reply_text("❌ Ошибка загрузки конфигурации")
        return

    accounts = config.get("vk_ads_api", {}).get("accounts", {})
    
    if not accounts:
        await update.message.reply_text("❌ Кабинеты не настроены")
        return

    message = "📋 <b>Доступные кабинеты:</b>\n\n"
    for i, account_name in enumerate(accounts.keys(), 1):
        message += f"{i}. <code>{account_name}</code>\n"
    
    message += "\n💡 Для отключения групп используйте:\n"
    message += "<code>/stop_cab Название_Кабинета</code>"
    
    await update.message.reply_text(message, parse_mode="HTML")


async def stop_cab_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stop_cab [Name_Cab] - отключить все группы в кабинете"""
    
    # Проверка аргументов
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите название кабинета!\n\n"
            "Пример: <code>/stop_cab Кокос 1</code>\n\n"
            "Список кабинетов: /accounts",
            parse_mode="HTML"
        )
        return
    
    # Получаем название кабинета (может содержать пробелы)
    account_name = " ".join(context.args)
    
    # Загружаем конфигурацию
    config = load_config()
    if not config:
        await update.message.reply_text("❌ Ошибка загрузки конфигурации")
        return
    
    # Проверяем наличие кабинета
    accounts = config.get("vk_ads_api", {}).get("accounts", {})
    if account_name not in accounts:
        available = ", ".join([f"<code>{name}</code>" for name in accounts.keys()])
        await update.message.reply_text(
            f"❌ Кабинет '<b>{account_name}</b>' не найден!\n\n"
            f"Доступные кабинеты:\n{available}\n\n"
            f"Или используйте: /accounts",
            parse_mode="HTML"
        )
        return
    
    # Получаем API токен и настройки
    account_config = accounts[account_name]
    api_token = account_config.get("api")
    base_url = config.get("vk_ads_api", {}).get("base_url", "https://ads.vk.com/api/v2")
    dry_run = config.get("analysis_settings", {}).get("dry_run", True)
    
    if not api_token:
        await update.message.reply_text(
            f"❌ API токен для кабинета '<b>{account_name}</b>' не настроен!",
            parse_mode="HTML"
        )
        return
    
    # Отправляем уведомление о начале
    status_message = await update.message.reply_text(
        f"⏳ Загружаю активные группы кабинета '<b>{account_name}</b>'...",
        parse_mode="HTML"
    )
    
    try:
        # Получаем активные группы
        logger.info(f"Загрузка активных групп для кабинета: {account_name}")
        active_groups = get_ad_groups_active(
            token=api_token,
            base_url=base_url,
            fields="id,name,status"
        )
        
        if not active_groups:
            await status_message.edit_text(
                f"ℹ️ В кабинете '<b>{account_name}</b>' нет активных групп",
                parse_mode="HTML"
            )
            return
        
        total_groups = len(active_groups)
        
        # Обновляем статус
        mode_text = "🔸 <b>ТЕСТОВЫЙ РЕЖИМ</b>" if dry_run else "🔴 <b>РЕАЛЬНОЕ ОТКЛЮЧЕНИЕ</b>"
        await status_message.edit_text(
            f"{mode_text}\n\n"
            f"📊 Найдено активных групп: <b>{total_groups}</b>\n"
            f"🔄 Отключаю группы...",
            parse_mode="HTML"
        )
        
        # Отключаем группы
        disabled_count = 0
        failed_count = 0
        
        for group in active_groups:
            group_id = group.get("id")
            group_name = group.get("name", "Без названия")
            
            result = disable_ad_group(
                token=api_token,
                base_url=base_url,
                group_id=group_id,
                dry_run=dry_run
            )
            
            if result.get("success"):
                disabled_count += 1
            else:
                failed_count += 1
                logger.error(f"Ошибка отключения группы {group_id} ({group_name}): {result.get('error')}")
        
        # Формируем итоговое сообщение
        if dry_run:
            final_message = (
                f"🔸 <b>Тестовый режим (DRY RUN)</b>\n\n"
                f"🏢 Кабинет: <b>{account_name}</b>\n"
                f"✅ Было бы отключено: <b>{disabled_count}</b> групп\n"
                f"❌ Ошибок: <b>{failed_count}</b>\n"
                f"📊 Всего обработано: <b>{total_groups}</b>\n\n"
                f"💡 Для реального отключения установите\n"
                f"<code>dry_run: false</code> в настройках"
            )
        else:
            final_message = (
                f"✅ <b>Отключение завершено</b>\n\n"
                f"🏢 Кабинет: <b>{account_name}</b>\n"
                f"🛑 Отключено: <b>{disabled_count}</b> групп\n"
                f"❌ Ошибок: <b>{failed_count}</b>\n"
                f"📊 Всего обработано: <b>{total_groups}</b>"
            )
        
        await status_message.edit_text(final_message, parse_mode="HTML")
        
        # Логируем результат
        logger.info(
            f"Команда /stop_cab выполнена для кабинета '{account_name}': "
            f"отключено={disabled_count}, ошибок={failed_count}, dry_run={dry_run}"
        )
        
    except Exception as e:
        error_message = (
            f"❌ <b>Ошибка при отключении групп</b>\n\n"
            f"🏢 Кабинет: <b>{account_name}</b>\n"
            f"⚠️ Ошибка: <code>{str(e)}</code>"
        )
        await status_message.edit_text(error_message, parse_mode="HTML")
        logger.error(f"Ошибка выполнения команды /stop_cab для '{account_name}': {e}", exc_info=True)


def main():
    """Запуск бота"""
    config = load_config()
    if not config:
        logger.error("❌ Не удалось загрузить конфигурацию. Бот не запущен.")
        return
    
    telegram_config = config.get("telegram", {})
    bot_token = telegram_config.get("bot_token")
    
    if not bot_token:
        logger.error("❌ Telegram bot_token не настроен в config.json")
        return
    
    # Создаем приложение
    application = Application.builder().token(bot_token).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("accounts", accounts_command))
    application.add_handler(CommandHandler("stop_cab", stop_cab_command))
    
    logger.info("🤖 Telegram бот запущен и готов к работе!")
    logger.info("📋 Доступные команды: /start, /accounts, /stop_cab")
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
