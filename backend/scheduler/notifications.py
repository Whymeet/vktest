"""
Scheduler notifications - Telegram messaging
"""
import re
import time
from typing import Dict, List, Optional

import requests

from scheduler.config import BANNERS_PER_MESSAGE, TELEGRAM_MESSAGE_DELAY


def send_telegram_message(
    telegram_config: Dict,
    message: str,
    logger=None
) -> bool:
    """
    Send message to Telegram.

    Args:
        telegram_config: Dict with bot_token, chat_id, enabled
        message: HTML formatted message
        logger: Optional logger for error reporting

    Returns:
        True if at least one message was sent successfully
    """
    if not telegram_config.get("enabled", False):
        return False

    bot_token = telegram_config.get("bot_token")
    chat_ids = telegram_config.get("chat_id", [])

    if not bot_token or not chat_ids:
        return False

    if isinstance(chat_ids, str):
        chat_ids = [chat_ids]

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
                success_count += 1
            else:
                if logger:
                    logger.error(f"Telegram error for {chat_id}: {response.status_code}")
        except Exception as e:
            if logger:
                logger.error(f"Telegram exception for {chat_id}: {e}")

    return success_count > 0


def send_reenable_notification(
    telegram_config: Dict,
    reenabled_banners: List[Dict],
    total_checked: int,
    total_reenabled: int,
    total_skipped: int,
    total_errors: int,
    dry_run: bool,
    lookback_hours: int,
    lookback_days: int,
    logger=None
) -> bool:
    """
    Send reenable results notification to Telegram.

    Args:
        telegram_config: Telegram configuration
        reenabled_banners: List of reenabled banner details
        total_checked: Total banners checked
        total_reenabled: Total banners reenabled
        total_skipped: Total banners skipped (still match rules)
        total_errors: Total errors
        dry_run: Whether this was a dry run
        lookback_hours: Period for searching disabled banners
        lookback_days: Period for statistics
        logger: Optional logger

    Returns:
        True if notifications sent successfully
    """
    try:
        mode_text = "ТЕСТОВЫЙ РЕЖИМ" if dry_run else "АВТОВКЛЮЧЕНИЕ"

        # Group banners by account
        by_account: Dict[str, List[Dict]] = {}
        if reenabled_banners:
            for b in reenabled_banners:
                acc = b["account"]
                if acc not in by_account:
                    by_account[acc] = []
                by_account[acc].append(b)

        # Send per-account messages with tags
        if by_account:
            for account_name, banners in by_account.items():
                clean_account_name = re.sub(r'[^\w]', '_', account_name)

                # Split into parts
                total_parts = (len(banners) + BANNERS_PER_MESSAGE - 1) // BANNERS_PER_MESSAGE

                for part_num in range(total_parts):
                    start_idx = part_num * BANNERS_PER_MESSAGE
                    end_idx = min(start_idx + BANNERS_PER_MESSAGE, len(banners))
                    part_banners = banners[start_idx:end_idx]

                    # Header only in first message
                    if part_num == 0:
                        message = f"<b>#включение_{clean_account_name}</b>\n\n"
                        message += f"<b>{mode_text}</b>\n\n"
                        message += f"Кабинет: {account_name}\n"
                        message += f"Отключённые за: последние {lookback_hours}ч\n"
                        message += f"Статистика за: {lookback_days} дней\n"
                        message += f"{'Было бы включено' if dry_run else 'Включено'}: <b>{len(banners)}</b>\n\n"
                        message += f"<b>{'Баннеры для включения:' if dry_run else 'Включённые баннеры:'}</b>\n"
                    else:
                        message = f"<b>#включение_{clean_account_name}</b> (часть {part_num + 1}/{total_parts})\n\n"

                    for i, b in enumerate(part_banners, start_idx + 1):
                        extras = []
                        if b.get("campaign_enabled"):
                            extras.append("+ кампания")
                        if b.get("group_enabled"):
                            extras.append("+ группа")
                        extras_text = f" ({', '.join(extras)})" if extras else ""

                        banner_name = b['banner_name'][:30] if b.get('banner_name') else ''
                        message += f"{i}. {b['banner_id']} {banner_name}{extras_text}\n"
                        message += f"   Потрачено: {b['spent']:.2f} | Рез: {int(b['goals'])}\n"

                    # Note only in last message
                    if part_num == total_parts - 1 and dry_run:
                        message += f"\n<i>Для реального включения отключите DRY RUN в настройках</i>"

                    send_telegram_message(telegram_config, message, logger)
                    time.sleep(TELEGRAM_MESSAGE_DELAY)

                if logger:
                    logger.info(f"Telegram: sent {total_parts} messages for account {account_name}")

        # Send summary message (always)
        summary_message = f"<b>{mode_text} - ИТОГИ</b>\n\n"
        summary_message += f"Результаты проверки:\n"
        summary_message += f"Отключённые за: последние {lookback_hours}ч\n"
        summary_message += f"Статистика за: {lookback_days} дней\n"
        summary_message += f"Проверено баннеров: {total_checked}\n"
        summary_message += f"{'Было бы включено' if dry_run else 'Включено'}: <b>{total_reenabled}</b>\n"
        summary_message += f"Пропущено (под правилами): {total_skipped}\n"
        summary_message += f"Ошибок: {total_errors}\n"

        if total_reenabled == 0 and total_checked > 0:
            summary_message += f"\n<i>Все проверенные баннеры остаются отключенными (подпадают под правила)</i>"
        elif total_checked == 0:
            summary_message += f"\n<i>Нет отключённых баннеров за указанный период</i>"

        if dry_run and total_reenabled > 0:
            summary_message += f"\n<i>Режим DRY RUN - реальные изменения НЕ применялись</i>"

        send_telegram_message(telegram_config, summary_message, logger)

        if logger:
            logger.info("Telegram summary notification sent")

        return True

    except Exception as e:
        if logger:
            logger.error(f"Error sending Telegram notification: {e}")
        return False
