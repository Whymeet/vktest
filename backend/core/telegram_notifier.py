"""
Core Telegram notifier - Send analysis notifications to Telegram
"""
import asyncio
from typing import Dict, List, Optional

from bot.telegram_notify import send_telegram_message, format_telegram_account_statistics
from utils.logging_setup import get_logger

logger = get_logger(service="vk_api", function="telegram")


async def send_analysis_notifications(
    config: Dict,
    results: List[Dict],
    lookback_days: int
) -> bool:
    """
    Send all analysis notifications to Telegram at the end of processing.

    Args:
        config: Configuration dict with telegram settings
        results: List of analysis results per account
        lookback_days: Analysis lookback period

    Returns:
        True if at least one message was sent successfully
    """
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enabled", False):
        logger.info("Telegram notifications disabled")
        return False

    # Collect all messages to send
    all_messages = []

    for result in results:
        if not result:
            continue

        over_limit = result.get("over_limit", [])
        if not over_limit:
            continue  # Only send if there are unprofitable banners

        account_name = result["account_name"]
        under_limit = result.get("under_limit", [])
        no_activity = result.get("no_activity", [])
        total_spent = result.get("total_spent", 0)
        total_vk_goals = result.get("total_vk_goals", 0)
        disable_results = result.get("disable_results")

        avg_cost = total_spent / total_vk_goals if total_vk_goals > 0 else 0

        # Format messages for this account
        account_messages = format_telegram_account_statistics(
            account_name=account_name,
            unprofitable_count=len(over_limit),
            effective_count=len(under_limit),
            testing_count=len(no_activity),
            total_count=len(over_limit) + len(under_limit) + len(no_activity),
            total_spent=total_spent,
            total_goals=int(total_vk_goals),
            avg_cost=avg_cost,
            lookback_days=lookback_days,
            disable_results=disable_results,
            unprofitable_groups=over_limit
        )

        all_messages.extend(account_messages)

    if not all_messages:
        logger.info("No unprofitable banners - notifications not sent")
        return False

    logger.info(f"Sending {len(all_messages)} messages to Telegram...")

    success_count = 0
    # Send all messages with small delay between them
    for i, message in enumerate(all_messages, 1):
        try:
            send_telegram_message(config, message)
            logger.info(f"Sent message {i}/{len(all_messages)}")
            success_count += 1
        except Exception as e:
            logger.error(f"Error sending message {i}: {e}")

        # Delay between messages to avoid flooding
        if i < len(all_messages):
            await asyncio.sleep(1)

    logger.info(f"Telegram messages sent: {success_count}/{len(all_messages)}")
    return success_count > 0


async def send_error_notification(
    config: Dict,
    error_message: str
) -> bool:
    """
    Send error notification to Telegram.

    Args:
        config: Configuration dict with telegram settings
        error_message: Error message to send

    Returns:
        True if sent successfully
    """
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enabled", False):
        return False

    try:
        send_telegram_message(config, f"<b>Error</b>\n\n{error_message}")
        return True
    except Exception as e:
        logger.error(f"Failed to send error to Telegram: {e}")
        return False


async def send_summary_notification(
    config: Dict,
    total_unprofitable: int,
    total_effective: int,
    total_testing: int,
    total_spent: float,
    total_goals: int,
    accounts_count: int,
    lookback_days: int,
    dry_run: bool = False
) -> bool:
    """
    Send summary notification after analysis completion.

    Args:
        config: Configuration dict with telegram settings
        total_unprofitable: Total unprofitable banners count
        total_effective: Total effective banners count
        total_testing: Total testing banners count
        total_spent: Total spend amount
        total_goals: Total goals count
        accounts_count: Number of accounts analyzed
        lookback_days: Analysis lookback period
        dry_run: Whether this was a dry run

    Returns:
        True if sent successfully
    """
    telegram_config = config.get("telegram", {})
    if not telegram_config.get("enabled", False):
        return False

    avg_cost = total_spent / total_goals if total_goals > 0 else 0
    mode_text = "DRY RUN" if dry_run else "LIVE"

    message = f"""<b>Analysis Summary ({mode_text})</b>

Accounts analyzed: {accounts_count}
Period: {lookback_days} days

<b>Results:</b>
Unprofitable: {total_unprofitable}
Effective: {total_effective}
Testing: {total_testing}

<b>Totals:</b>
Spent: {total_spent:.2f}₽
Goals: {total_goals}
Avg cost per goal: {avg_cost:.2f}₽
"""

    try:
        send_telegram_message(config, message)
        return True
    except Exception as e:
        logger.error(f"Failed to send summary to Telegram: {e}")
        return False
