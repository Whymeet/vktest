"""
ROI-based auto-reenable for disabled banners.
Enables disabled banners that have ROI >= threshold based on LeadsTech data.
"""
import time
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from utils.time_utils import get_moscow_time
from utils.vk_api.banner_stats import get_banners_paginated
from database import crud
from database.crud.leadstech import get_leadstech_roi_for_banners, get_leadstech_cabinets
from database.models import Account
from scheduler.config import VK_API_BASE_URL
from scheduler.reenable import enable_banner_with_parents
from scheduler.notifications import send_reenable_notification
from scheduler.event_logger import log_scheduler_event, EventType


def get_disabled_banners_from_vk(
    token: str,
    base_url: str = VK_API_BASE_URL
) -> List[int]:
    """
    Get all disabled (blocked) banner IDs from VK API.

    Args:
        token: VK API token
        base_url: VK API base URL

    Returns:
        List of disabled banner IDs
    """
    disabled_ids = []

    for batch in get_banners_paginated(
        token=token,
        base_url=base_url,
        fields="id,status",
        include_blocked=True,
        sleep_between_calls=0.1
    ):
        for banner in batch:
            if banner.get("status") == "blocked":
                banner_id = banner.get("id")
                if banner_id:
                    disabled_ids.append(banner_id)

    return disabled_ids


def run_roi_reenable_analysis(
    db: Session,
    user_id: int,
    username: str,
    roi_reenable_settings: Dict,
    telegram_config: Dict,
    should_stop_fn: Optional[Callable[[], bool]] = None,
    run_count: int = 0,
    logger=None
) -> Tuple[int, int, int, int]:
    """
    Run ROI-based auto-reenable analysis for disabled banners.

    Flow:
    1. Get disabled banners for specified accounts from VK API
    2. Get ROI data from LeadsTech analysis results
    3. Filter by ROI threshold
    4. Enable banners that meet the threshold

    Args:
        db: Database session
        user_id: User ID
        username: Username for logging
        roi_reenable_settings: ROI reenable configuration
        telegram_config: Telegram notification settings
        should_stop_fn: Optional callable to check if should stop
        run_count: Current run count for logging
        logger: Optional logger

    Returns:
        Tuple of (total_checked, total_reenabled, total_skipped, total_errors)
    """
    # Extract settings
    roi_threshold = roi_reenable_settings.get("roi_threshold", 50.0)
    dry_run = roi_reenable_settings.get("dry_run", True)
    lookback_days = roi_reenable_settings.get("lookback_days", 7)

    # Get enabled LeadsTech cabinets (same as used for LeadsTech analysis)
    enabled_cabinets = get_leadstech_cabinets(db, user_id=user_id, enabled_only=True)

    if logger:
        logger.info("")
        logger.info("=" * 60)
        logger.info("ROI AUTO-REENABLE DISABLED BANNERS")
        logger.info("=" * 60)
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   ROI threshold: >= {roi_threshold}%")
        logger.info(f"   Enabled LeadsTech cabinets: {len(enabled_cabinets)}")
        logger.info(f"   Lookback days (ROI period): {lookback_days}")
        logger.info(f"   Mode: {'DRY RUN (test)' if dry_run else 'REAL'}")
        logger.info(f"   Telegram: {'enabled' if telegram_config.get('enabled') else 'disabled'}")

    log_scheduler_event(
        EventType.REENABLE_STARTED,
        "ROI Reenable analysis started",
        username=username,
        user_id=str(user_id),
        run_count=run_count,
        extra_data={
            "roi_threshold": roi_threshold,
            "enabled_cabinets": len(enabled_cabinets),
            "lookback_days": lookback_days,
            "dry_run": dry_run,
            "type": "roi_reenable"
        }
    )

    if not enabled_cabinets:
        if logger:
            logger.warning("No enabled LeadsTech cabinets found, skipping ROI reenable")
        return 0, 0, 0, 0

    # Get account IDs from enabled cabinets and fetch Account objects
    cabinet_account_ids = [cab.account_id for cab in enabled_cabinets]
    selected_accounts = db.query(Account).filter(
        Account.id.in_(cabinet_account_ids),
        Account.user_id == user_id
    ).all()

    if not selected_accounts:
        if logger:
            logger.warning("No accounts found for enabled cabinets")
        return 0, 0, 0, 0

    # Get account names for filtering LeadsTech results
    account_names = [acc.name for acc in selected_accounts]

    if logger:
        logger.info(f"   Processing accounts: {', '.join(account_names)}")

    # Statistics
    total_checked = 0
    total_reenabled = 0
    total_skipped = 0
    total_errors = 0

    # List for Telegram notification
    reenabled_banners = []

    # Collect all disabled banners from all selected accounts
    all_disabled_banners: Dict[int, dict] = {}  # banner_id -> {account, token}

    for account in selected_accounts:
        if should_stop_fn and should_stop_fn():
            break

        if not account.api_token:
            if logger:
                logger.warning(f"Account '{account.name}' has no API token, skipping")
            continue

        if logger:
            logger.info(f"\n   Fetching disabled banners from '{account.name}'...")

        try:
            disabled_ids = get_disabled_banners_from_vk(account.api_token, VK_API_BASE_URL)
            if logger:
                logger.info(f"      Found {len(disabled_ids)} disabled banners")

            for banner_id in disabled_ids:
                all_disabled_banners[banner_id] = {
                    "account": account,
                    "account_name": account.name
                }
        except Exception as e:
            if logger:
                logger.error(f"      Error fetching banners: {e}")
            total_errors += 1

    if not all_disabled_banners:
        if logger:
            logger.info("\nNo disabled banners found in selected accounts")
        return 0, 0, 0, 0

    if logger:
        logger.info(f"\n   Total disabled banners across all accounts: {len(all_disabled_banners)}")

    # Get ROI data for all disabled banners
    disabled_banner_ids = list(all_disabled_banners.keys())
    roi_data = get_leadstech_roi_for_banners(
        db=db,
        user_id=user_id,
        banner_ids=disabled_banner_ids,
        account_names=account_names
    )

    if logger:
        logger.info(f"   Found ROI data for {len(roi_data)} banners")

    # Filter banners with ROI >= threshold
    profitable_banners = []
    for banner_id, data in roi_data.items():
        roi_percent = data.get("roi_percent")
        if roi_percent is not None and roi_percent >= roi_threshold:
            profitable_banners.append({
                "banner_id": banner_id,
                "roi_percent": roi_percent,
                "vk_spent": data.get("vk_spent", 0),
                "lt_revenue": data.get("lt_revenue", 0),
                "profit": data.get("profit", 0),
                "cabinet_name": data.get("cabinet_name"),
                "account_info": all_disabled_banners.get(banner_id)
            })

    if logger:
        logger.info(f"   Banners with ROI >= {roi_threshold}%: {len(profitable_banners)}")

    if not profitable_banners:
        if logger:
            logger.info("\nNo profitable disabled banners found")

        log_scheduler_event(
            EventType.REENABLE_COMPLETED,
            "ROI Reenable completed - no profitable disabled banners",
            username=username,
            user_id=str(user_id),
            run_count=run_count,
            extra_data={
                "total_checked": len(all_disabled_banners),
                "total_reenabled": 0,
                "type": "roi_reenable"
            }
        )
        return len(all_disabled_banners), 0, len(all_disabled_banners), 0

    # Enable profitable banners
    if logger:
        logger.info("\n" + "=" * 40)
        logger.info("ENABLING PROFITABLE BANNERS")
        logger.info("=" * 40)

    for banner_data in profitable_banners:
        if should_stop_fn and should_stop_fn():
            break

        banner_id = banner_data["banner_id"]
        roi_percent = banner_data["roi_percent"]
        account_info = banner_data["account_info"]

        if not account_info:
            total_errors += 1
            continue

        account = account_info["account"]
        account_name = account_info["account_name"]

        total_checked += 1

        if logger:
            logger.info(f"\n   [{banner_id}] ROI: {roi_percent:.1f}% | Spent: {banner_data['vk_spent']:.2f} | Revenue: {banner_data['lt_revenue']:.2f}")
            logger.info(f"      Account: {account_name}")

        # Enable banner with parents
        enable_result = enable_banner_with_parents(
            token=account.api_token,
            banner_id=banner_id,
            dry_run=dry_run,
            logger=logger
        )

        if enable_result.get("success"):
            total_reenabled += 1

            reenabled_banners.append({
                "account": account_name,
                "banner_id": banner_id,
                "banner_name": f"ID:{banner_id}",
                "roi_percent": roi_percent,
                "spent": banner_data["vk_spent"],
                "revenue": banner_data["lt_revenue"],
                "profit": banner_data["profit"],
                "campaign_enabled": enable_result.get("campaign_enabled", False),
                "group_enabled": enable_result.get("group_enabled", False)
            })

            if not dry_run:
                # Record action in history
                crud.create_banner_action(
                    db=db,
                    user_id=user_id,
                    banner_id=banner_id,
                    action="enabled",
                    account_name=account_name,
                    banner_name=None,
                    ad_group_id=None,
                    spend=banner_data["vk_spent"],
                    clicks=0,
                    shows=0,
                    conversions=0,
                    reason=f"ROI reenable: ROI {roi_percent:.1f}% >= {roi_threshold}%",
                    stats={
                        "roi_percent": roi_percent,
                        "vk_spent": banner_data["vk_spent"],
                        "lt_revenue": banner_data["lt_revenue"],
                        "profit": banner_data["profit"]
                    },
                    is_dry_run=dry_run
                )
                if logger:
                    logger.info(f"      Recorded in history")

            # Small delay between enables (VK API rate limit)
            time.sleep(0.15)
        else:
            total_errors += 1
            error_text = enable_result.get('error')
            if logger:
                logger.error(f"      Enable error: {error_text}")

    # Banners not in ROI data = skipped
    total_skipped = len(all_disabled_banners) - total_checked

    # Summary
    if logger:
        logger.info("")
        logger.info("=" * 60)
        logger.info("ROI REENABLE SUMMARY")
        logger.info(f"   Total disabled banners found: {len(all_disabled_banners)}")
        logger.info(f"   With ROI data: {len(roi_data)}")
        logger.info(f"   Meeting ROI threshold: {len(profitable_banners)}")
        logger.info(f"   Successfully enabled: {total_reenabled}")
        logger.info(f"   Errors: {total_errors}")
        if dry_run:
            logger.info(f"   DRY RUN mode - no actual changes made")
        logger.info("=" * 60)

    # Log event
    log_scheduler_event(
        EventType.REENABLE_COMPLETED,
        "ROI Reenable analysis completed",
        username=username,
        user_id=str(user_id),
        run_count=run_count,
        extra_data={
            "total_disabled": len(all_disabled_banners),
            "total_with_roi": len(roi_data),
            "total_profitable": len(profitable_banners),
            "total_reenabled": total_reenabled,
            "total_errors": total_errors,
            "roi_threshold": roi_threshold,
            "dry_run": dry_run,
            "type": "roi_reenable"
        }
    )

    # Send Telegram notification
    if telegram_config.get("enabled", False) and reenabled_banners:
        _send_roi_reenable_notification(
            telegram_config=telegram_config,
            reenabled_banners=reenabled_banners,
            roi_threshold=roi_threshold,
            total_disabled=len(all_disabled_banners),
            total_reenabled=total_reenabled,
            total_errors=total_errors,
            dry_run=dry_run,
            logger=logger
        )

    return len(all_disabled_banners), total_reenabled, total_skipped, total_errors


def _send_roi_reenable_notification(
    telegram_config: Dict,
    reenabled_banners: List[Dict],
    roi_threshold: float,
    total_disabled: int,
    total_reenabled: int,
    total_errors: int,
    dry_run: bool,
    logger=None
):
    """Send Telegram notification about ROI reenable results."""
    from scheduler.notifications import send_telegram_message

    chat_ids = telegram_config.get("chat_id", [])
    bot_token = telegram_config.get("bot_token")

    if not chat_ids or not bot_token:
        return

    # Build message
    mode_text = "🔬 ТЕСТ" if dry_run else "✅ ВЫПОЛНЕНО"
    header = f"📈 ROI Автовключение {mode_text}\n\n"

    summary = f"Порог ROI: >= {roi_threshold}%\n"
    summary += f"Проверено выключенных: {total_disabled}\n"
    summary += f"Включено: {total_reenabled}\n"
    if total_errors > 0:
        summary += f"Ошибок: {total_errors}\n"
    summary += "\n"

    # Banner details (limit to first 10)
    details = ""
    for i, banner in enumerate(reenabled_banners[:10]):
        details += f"• {banner['account']}\n"
        details += f"  ID: {banner['banner_id']}\n"
        details += f"  ROI: {banner['roi_percent']:.1f}%\n"
        details += f"  Потрачено: {banner['spent']:.2f}₽\n"
        details += f"  Доход: {banner['revenue']:.2f}₽\n"
        details += f"  Прибыль: {banner['profit']:.2f}₽\n"
        if banner.get('campaign_enabled'):
            details += f"  + Кампания включена\n"
        if banner.get('group_enabled'):
            details += f"  + Группа включена\n"
        details += "\n"

    if len(reenabled_banners) > 10:
        details += f"... и ещё {len(reenabled_banners) - 10} баннеров\n"

    message = header + summary + details

    # Send to all chat IDs
    for chat_id in chat_ids:
        try:
            send_telegram_message(bot_token, chat_id, message)
            if logger:
                logger.info(f"Telegram notification sent to {chat_id}")
        except Exception as e:
            if logger:
                logger.error(f"Failed to send Telegram notification: {e}")
