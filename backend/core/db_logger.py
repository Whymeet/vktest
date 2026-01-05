"""
Core DB logger - Async database logging for analysis results
"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from database import SessionLocal
from database import crud
from utils.logging_setup import get_logger

logger = get_logger(service="vk_api", function="db_logger")


async def log_disabled_banners_to_db(
    banners: List[Dict],
    disable_results: Optional[Dict],
    account_name: str,
    lookback_days: int,
    date_from: str,
    date_to: str,
    is_dry_run: bool = False,
    user_id: Optional[int] = None,
    roi_data: Optional[Dict] = None
) -> int:
    """
    Log disabled banners to database asynchronously.

    Runs in a thread pool to avoid blocking the event loop.

    Args:
        banners: List of banner data dicts with matched_rule info
        disable_results: Results from disable operation (or None)
        account_name: Account name for logging
        lookback_days: Analysis lookback period
        date_from: Analysis start date
        date_to: Analysis end date
        is_dry_run: Whether this was a dry run
        user_id: User ID (if None, gets from environment)
        roi_data: Optional dict mapping banner_id -> BannerROIData with ROI metrics

    Returns:
        Number of banners logged successfully
    """
    if user_id is None:
        user_id = int(os.environ.get('VK_ADS_USER_ID', 0)) or None

    def _log_to_db() -> int:
        db = SessionLocal()
        try:
            logged_count = 0
            for banner_data in banners:
                banner_id = banner_data.get("id")

                # Check disable result for this banner
                disable_success = True
                if disable_results and isinstance(disable_results, dict):
                    result = disable_results.get(str(banner_id)) or disable_results.get(banner_id)
                    if result:
                        disable_success = result.get("success", True)

                # Get disable reason (rule name)
                matched_rule = banner_data.get("matched_rule", "Rule not specified")

                try:
                    crud.log_disabled_banner(
                        db=db,
                        banner_data=banner_data,
                        account_name=account_name,
                        lookback_days=lookback_days,
                        date_from=date_from,
                        date_to=date_to,
                        is_dry_run=is_dry_run,
                        disable_success=disable_success,
                        reason=matched_rule,
                        user_id=user_id,
                        roi_data=roi_data
                    )
                    logged_count += 1
                except Exception as e:
                    logger.error(f"DB write error for banner {banner_id}: {e}")

            logger.info(f"[{account_name}] Logged to DB: {logged_count} disabled banners")
            return logged_count
        except Exception as e:
            logger.error(f"DB logging error: {e}")
            return 0
        finally:
            db.close()

    # Run DB write in thread pool to not block async
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _log_to_db)


async def save_account_stats_to_db(
    account_name: str,
    stats_date: str,
    over_limit: List[Dict],
    under_limit: List[Dict],
    no_activity: List[Dict],
    total_spent: float,
    total_conversions: int,
    lookback_days: int,
    vk_account_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> bool:
    """
    Save account statistics to database asynchronously.

    Args:
        account_name: Account name
        stats_date: Statistics date (YYYY-MM-DD)
        over_limit: List of unprofitable banners
        under_limit: List of effective banners
        no_activity: List of testing/inactive banners
        total_spent: Total spend amount
        total_conversions: Total conversions count
        lookback_days: Analysis lookback period
        vk_account_id: VK account ID (optional)
        user_id: User ID (if None, gets from environment)

    Returns:
        True if saved successfully
    """
    if user_id is None:
        user_id = int(os.environ.get('VK_ADS_USER_ID', 0)) or None

    def _save_stats() -> bool:
        db = SessionLocal()
        try:
            # Calculate totals
            all_banners = over_limit + under_limit + no_activity
            total_clicks = sum(b.get("clicks", 0) for b in all_banners)
            total_shows = sum(b.get("shows", 0) for b in all_banners)

            crud.save_account_stats(
                db=db,
                account_name=account_name,
                stats_date=stats_date,
                active_banners=len(all_banners),
                disabled_banners=len(over_limit),
                over_limit_banners=len(over_limit),
                under_limit_banners=len(under_limit),
                no_activity_banners=len(no_activity),
                total_spend=total_spent,
                total_clicks=int(total_clicks),
                total_shows=int(total_shows),
                total_conversions=total_conversions,
                lookback_days=lookback_days,
                vk_account_id=vk_account_id,
                user_id=user_id
            )
            logger.info(f"[{account_name}] Statistics saved to DB")
            return True
        except Exception as e:
            logger.error(f"Error saving statistics to DB: {e}")
            return False
        finally:
            db.close()

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _save_stats)


def get_account_rules(account_name: str, user_id: Optional[int] = None) -> list:
    """
    Get active disable rules for an account.

    Args:
        account_name: Account name
        user_id: User ID (optional, for future multi-tenant support)

    Returns:
        List of DisableRule objects
    """
    db = SessionLocal()
    try:
        return crud.get_rules_for_account_by_name(db, account_name, enabled_only=True)
    finally:
        db.close()
