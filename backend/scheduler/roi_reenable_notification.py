"""
Telegram notification function for ROI reenable
"""
import re
from typing import Dict, List


def send_roi_reenable_notification(
    telegram_config: Dict,
    reenabled_banners: List[Dict],
    roi_threshold: float,
    total_disabled: int,
    total_reenabled: int,
    total_errors: int,
    dry_run: bool,
    lookback_days: int,
    logger=None
):
    """Send Telegram notification about ROI reenable results."""
    from scheduler.notifications import send_telegram_message

    if not telegram_config.get("enabled", False):
        return

    # Group banners by account
    by_account: Dict[str, List[Dict]] = {}
    for banner in reenabled_banners:
        account = banner["account"]
        if account not in by_account:
            by_account[account] = []
        by_account[account].append(banner)

    # Send per-account messages
    for account_name, banners in by_account.items():
        # Clean account name for hashtag
        clean_account = re.sub(r'[^\w]', '_', account_name)

        # Build message
        message = f"<b>#автовключение_roi_{clean_account}</b>\n\n"
        message += f"Период анализа: {lookback_days} дней\n"
        message += f"Порог ROI: >= {roi_threshold}%\n\n"

        if dry_run:
            message += f"<b>🔬 ТЕСТОВЫЙ РЕЖИМ - Было бы включено {len(banners)} шт.:</b>\n\n"
        else:
            message += f"<b>✅ Прибыльные объявления ({len(banners)} шт.):</b>\n\n"

        # Add banners
        for i, banner in enumerate(banners, 1):
            banner_name = banner.get('banner_name', '')
            if banner_name.startswith('ID:'):
                banner_name = ''

            message += f"{i}. <code>{banner['banner_id']}</code>"
            if banner_name:
                message += f" {banner_name[:30]}"
            message += "\n"
            message += f"   ROI: {banner['roi_percent']:.1f}%\n"
            message += f"   Потрачено: {banner['spent']:.2f}₽\n"
            message += f"   Доход: {banner['revenue']:.2f}₽\n"
            message += f"   Прибыль: {banner['profit']:.2f}₽\n"

            extras = []
            if banner.get('campaign_enabled'):
                extras.append('+ кампания')
            if banner.get('group_enabled'):
                extras.append('+ группа')
            if extras:
                message += f"   ({', '.join(extras)})\n"
            message += "\n"

        if dry_run:
            message += "<i>Для реального включения отключите DRY RUN</i>"

        # Send message
        try:
            send_telegram_message(telegram_config, message, logger)
            if logger:
                logger.info(f"Telegram notification sent for account {account_name}")
        except Exception as e:
            if logger:
                logger.error(f"Failed to send Telegram notification: {e}")
