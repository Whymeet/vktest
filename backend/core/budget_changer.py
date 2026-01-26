"""
Budget Changer - Automatic ad group budget adjustment based on rules
Similar to analyzer.py but changes budgets instead of disabling banners
"""
import asyncio
import aiohttp
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from database import crud, SessionLocal
from database.models import BudgetRule, Account, LeadsTechConfig
from utils.vk_api_async import (
    get_banners_active,
    get_banners_stats_batched,
    change_ad_group_budget_percent,
)
from utils.logging_setup import get_logger

logger = get_logger(service="vk_api", function="budget_changer")


def _iso(d: date) -> str:
    """Format date to ISO string"""
    return d.isoformat()


async def _load_roi_for_account(
    account_name: str,
    banner_ids: List[int],
    date_from: str,
    date_to: str,
    rules: List[BudgetRule],
    user_id: Optional[int] = None,
    vk_spent_cache: Optional[Dict[int, float]] = None
) -> Optional[Dict]:
    """
    Load ROI data for an account if rules use ROI metric.
    (Same logic as in analyzer.py)
    """
    if user_id is None:
        user_id = int(os.environ.get('VK_ADS_USER_ID', 0)) or None

    if not user_id:
        logger.warning("No user_id for ROI loading")
        return None

    def _load_roi_sync() -> Optional[Dict]:
        db = SessionLocal()
        try:
            lt_config = db.query(LeadsTechConfig).filter(
                LeadsTechConfig.user_id == user_id
            ).first()

            if not lt_config:
                return None

            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.name == account_name
            ).first()

            if not account:
                return None

            if not account.label or not account.leadstech_enabled:
                return None

            from leadstech.leadstech_client import LeadstechClient, LeadstechClientConfig
            from leadstech.roi_loader_disable import load_roi_for_banners_sync
            from leadstech.vk_client import VkAdsClient, VkAdsConfig

            lt_client_config = LeadstechClientConfig(
                base_url=lt_config.base_url,
                login=lt_config.login,
                password=lt_config.password
            )
            lt_client = LeadstechClient(lt_client_config, db=db, user_id=user_id)

            vk_config = VkAdsConfig(
                base_url="https://ads.vk.com/api/v2",
                api_token=account.api_token
            )
            vk_client = VkAdsClient(vk_config)

            sub_fields = set()
            for rule in rules:
                if rule.roi_sub_field:
                    sub_fields.add(rule.roi_sub_field)
            if not sub_fields:
                sub_fields = {"sub4", "sub5"}

            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()

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
                        vk_spent_cache=vk_spent_cache
                    )
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

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _load_roi_sync)


def calculate_banner_metrics(banner: Dict) -> Dict:
    """Calculate derived metrics for banner analysis."""
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
        "cr": (vk_goals / clicks * 100) if clicks > 0 else 0,
        "cost_per_goal": (spent / vk_goals) if vk_goals > 0 else float('inf'),
    }


def prepare_banner_info(banners: List[Dict]) -> Tuple[List[int], Dict[int, Dict]]:
    """Prepare banner IDs list and info dictionary from raw banner data."""
    banner_ids = []
    banners_info = {}

    for b in banners:
        bid = b.get("id")
        if not bid:
            continue

        banner_ids.append(bid)

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


async def log_budget_change_to_db(
    user_id: int,
    rule: BudgetRule,
    banner: Dict,
    ad_group_id: int,
    ad_group_name: Optional[str],
    account_name: str,
    result: Dict,
    lookback_days: int,
    date_from: str,
    date_to: str,
    roi_data: Optional[Dict] = None
):
    """Log budget change to database"""
    def _log_sync():
        db = SessionLocal()
        try:
            # Build stats snapshot
            stats_snapshot = {
                "spent": banner.get("spent", 0),
                "clicks": banner.get("clicks", 0),
                "shows": banner.get("shows", 0),
                "vk_goals": banner.get("vk_goals", 0),
            }
            
            # Add ROI if available
            if roi_data:
                banner_id = banner.get("id")
                roi_info = roi_data.get(banner_id)
                if roi_info:
                    roi_percent = roi_info.roi_percent if hasattr(roi_info, 'roi_percent') else roi_info.get('roi_percent')
                    stats_snapshot["roi"] = roi_percent
            
            crud.create_budget_change_log(
                db=db,
                user_id=user_id,
                ad_group_id=ad_group_id,
                change_percent=rule.change_percent,
                change_direction=rule.change_direction,
                rule_id=rule.id,
                rule_name=rule.name,
                account_name=account_name,
                ad_group_name=ad_group_name or result.get("group_name"),
                banner_id=banner.get("id"),
                banner_name=banner.get("name"),
                old_budget=result.get("old_budget"),
                new_budget=result.get("new_budget"),
                stats_snapshot=stats_snapshot,
                success=result.get("success", False),
                error_message=result.get("error"),
                is_dry_run=result.get("dry_run", False),
                lookback_days=lookback_days,
                analysis_date_from=date_from,
                analysis_date_to=date_to
            )
        except Exception as e:
            logger.error(f"Error logging budget change to DB: {e}")
        finally:
            db.close()
    
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, _log_sync)


async def process_budget_rules_for_account(
    session: aiohttp.ClientSession,
    account_name: str,
    access_token: str,
    base_url: str,
    user_id: int,
    dry_run: bool = True,
    whitelist: Optional[Set[int]] = None,
    specific_rule_id: Optional[int] = None
) -> Dict:
    """
    Process budget rules for one account.
    
    Args:
        specific_rule_id: If provided, run only this specific rule (for manual runs)
    
    Returns:
        Dict with results of budget changes
    """
    logger.info("=" * 100)
    logger.info(f"BUDGET RULES: Processing account {account_name}")
    logger.info("=" * 100)

    # Set VK API notification context for error alerts
    def _get_notify_config() -> Optional[Dict]:
        db = SessionLocal()
        try:
            all_settings = crud.get_all_user_settings(db, user_id)
            telegram_settings = all_settings.get('telegram', {})
            return {"telegram": telegram_settings}
        finally:
            db.close()

    from utils.vk_api_async import set_vk_api_notify_context
    notify_config = _get_notify_config()
    set_vk_api_notify_context(notify_config, account_name)

    whitelist = whitelist or set()

    # Load budget rules for this account
    def _get_rules_sync() -> Tuple[List[BudgetRule], int]:
        db = SessionLocal()
        try:
            # Get account's VK ID for logging
            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.name == account_name
            ).first()
            
            if not account:
                logger.warning(f"[{account_name}] Account not found in DB for user_id={user_id}")
                return [], None
            
            logger.debug(f"[{account_name}] Found account: id={account.id}, user_id={account.user_id}")
            
            # If specific rule is provided, use it directly (for manual runs)
            if specific_rule_id:
                rule = crud.get_budget_rule_by_id(db, specific_rule_id)
                if rule:
                    logger.info(f"[{account_name}] Using specific rule: '{rule.name}' (ID: {rule.id}, enabled={rule.enabled})")
                    rules = [rule]
                else:
                    logger.warning(f"[{account_name}] Specific rule ID {specific_rule_id} not found")
                    rules = []
            else:
                # Get all enabled rules for this account
                rules = crud.get_budget_rules_for_account_by_name(db, account_name, user_id=user_id, enabled_only=True)
                logger.debug(f"[{account_name}] Found {len(rules)} enabled budget rules")
                
                # Also log all rules for this account (including disabled)
                all_rules = crud.get_budget_rules_for_account_by_name(db, account_name, user_id=user_id, enabled_only=False)
                if len(all_rules) != len(rules):
                    logger.debug(f"[{account_name}] Total rules (including disabled): {len(all_rules)}")
                    for r in all_rules:
                        logger.debug(f"   - Rule '{r.name}': enabled={r.enabled}")
            
            vk_account_id = account.account_id if account else None
            return rules, vk_account_id
        finally:
            db.close()
    
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        rules, vk_account_id = await loop.run_in_executor(executor, _get_rules_sync)
    
    if not rules:
        logger.info(f"[{account_name}] No enabled budget rules for this account")
        set_vk_api_notify_context(None)  # Clear context before early return
        return {
            "account_name": account_name,
            "changes": [],
            "total_changes": 0,
            "skipped": True
        }
    
    logger.info(f"[{account_name}] Loaded {len(rules)} budget rules")
    for rule in rules:
        conditions_str = ", ".join([
            f"{c.metric} {c.operator} {c.value}" for c in rule.conditions
        ])
        logger.info(f"   Rule \"{rule.name}\": {rule.change_direction} {rule.change_percent}% if {conditions_str}")
    
    # Determine analysis period (use max lookback_days from all rules)
    max_lookback = max(rule.lookback_days for rule in rules)
    today = date.today()
    date_from = _iso(today - timedelta(days=max_lookback))
    date_to = _iso(today)
    
    logger.info(f"[{account_name}] Analysis period: {date_from} — {date_to} ({max_lookback} days)")
    
    # Load active banners
    banners = await get_banners_active(
        session, access_token, base_url,
        sleep_between_calls=0.25
    )
    logger.info(f"[{account_name}] Active banners: {len(banners)}")
    
    if not banners:
        set_vk_api_notify_context(None)  # Clear context before early return
        return {
            "account_name": account_name,
            "changes": [],
            "total_changes": 0,
            "skipped": False,
            "reason": "no_banners"
        }
    
    # Prepare banner info
    banner_ids, banners_info = prepare_banner_info(banners)
    
    # Check if any rule uses ROI metric
    rules_use_roi = any(
        any(c.metric == "roi" for c in rule.conditions)
        for rule in rules
    )
    
    # Phase 1: Load statistics
    logger.info(f"[{account_name}] Loading statistics...")
    all_banners_with_stats = []
    vk_spent_cache: Dict[int, float] = {}
    
    async for batch_data in get_banners_stats_batched(
        session, access_token, base_url, date_from, date_to,
        banner_ids=banner_ids,
        banners_info=banners_info,
        metrics="base",
        batch_size=200,
        sleep_between_calls=0.6
    ):
        batch_banners = batch_data["banners"]
        stats_map = batch_data.get("stats_map", {})
        
        all_banners_with_stats.extend(batch_banners)
        for bid, stats in stats_map.items():
            vk_spent_cache[bid] = stats.get("spent", 0.0)
    
    # Phase 2: Load ROI data if needed
    roi_data = None
    if rules_use_roi:
        logger.info(f"[{account_name}] Loading ROI data...")
        roi_data = await _load_roi_for_account(
            account_name=account_name,
            banner_ids=banner_ids,
            date_from=date_from,
            date_to=date_to,
            rules=rules,
            user_id=user_id,
            vk_spent_cache=vk_spent_cache
        )
        if roi_data:
            logger.info(f"[{account_name}] Loaded ROI data for {len(roi_data)} banners")
    
    # Phase 3: Check banners against rules and collect ad_groups to change
    # Key: (ad_group_id, rule_id) -> {rule, banner, metrics}
    # This ensures we don't change the same group multiple times for the same rule
    ad_groups_to_change: Dict[Tuple[int, int], Dict] = {}
    
    for b in all_banners_with_stats:
        bid = b.get("id")
        ad_group_id = b.get("ad_group_id")
        
        if not ad_group_id or ad_group_id == "N/A":
            continue
        
        # Skip whitelisted banners
        if bid in whitelist:
            continue
        
        banner_data = {
            "id": bid,
            "name": b.get("name", "Unknown"),
            "spent": b.get("spent", 0.0),
            "clicks": b.get("clicks", 0.0),
            "shows": b.get("shows", 0.0),
            "vk_goals": b.get("vk_goals", 0.0),
            "ad_group_id": ad_group_id,
            "account": account_name
        }
        
        # Check against budget rules
        matched_rule = crud.check_banner_against_budget_rules(
            banner_data, rules, roi_data
        )
        
        if matched_rule:
            key = (ad_group_id, matched_rule.id)
            
            # Only process first match for each ad_group + rule combination
            if key not in ad_groups_to_change:
                metrics = calculate_banner_metrics(banner_data)
                metrics["id"] = bid
                
                reason = crud.format_budget_rule_match_reason(matched_rule, metrics, roi_data)
                logger.info(f"[{account_name}] MATCH: Banner [{bid}] {banner_data['name']}")
                logger.info(f"   {reason.replace(chr(10), chr(10) + '   ')}")
                
                ad_groups_to_change[key] = {
                    "rule": matched_rule,
                    "banner": banner_data,
                    "ad_group_id": ad_group_id,
                    "reason": reason
                }
    
    # Phase 4: Apply budget changes
    changes = []
    
    if ad_groups_to_change:
        logger.info(f"[{account_name}] Changing budgets for {len(ad_groups_to_change)} ad groups...")
        
        for (ad_group_id, rule_id), data in ad_groups_to_change.items():
            rule = data["rule"]
            banner = data["banner"]
            
            result = await change_ad_group_budget_percent(
                session, access_token, base_url,
                group_id=ad_group_id,
                change_percent=rule.change_percent,
                change_direction=rule.change_direction,
                dry_run=dry_run
            )
            
            # Log to database
            await log_budget_change_to_db(
                user_id=user_id,
                rule=rule,
                banner=banner,
                ad_group_id=ad_group_id,
                ad_group_name=result.get("group_name"),
                account_name=account_name,
                result=result,
                lookback_days=max_lookback,
                date_from=date_from,
                date_to=date_to,
                roi_data=roi_data
            )
            
            changes.append({
                "ad_group_id": ad_group_id,
                "ad_group_name": result.get("group_name"),
                "rule_name": rule.name,
                "change_percent": rule.change_percent,
                "change_direction": rule.change_direction,
                "old_budget": result.get("old_budget"),
                "new_budget": result.get("new_budget"),
                "success": result.get("success", False),
                "error": result.get("error"),
                "dry_run": result.get("dry_run", False),
                "triggered_by_banner": {
                    "id": banner.get("id"),
                    "name": banner.get("name")
                }
            })
            
            # Small delay between budget changes
            await asyncio.sleep(0.3)
    
    # Summary
    successful = sum(1 for c in changes if c["success"])
    failed = sum(1 for c in changes if not c["success"])
    
    logger.info("=" * 80)
    logger.info(f"[{account_name}] Budget changes summary:")
    logger.info(f"   Total ad groups changed: {len(changes)}")
    logger.info(f"   Successful: {successful}")
    logger.info(f"   Failed: {failed}")
    logger.info(f"   Dry run: {dry_run}")
    logger.info("=" * 80)
    
    # Clear VK API notification context
    set_vk_api_notify_context(None)

    return {
        "account_name": account_name,
        "changes": changes,
        "total_changes": len(changes),
        "successful": successful,
        "failed": failed,
        "dry_run": dry_run,
        "date_from": date_from,
        "date_to": date_to,
        "lookback_days": max_lookback
    }
