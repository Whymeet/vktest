"""
Core analyzer - Banner analysis logic with streaming batch processing
"""
import asyncio
import aiohttp
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from database import crud, SessionLocal
from database.models import DisableRule, Account, LeadsTechConfig
from utils.vk_api_async import (
    get_banners_active,
    get_banners_stats_batched,
    disable_banners_batch,
    trigger_statistics_refresh,
)
from utils.logging_setup import get_logger

from core.config_loader import AnalysisConfig
from core.db_logger import log_disabled_banners_to_db, save_account_stats_to_db, get_account_rules

logger = get_logger(service="vk_api", function="analyzer")


async def _load_roi_for_account(
    account_name: str,
    banner_ids: List[int],
    date_from: str,
    date_to: str,
    rules: List[DisableRule],
    user_id: Optional[int] = None,
    vk_spent_cache: Optional[Dict[int, float]] = None
) -> Optional[Dict]:
    """
    Load ROI data for an account if rules use ROI metric.

    Runs in a thread pool to avoid blocking the event loop.

    ОПТИМИЗАЦИЯ: если передан vk_spent_cache, не делает запросов к VK API,
    а использует уже загруженные данные о spent. Это экономит API лимиты.

    Args:
        account_name: Account name
        banner_ids: List of banner IDs to load ROI for
        date_from: Analysis start date (YYYY-MM-DD)
        date_to: Analysis end date (YYYY-MM-DD)
        rules: Disable rules for the account
        user_id: User ID
        vk_spent_cache: Pre-loaded VK spent data {banner_id: spent_amount}

    Returns:
        Dict mapping banner_id -> BannerROIData, or None if not configured
    """
    if user_id is None:
        user_id = int(os.environ.get('VK_ADS_USER_ID', 0)) or None

    if not user_id:
        logger.warning("No user_id for ROI loading")
        return None

    def _load_roi_sync() -> Optional[Dict]:
        db = SessionLocal()
        try:
            # Get LeadsTech config for user
            lt_config = db.query(LeadsTechConfig).filter(
                LeadsTechConfig.user_id == user_id
            ).first()

            if not lt_config:
                logger.warning(f"No LeadsTech config found for user {user_id}")
                return None

            # Get account with label
            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.name == account_name
            ).first()

            if not account:
                logger.warning(f"Account not found: {account_name}")
                return None

            if not account.label or not account.leadstech_enabled:
                logger.info(f"Account {account_name} has no label or LeadsTech disabled")
                return None

            # Import LeadsTech client and ROI loader
            from leadstech.leadstech_client import LeadstechClient, LeadstechClientConfig
            from leadstech.roi_loader_disable import load_roi_for_banners_sync
            from leadstech.vk_client import VkAdsClient, VkAdsConfig

            # Create LeadsTech client
            lt_client_config = LeadstechClientConfig(
                base_url=lt_config.base_url,
                login=lt_config.login,
                password=lt_config.password
            )
            lt_client = LeadstechClient(lt_client_config)

            # Create VK client for account (will only be used if no cache)
            vk_config = VkAdsConfig(
                base_url="https://ads.vk.com/api/v2",
                api_token=account.api_token
            )
            vk_client = VkAdsClient(vk_config)

            # Determine sub field from rules
            sub_fields = set()
            for rule in rules:
                if rule.roi_sub_field:
                    sub_fields.add(rule.roi_sub_field)
            if not sub_fields:
                sub_fields = {"sub4", "sub5"}  # Default to both

            # Convert dates
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()

            # Load ROI for each sub field, passing VK spent cache to avoid extra API calls
            all_roi_data = {}
            for sub_field in sub_fields:
                try:
                    roi_result = load_roi_for_banners_sync(
                        lt_client=lt_client,
                        vk_client=vk_client,
                        account=account,
                        banner_ids=banner_ids,
                        date_from=date_from_obj,
                        date_to=date_to_obj,
                        sub_field=sub_field,
                        vk_spent_cache=vk_spent_cache  # Pass cache to avoid VK API calls
                    )
                    # Merge results (first found wins)
                    for bid, roi_info in roi_result.items():
                        if bid not in all_roi_data:
                            all_roi_data[bid] = roi_info
                except Exception as e:
                    logger.error(f"Error loading ROI with {sub_field}: {e}")
                    continue

            return all_roi_data if all_roi_data else None

        except Exception as e:
            logger.error(f"Error loading ROI data: {e}")
            return None
        finally:
            db.close()

    # Run in thread pool to not block async
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _load_roi_sync)


def _iso(d: date) -> str:
    """Format date to ISO string"""
    return d.isoformat()


def prepare_banner_info(banners: List[Dict]) -> Tuple[List[int], Dict[int, Dict]]:
    """
    Prepare banner IDs list and info dictionary from raw banner data.

    Args:
        banners: Raw banner data from VK API

    Returns:
        Tuple of (banner_ids list, banners_info dict)
    """
    banner_ids = []
    banners_info = {}

    for b in banners:
        bid = b.get("id")
        if not bid:
            continue

        banner_ids.append(bid)

        # Extract delivery status
        delivery = b.get("delivery")
        if isinstance(delivery, dict):
            delivery_status = delivery.get("status", "N/A")
        elif isinstance(delivery, str):
            delivery_status = delivery
        else:
            delivery_status = "N/A"

        banners_info[bid] = {
            "name": b.get("name", "Unknown"),
            "status": b.get("status", "N/A"),
            "ad_group_id": b.get("ad_group_id", "N/A"),
            "moderation_status": b.get("moderation_status", "N/A"),
            "delivery": delivery_status,
        }

    return banner_ids, banners_info


def calculate_banner_metrics(banner: Dict) -> Dict:
    """
    Calculate derived metrics for banner analysis.

    Args:
        banner: Banner data with spent, clicks, shows, vk_goals

    Returns:
        Dict with all metrics including calculated ones
    """
    spent = banner.get("spent", 0.0)
    clicks = banner.get("clicks", 0.0)
    shows = banner.get("shows", 0.0)
    vk_goals = banner.get("vk_goals", 0.0)

    return {
        "goals": vk_goals,
        "vk_goals": vk_goals,
        "spent": spent,
        "clicks": clicks,
        "shows": shows,
        "ctr": (clicks / shows * 100) if shows > 0 else 0,
        "cpc": (spent / clicks) if clicks > 0 else float('inf'),
        "cost_per_goal": (spent / vk_goals) if vk_goals > 0 else float('inf'),
    }


def check_banner_profitability(
    banner: Dict,
    rules: List[DisableRule],
    whitelist: Set[int],
    roi_data: Optional[Dict] = None
) -> Tuple[bool, Optional[DisableRule], str]:
    """
    Check if banner should be disabled based on rules.

    Args:
        banner: Banner data with metrics
        rules: List of disable rules
        whitelist: Set of whitelisted banner IDs
        roi_data: Optional dict mapping banner_id -> BannerROIData for ROI metric

    Returns:
        Tuple of (is_unprofitable, matched_rule, category)
        category: 'whitelisted', 'unprofitable', 'effective', 'testing', 'inactive'
    """
    bid = banner.get("id")

    # Check whitelist first
    if bid in whitelist:
        return False, None, "whitelisted"

    # Calculate metrics for rule checking
    metrics = calculate_banner_metrics(banner)
    metrics["id"] = bid  # Add banner ID for ROI lookup

    # Check against rules (pass roi_data for ROI metric support)
    matched_rule = crud.check_banner_against_rules(metrics, rules, roi_data)

    if matched_rule:
        return True, matched_rule, "unprofitable"

    # Categorize based on goals
    vk_goals = banner.get("vk_goals", 0)
    spent = banner.get("spent", 0)

    if vk_goals >= 1:
        return False, None, "effective"
    elif spent > 0:
        return False, None, "testing"
    else:
        return False, None, "inactive"


async def process_banner_batch(
    session: aiohttp.ClientSession,
    batch_banners: List[Dict],
    rules: List[DisableRule],
    whitelist: Set[int],
    account_name: str,
    access_token: str,
    base_url: str,
    dry_run: bool,
    lookback_days: int,
    date_from: str,
    date_to: str,
    user_id: int,
    roi_data: Optional[Dict] = None
) -> Dict:
    """
    Process a single batch of banners: analyze and disable unprofitable ones.

    Args:
        session: aiohttp session
        batch_banners: List of banners in this batch
        rules: Disable rules for the account
        whitelist: Whitelisted banner IDs
        account_name: Account name for logging
        access_token: VK API token
        base_url: VK API base URL
        dry_run: Whether to actually disable
        lookback_days: Analysis period
        date_from: Analysis start date
        date_to: Analysis end date
        user_id: User ID for DB logging
        roi_data: Optional dict mapping banner_id -> BannerROIData for ROI metric

    Returns:
        Dict with categorized banners and disable results
    """
    over_limit = []
    under_limit = []
    no_activity = []
    whitelisted = []

    for b in batch_banners:
        bid = b.get("id")
        name = b.get("name", "Unknown")
        status = b.get("status", "N/A")
        ad_group_id = b.get("ad_group_id", "N/A")
        moderation_status = b.get("moderation_status", "N/A")
        delivery_status = b.get("delivery", "N/A")

        spent = b.get("spent", 0.0)
        clicks = b.get("clicks", 0.0)
        shows = b.get("shows", 0.0)
        vk_goals = b.get("vk_goals", 0.0)

        banner_data = {
            "id": bid,
            "name": name,
            "spent": spent,
            "clicks": clicks,
            "shows": shows,
            "vk_goals": vk_goals,
            "status": status,
            "delivery": delivery_status,
            "ad_group_id": ad_group_id,
            "moderation_status": moderation_status,
            "account": account_name
        }

        is_unprofitable, matched_rule, category = check_banner_profitability(
            banner_data, rules, whitelist, roi_data
        )

        if category == "whitelisted":
            whitelisted.append(banner_data)
            logger.debug(f"[{account_name}] Skipping {bid} - whitelisted")

        elif is_unprofitable and matched_rule:
            banner_data["matched_rule"] = matched_rule.name
            banner_data["matched_rule_id"] = matched_rule.id
            over_limit.append(banner_data)

            metrics = calculate_banner_metrics(banner_data)
            metrics["id"] = bid  # Add banner ID for ROI lookup
            reason = crud.format_rule_match_reason(matched_rule, metrics, roi_data)
            logger.info(f"[{account_name}] UNPROFITABLE: [{bid}] {name}")
            logger.info(f"   {reason.replace(chr(10), chr(10) + '   ')}")

        elif category == "effective":
            under_limit.append(banner_data)
            logger.debug(f"[{account_name}] EFFECTIVE: [{bid}] {name} ({int(vk_goals)} goals)")

        else:
            no_activity.append(banner_data)
            if spent > 0:
                logger.debug(f"[{account_name}] TESTING: [{bid}] {name} ({spent:.2f}₽)")

    # Disable unprofitable banners from this batch
    disable_results = None
    if over_limit:
        logger.info(f"[{account_name}] Disabling {len(over_limit)} unprofitable from batch...")

        disable_results = await disable_banners_batch(
            session, access_token, base_url, over_limit,
            dry_run=dry_run,
            whitelist_ids=whitelist,
            concurrency=5
        )

        # Log to DB immediately
        await log_disabled_banners_to_db(
            banners=over_limit,
            disable_results=disable_results,
            account_name=account_name,
            lookback_days=lookback_days,
            date_from=date_from,
            date_to=date_to,
            is_dry_run=dry_run,
            user_id=user_id,
            roi_data=roi_data
        )

    return {
        "over_limit": over_limit,
        "under_limit": under_limit,
        "no_activity": no_activity,
        "whitelisted": whitelisted,
        "disable_results": disable_results
    }


async def analyze_account(
    session: aiohttp.ClientSession,
    account_name: str,
    access_token: str,
    config: AnalysisConfig,
    account_trigger_id: Optional[int] = None
) -> Optional[Dict]:
    """
    Analyze one VK Ads account asynchronously with streaming batch processing.

    Args:
        session: aiohttp session
        account_name: Account name
        access_token: VK API access token
        config: Analysis configuration
        account_trigger_id: Optional trigger ID for this account

    Returns:
        Analysis result dict or None on error
    """
    logger.info("=" * 100)
    logger.info(f"STARTING ACCOUNT ANALYSIS: {account_name}")
    logger.info("=" * 100)

    try:
        # Get effective lookback days (including extra from env)
        from core.config_loader import get_extra_lookback_days
        extra_days = get_extra_lookback_days()
        lookback_days = config.get_effective_lookback_days(extra_days)

        # Prepare trigger config
        trigger_config = {
            "enabled": config.statistics_trigger.enabled and account_trigger_id is not None,
            "wait_seconds": config.statistics_trigger.wait_seconds,
            "group_id": account_trigger_id
        }

        if trigger_config["enabled"]:
            logger.info(f"Using trigger for {account_name}: group {account_trigger_id}")
        else:
            logger.info(f"Trigger disabled for {account_name}")

        # Trigger statistics refresh
        trigger_result = await trigger_statistics_refresh(
            session, access_token, config.base_url, trigger_config
        )
        if not trigger_result.get("success") and not trigger_result.get("skipped"):
            logger.warning(f"Trigger failed: {trigger_result.get('error')}")

        # Load rules for this account
        account_rules = get_account_rules(account_name)
        logger.info(f"[{account_name}] Loaded {len(account_rules)} disable rules")

        for rule in account_rules:
            conditions_str = ", ".join([
                f"{c.metric} {c.operator} {c.value}" for c in rule.conditions
            ])
            logger.info(f"   Rule \"{rule.name}\": {conditions_str}")

        # Skip if no rules
        if not account_rules:
            logger.warning(f"[{account_name}] No active rules - skipping")
            return {
                "account_name": account_name,
                "over_limit": [],
                "under_limit": [],
                "no_activity": [],
                "total_spent": 0.0,
                "total_vk_goals": 0,
                "matched_rules": [],
                "disable_results": None,
                "date_from": _iso(date.today() - timedelta(days=lookback_days)),
                "date_to": _iso(date.today()),
                "skipped": True
            }

        # Determine analysis period
        today = date.today()
        date_from = _iso(today - timedelta(days=lookback_days))
        date_to = _iso(today)

        logger.info(f"Account: {account_name}")
        logger.info(f"Period: {date_from} — {date_to} ({lookback_days} days)")

        # Load active banners
        banners = await get_banners_active(
            session, access_token, config.base_url,
            sleep_between_calls=config.settings.sleep_between_calls
        )
        logger.info(f"[{account_name}] Active banners: {len(banners)}")

        if len(banners) == 0:
            logger.warning(f"[{account_name}] No active banners found!")
            return {
                "account_name": account_name,
                "over_limit": [],
                "under_limit": [],
                "no_activity": [],
                "total_spent": 0.0,
                "total_vk_goals": 0,
                "rules_count": len(account_rules),
                "disable_results": None,
                "date_from": date_from,
                "date_to": date_to
            }

        # Prepare banner info
        banner_ids, banners_info = prepare_banner_info(banners)

        # Check if any rule uses ROI metric
        rules_use_roi = any(
            any(c.metric == "roi" for c in rule.conditions)
            for rule in account_rules
        )

        # ФАЗА 1: Загружаем статистику всех батчей и собираем кэш spent
        # Это нужно до загрузки ROI чтобы не делать лишние VK API запросы
        logger.info(f"PHASE 1: Loading statistics for {account_name}")
        logger.info("=" * 80)

        all_banners_with_stats = []
        vk_spent_cache: Dict[int, float] = {}  # Кэш spent для ROI загрузки

        async for batch_data in get_banners_stats_batched(
            session, access_token, config.base_url, date_from, date_to,
            banner_ids=banner_ids,
            banners_info=banners_info,
            metrics="base",
            batch_size=200,  # VK API max is ~250
            sleep_between_calls=config.settings.sleep_between_calls
        ):
            batch_num = batch_data["batch_num"]
            total_batches = batch_data["total_batches"]
            batch_banners = batch_data["banners"]
            stats_map = batch_data.get("stats_map", {})

            logger.info(f"[{account_name}] Loaded batch {batch_num}/{total_batches} ({len(batch_banners)} banners)")

            # Собираем все баннеры и кэш spent
            all_banners_with_stats.extend(batch_banners)
            for bid, stats in stats_map.items():
                vk_spent_cache[bid] = stats.get("spent", 0.0)

        logger.info(f"[{account_name}] Phase 1 complete: {len(all_banners_with_stats)} banners, spent cache: {len(vk_spent_cache)}")

        # ФАЗА 2: Загружаем ROI данные с кэшем spent (без VK API запросов!)
        roi_data = None
        if rules_use_roi:
            logger.info(f"PHASE 2: Loading ROI data for {account_name}")
            logger.info("=" * 80)
            logger.info(f"[{account_name}] Rules use ROI metric, loading LeadsTech data (using spent cache)...")

            roi_data = await _load_roi_for_account(
                account_name=account_name,
                banner_ids=banner_ids,
                date_from=date_from,
                date_to=date_to,
                rules=account_rules,
                user_id=config.user_id,
                vk_spent_cache=vk_spent_cache  # Передаём кэш чтобы не делать VK API запросы
            )
            if roi_data:
                logger.info(f"[{account_name}] Loaded ROI data for {len(roi_data)} banners")
            else:
                logger.warning(f"[{account_name}] No ROI data loaded (LeadsTech not configured?)")

        # ФАЗА 3: Анализируем баннеры и отключаем убыточные (одним массовым запросом)
        logger.info(f"PHASE 3: Analyzing and disabling unprofitable banners for {account_name}")
        logger.info("=" * 80)

        # Accumulators
        all_over_limit = []
        all_under_limit = []
        all_no_activity = []
        all_whitelisted = []

        # Анализируем все баннеры
        for b in all_banners_with_stats:
            bid = b.get("id")
            banner_data = {
                "id": bid,
                "name": b.get("name", "Unknown"),
                "spent": b.get("spent", 0.0),
                "clicks": b.get("clicks", 0.0),
                "shows": b.get("shows", 0.0),
                "vk_goals": b.get("vk_goals", 0.0),
                "status": b.get("status", "N/A"),
                "delivery": b.get("delivery", "N/A"),
                "ad_group_id": b.get("ad_group_id", "N/A"),
                "moderation_status": b.get("moderation_status", "N/A"),
                "account": account_name
            }

            is_unprofitable, matched_rule, category = check_banner_profitability(
                banner_data, account_rules, config.whitelist, roi_data
            )

            if category == "whitelisted":
                all_whitelisted.append(banner_data)
            elif is_unprofitable and matched_rule:
                banner_data["matched_rule"] = matched_rule.name
                banner_data["matched_rule_id"] = matched_rule.id
                all_over_limit.append(banner_data)

                metrics = calculate_banner_metrics(banner_data)
                metrics["id"] = bid
                reason = crud.format_rule_match_reason(matched_rule, metrics, roi_data)
                logger.info(f"[{account_name}] UNPROFITABLE: [{bid}] {banner_data['name']}")
                logger.info(f"   {reason.replace(chr(10), chr(10) + '   ')}")
            elif category == "effective":
                all_under_limit.append(banner_data)
            else:
                all_no_activity.append(banner_data)

        # Отключаем все убыточные баннеры одним массовым запросом
        all_disable_results = []
        if all_over_limit:
            logger.info(f"[{account_name}] Disabling {len(all_over_limit)} unprofitable banners (single mass_action request)...")

            disable_results = await disable_banners_batch(
                session, access_token, config.base_url, all_over_limit,
                dry_run=config.settings.dry_run,
                whitelist_ids=config.whitelist,
                concurrency=5  # Deprecated, mass_action используется
            )

            all_disable_results.append(disable_results)

            # Log to DB
            await log_disabled_banners_to_db(
                banners=all_over_limit,
                disable_results=disable_results,
                account_name=account_name,
                lookback_days=lookback_days,
                date_from=date_from,
                date_to=date_to,
                is_dry_run=config.settings.dry_run,
                user_id=config.user_id,
                roi_data=roi_data
            )

        logger.info(
            f"[{account_name}] Analysis complete: "
            f"unprofitable={len(all_over_limit)}, effective={len(all_under_limit)}, "
            f"testing/inactive={len(all_no_activity)}, whitelisted={len(all_whitelisted)}"
        )

        # Final statistics
        logger.info("=" * 80)
        logger.info(f"FINAL STATISTICS: {account_name}")
        logger.info(f"Unprofitable (by rules): {len(all_over_limit)}")
        logger.info(f"Effective: {len(all_under_limit)}")
        logger.info(f"Testing/Inactive: {len(all_no_activity)}")
        logger.info(f"Whitelisted: {len(all_whitelisted)}")
        logger.info(f"Total active: {len(banners)}")

        all_banners = all_over_limit + all_under_limit + all_no_activity
        total_spent = sum(b["spent"] for b in all_banners)
        total_vk_goals = sum(b["vk_goals"] for b in all_banners)

        logger.info(f"[{account_name}] Total spent: {total_spent:.2f}₽")
        logger.info(f"[{account_name}] Total VK goals: {int(total_vk_goals)}")

        # Combine disable results
        combined_disable_results = {
            "disabled": sum(r.get("disabled", 0) for r in all_disable_results),
            "failed": sum(r.get("failed", 0) for r in all_disable_results),
            "skipped": sum(r.get("skipped", 0) for r in all_disable_results),
            "total": sum(r.get("total", 0) for r in all_disable_results),
            "dry_run": config.settings.dry_run,
            "results": []
        }
        for r in all_disable_results:
            combined_disable_results["results"].extend(r.get("results", []))

        # Save account stats to DB
        await save_account_stats_to_db(
            account_name=account_name,
            stats_date=date_to,
            over_limit=all_over_limit,
            under_limit=all_under_limit,
            no_activity=all_no_activity,
            total_spent=total_spent,
            total_conversions=int(total_vk_goals),
            lookback_days=lookback_days,
            user_id=config.user_id
        )

        logger.info(f"[{account_name}] Analysis complete!")

        return {
            "account_name": account_name,
            "over_limit": all_over_limit,
            "under_limit": all_under_limit,
            "no_activity": all_no_activity,
            "total_spent": total_spent,
            "total_vk_goals": int(total_vk_goals),
            "rules_count": len(account_rules),
            "disable_results": combined_disable_results if all_over_limit else None,
            "date_from": date_from,
            "date_to": date_to
        }

    except Exception as e:
        logger.error(f"[{account_name}] ANALYSIS ERROR: {e}")
        logger.exception("Error details:")
        return None
