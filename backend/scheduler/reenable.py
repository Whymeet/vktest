"""
Scheduler reenable - Auto-enabling disabled banners
"""
import time
from datetime import timedelta
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from utils.time_utils import get_moscow_time
from utils.vk_api import (
    get_banner_info,
    get_ad_group_full,
    get_campaign_full,
    toggle_banner_status,
    toggle_ad_group_status,
    toggle_campaign_status
)
from database import crud
from database.models import BannerAction, DisableRule
from scheduler.config import VK_API_BASE_URL
from scheduler.stats import get_fresh_stats_batch
from scheduler.notifications import send_reenable_notification
from scheduler.event_logger import log_scheduler_event, EventType


def get_disabled_banners_for_period(
    db: Session,
    lookback_hours: int,
    user_id: int
) -> List[BannerAction]:
    """
    Get banners disabled within specified period for a user.

    Args:
        db: Database session
        lookback_hours: Hours to look back
        user_id: User ID

    Returns:
        List of unique BannerAction records (most recent per banner_id)
    """
    cutoff_time = get_moscow_time() - timedelta(hours=lookback_hours)

    query = db.query(BannerAction).filter(
        and_(
            BannerAction.user_id == user_id,
            BannerAction.action == 'disabled',
            BannerAction.created_at >= cutoff_time,
            BannerAction.is_dry_run == False
        )
    ).order_by(BannerAction.created_at.desc())

    all_actions = query.all()

    # Keep only unique banner_ids
    seen_banners = set()
    unique_actions = []
    for action in all_actions:
        if action.banner_id not in seen_banners:
            seen_banners.add(action.banner_id)
            unique_actions.append(action)

    return unique_actions


def should_reenable_banner(stats: Dict, rules: List[DisableRule]) -> bool:
    """
    Check if banner should be re-enabled based on current stats and rules.

    Args:
        stats: Current banner statistics
        rules: List of active disable rules

    Returns:
        True if banner should be re-enabled (doesn't match any rule)
    """
    matched_rule = crud.check_banner_against_rules(stats, rules)
    return matched_rule is None


def enable_banner_with_parents(
    token: str,
    banner_id: int,
    dry_run: bool = True,
    logger=None
) -> Dict:
    """
    Enable banner along with its ad group and campaign if they're disabled.

    Args:
        token: VK API token
        banner_id: Banner ID to enable
        dry_run: If True, don't make actual changes
        logger: Optional logger

    Returns:
        Dict with success status and details
    """
    result = {
        "success": False,
        "banner_enabled": False,
        "group_enabled": False,
        "campaign_enabled": False,
        "error": None
    }

    if dry_run:
        if logger:
            logger.info(f"[DRY RUN] Banner {banner_id} would be enabled")
        result["success"] = True
        result["dry_run"] = True
        return result

    try:
        # Get banner info
        banner_info = get_banner_info(token, VK_API_BASE_URL, banner_id)
        if not banner_info:
            result["error"] = f"Failed to get banner info for {banner_id}"
            return result

        ad_group_id = banner_info.get("ad_group_id")
        if not ad_group_id:
            result["error"] = f"Banner {banner_id} has no ad_group_id"
            return result

        # Get ad group info
        group_info = get_ad_group_full(token, VK_API_BASE_URL, ad_group_id)
        if not group_info:
            result["error"] = f"Failed to get ad group info for {ad_group_id}"
            return result

        group_status = group_info.get("status")
        campaign_id = group_info.get("ad_plan_id")

        if not campaign_id:
            result["error"] = f"Ad group {ad_group_id} has no ad_plan_id"
            return result

        # Get campaign info
        campaign_info = get_campaign_full(token, VK_API_BASE_URL, campaign_id)
        if not campaign_info:
            result["error"] = f"Failed to get campaign info for {campaign_id}"
            return result

        campaign_status = campaign_info.get("status")

        # Enable campaign if disabled
        if campaign_status != "active":
            if logger:
                logger.info(f"   Campaign {campaign_id} is disabled, enabling...")
            campaign_result = toggle_campaign_status(token, VK_API_BASE_URL, campaign_id, "active")
            if not campaign_result.get("success"):
                result["error"] = f"Failed to enable campaign: {campaign_result.get('error')}"
                return result
            result["campaign_enabled"] = True

        # Enable ad group if disabled
        if group_status != "active":
            if logger:
                logger.info(f"   Ad group {ad_group_id} is disabled, enabling...")
            group_result = toggle_ad_group_status(token, VK_API_BASE_URL, ad_group_id, "active")
            if not group_result.get("success"):
                result["error"] = f"Failed to enable ad group: {group_result.get('error')}"
                return result
            result["group_enabled"] = True

        # Enable banner
        banner_result = toggle_banner_status(token, VK_API_BASE_URL, banner_id, "active")
        if not banner_result.get("success"):
            result["error"] = f"Failed to enable banner: {banner_result.get('error')}"
            return result

        result["success"] = True
        result["banner_enabled"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def run_reenable_analysis(
    db: Session,
    user_id: int,
    username: str,
    reenable_settings: Dict,
    analysis_settings: Dict,
    telegram_config: Dict,
    should_stop_fn: Optional[Callable[[], bool]] = None,
    run_count: int = 0,
    logger=None
) -> Tuple[int, int, int, int]:
    """
    Run auto-reenable analysis for disabled banners.

    Args:
        db: Database session
        user_id: User ID
        username: Username for logging
        reenable_settings: Reenable configuration
        analysis_settings: Analysis settings (for lookback_days)
        telegram_config: Telegram notification settings
        should_stop_fn: Optional callable to check if should stop
        run_count: Current run count for logging
        logger: Optional logger

    Returns:
        Tuple of (total_checked, total_reenabled, total_skipped, total_errors)
    """
    lookback_hours = reenable_settings.get("lookback_hours", 24)
    dry_run = reenable_settings.get("dry_run", True)
    lookback_days = analysis_settings.get("lookback_days", 10)

    if logger:
        logger.info("")
        logger.info("=" * 60)
        logger.info("REENABLE DISABLED BANNERS (BATCH)")
        logger.info("=" * 60)
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Disabled search period: {lookback_hours} hours")
        logger.info(f"   Stats period (lookback_days): {lookback_days} days")
        logger.info(f"   Mode: {'DRY RUN (test)' if dry_run else 'REAL'}")
        logger.info(f"   Telegram: {'enabled' if telegram_config.get('enabled') else 'disabled'}")

    log_scheduler_event(
        EventType.REENABLE_STARTED,
        "Reenable analysis started",
        username=username,
        user_id=str(user_id),
        run_count=run_count,
        extra_data={
            "lookback_hours": lookback_hours,
            "lookback_days": lookback_days,
            "dry_run": dry_run
        }
    )

    # Get disabled banners for this user
    disabled_banners = get_disabled_banners_for_period(db, lookback_hours, user_id)

    if not disabled_banners:
        if logger:
            logger.info("No disabled banners found for the specified period")
        return 0, 0, 0, 0

    if logger:
        logger.info(f"Found {len(disabled_banners)} disabled banners to check")

    # Get user accounts
    accounts = crud.get_accounts(db, user_id=user_id)
    accounts_by_name = {acc.name: acc for acc in accounts}

    # Statistics
    total_checked = 0
    total_reenabled = 0
    total_skipped = 0
    total_errors = 0

    # List for Telegram notification
    reenabled_banners = []

    # Group by accounts
    banners_by_account: Dict[str, List[BannerAction]] = {}
    for banner_action in disabled_banners:
        account_name = banner_action.account_name
        if account_name not in banners_by_account:
            banners_by_account[account_name] = []
        banners_by_account[account_name].append(banner_action)

    for account_name, banner_actions in banners_by_account.items():
        if should_stop_fn and should_stop_fn():
            break

        account = accounts_by_name.get(account_name)
        if not account:
            if logger:
                logger.warning(f"Account '{account_name}' not found in DB")
            continue

        # Get rules for account
        rules = crud.get_rules_for_account(db, account.id, enabled_only=True)
        if not rules:
            if logger:
                logger.warning(f"No active rules for account '{account_name}', skipping")
            continue

        if logger:
            logger.info("")
            logger.info(f"Account: {account_name}")
            logger.info(f"   Banners to check: {len(banner_actions)}")
            logger.info(f"   Active rules: {len(rules)}")

        api_token = account.api_token
        account_reenabled = 0

        # BATCH OPTIMIZATION: get stats for ALL banners at once
        banner_ids = [ba.banner_id for ba in banner_actions]
        banner_actions_map = {ba.banner_id: ba for ba in banner_actions}

        if logger:
            logger.info(f"   Requesting stats in batches (100 banners per batch)...")

        start_time = time.time()
        all_stats = get_fresh_stats_batch(
            token=api_token,
            banner_ids=banner_ids,
            lookback_days=lookback_days,
            should_stop_fn=should_stop_fn,
            logger=logger
        )
        elapsed = time.time() - start_time

        if logger:
            logger.info(f"   Stats retrieved in {elapsed:.1f} sec")

        # Process results
        for banner_id, fresh_stats in all_stats.items():
            if should_stop_fn and should_stop_fn():
                break

            banner_action = banner_actions_map.get(banner_id)
            if not banner_action:
                continue

            banner_name = banner_action.banner_name or f"ID:{banner_id}"
            total_checked += 1

            if fresh_stats is None:
                if logger:
                    logger.error(f"   [{banner_id}] Failed to get stats")
                total_errors += 1
                continue

            spent = fresh_stats.get('spent', 0)
            goals = fresh_stats.get('goals', 0)
            clicks = fresh_stats.get('clicks', 0)

            # Check if should reenable
            if should_reenable_banner(fresh_stats, rules):
                if logger:
                    logger.info(f"   [{banner_id}] {banner_name}")
                    logger.info(f"      Stats: spent={spent:.2f}, goals={goals}, clicks={clicks}")
                    logger.info(f"      No matching rules -> ENABLING")

                enable_result = enable_banner_with_parents(api_token, banner_id, dry_run, logger)

                if enable_result.get("success"):
                    total_reenabled += 1
                    account_reenabled += 1

                    reenabled_banners.append({
                        "account": account_name,
                        "banner_id": banner_id,
                        "banner_name": banner_name,
                        "spent": spent,
                        "goals": goals,
                        "clicks": clicks,
                        "campaign_enabled": enable_result.get("campaign_enabled", False),
                        "group_enabled": enable_result.get("group_enabled", False)
                    })

                    if not dry_run:
                        crud.create_banner_action(
                            db=db,
                            user_id=account.user_id,
                            banner_id=banner_id,
                            action="enabled",
                            account_name=account_name,
                            banner_name=banner_action.banner_name,
                            ad_group_id=banner_action.ad_group_id,
                            spend=spent,
                            clicks=clicks,
                            shows=fresh_stats.get("shows", 0),
                            conversions=goals,
                            reason="Auto-reenable: stats updated, no matching rules",
                            stats=fresh_stats,
                            is_dry_run=dry_run
                        )
                        if logger:
                            logger.info(f"      Recorded in history")

                    # Small delay between enables (VK API rate limit)
                    time.sleep(0.1)
                else:
                    total_errors += 1
                    error_text = enable_result.get('error')
                    if logger:
                        logger.error(f"      Enable error: {error_text}")
            else:
                total_skipped += 1
                if logger:
                    logger.debug(f"   [{banner_id}] Still matches rules (spent={spent:.2f}, goals={goals})")

        if account_reenabled > 0 and logger:
            logger.info(f"   Account total: enabled {account_reenabled} banners")

    # Summary
    if logger:
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"REENABLE SUMMARY")
        logger.info(f"   Checked: {total_checked}")
        logger.info(f"   Enabled: {total_reenabled}")
        logger.info(f"   Skipped (still match rules): {total_skipped}")
        logger.info(f"   Errors: {total_errors}")
        if dry_run:
            logger.info(f"   DRY RUN mode - no actual changes made")
        logger.info("=" * 60)

    # Log event
    log_scheduler_event(
        EventType.REENABLE_COMPLETED,
        "Reenable analysis completed",
        username=username,
        user_id=str(user_id),
        run_count=run_count,
        extra_data={
            "total_checked": total_checked,
            "total_reenabled": total_reenabled,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "dry_run": dry_run
        }
    )

    # Send Telegram notification
    if telegram_config.get("enabled", False):
        send_reenable_notification(
            telegram_config=telegram_config,
            reenabled_banners=reenabled_banners,
            total_checked=total_checked,
            total_reenabled=total_reenabled,
            total_skipped=total_skipped,
            total_errors=total_errors,
            dry_run=dry_run,
            lookback_hours=lookback_hours,
            lookback_days=lookback_days,
            logger=logger
        )

    return total_checked, total_reenabled, total_skipped, total_errors
