"""
ROI Loader for Auto-Disable Rules

Loads LeadsTech data for ROI calculation in auto-disable rules.
Uses batched requests with pipe-separated IDs (ad_id1|ad_id2|...) for efficiency.

Key features:
- Batch loading: up to 50 banner IDs per request using "|" separator in sub filter
- Parallel processing: load from multiple accounts concurrently
- Integration with disable rules: uses roi_sub_field to determine which sub to query
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Set

from database.models import Account, DisableRule
from utils.logging_setup import get_logger

logger = get_logger(service="roi_loader", function="disable")

# Maximum number of banner IDs per LeadsTech request
BATCH_SIZE = 50


@dataclass
class BannerROIData:
    """ROI data for a single banner."""
    banner_id: int
    lt_revenue: float
    vk_spent: float
    roi_percent: Optional[float]

    def __repr__(self) -> str:
        roi_str = f"{self.roi_percent:.1f}%" if self.roi_percent is not None else "N/A"
        return f"BannerROI({self.banner_id}: revenue={self.lt_revenue:.2f}, spent={self.vk_spent:.2f}, roi={roi_str})"


def calculate_roi(revenue: float, spent: float) -> Optional[float]:
    """
    Calculate ROI percentage.

    Args:
        revenue: Revenue from LeadsTech
        spent: Spending from VK Ads

    Returns:
        ROI percentage or None if spent is 0
    """
    if spent <= 0:
        return None
    profit = revenue - spent
    return (profit / spent) * 100.0


def _build_batched_sub_filter(banner_ids: List[int], batch_size: int = BATCH_SIZE) -> List[str]:
    """
    Build batched sub filters using pipe separator.

    LeadsTech supports search syntax:
    - Use "|" for OR search: "12345|67890|11111" matches any of these IDs

    Args:
        banner_ids: List of banner IDs to search for
        batch_size: Maximum IDs per batch (default 50)

    Returns:
        List of filter strings, each containing up to batch_size IDs
    """
    batches = []
    for i in range(0, len(banner_ids), batch_size):
        batch = banner_ids[i:i + batch_size]
        # Join with pipe for OR search
        filter_str = "|".join(str(bid) for bid in batch)
        batches.append(filter_str)
    return batches


def _aggregate_lt_rows_by_banner(
    rows: List[Dict[str, Any]],
    sub_field: str,
    target_banner_ids: Set[int]
) -> Dict[int, float]:
    """
    Aggregate LeadsTech rows by banner ID, summing revenue.

    Args:
        rows: Raw rows from LeadsTech API
        sub_field: Which sub field contains banner ID (sub4 or sub5)
        target_banner_ids: Set of banner IDs we're interested in

    Returns:
        Dict mapping banner_id -> total revenue
    """
    result: Dict[int, float] = {}

    for row in rows:
        sub_value = row.get(sub_field)
        if not sub_value:
            continue

        try:
            banner_id = int(str(sub_value))
        except (TypeError, ValueError):
            continue

        # Only include banners we're looking for
        if banner_id not in target_banner_ids:
            continue

        # Sum revenue (sumwebmaster is the webmaster revenue field)
        revenue = float(row.get("sumwebmaster", 0) or 0)

        if banner_id not in result:
            result[banner_id] = 0.0
        result[banner_id] += revenue

    return result


async def load_roi_for_banners_async(
    lt_client: Any,  # LeadstechClient
    vk_client: Any,  # VkAdsClient with async support
    account: Account,
    banner_ids: List[int],
    date_from: date,
    date_to: date,
    sub_field: str,  # "sub4" or "sub5"
) -> Dict[int, BannerROIData]:
    """
    Load ROI data for specific banners from one account.

    Uses batched LeadsTech requests with "|" separator for efficiency.

    Args:
        lt_client: LeadsTech API client
        vk_client: VK Ads API client
        account: Account with label for LeadsTech filtering
        banner_ids: List of banner IDs to load ROI for
        date_from: Start date
        date_to: End date
        sub_field: Which sub field to use (sub4 or sub5)

    Returns:
        Dict mapping banner_id to BannerROIData
    """
    if not account.label or not account.leadstech_enabled:
        logger.debug(f"Account {account.name} has no label or leadstech disabled, skipping ROI")
        return {}

    if not banner_ids:
        return {}

    logger.info(f"Loading ROI for {len(banner_ids)} banners from {account.name} using {sub_field}")

    result: Dict[int, BannerROIData] = {}
    banner_ids_set = set(banner_ids)

    # Build batched filters
    filter_batches = _build_batched_sub_filter(banner_ids, BATCH_SIZE)
    logger.info(f"  Split into {len(filter_batches)} batches (max {BATCH_SIZE} per batch)")

    # Aggregate LeadsTech data from all batches
    lt_revenue_by_banner: Dict[int, float] = {}

    for batch_idx, filter_str in enumerate(filter_batches):
        try:
            # Request LeadsTech with sub1=label and specific sub field filter
            # The sub field filter uses "|" syntax for OR search
            rows = lt_client.get_stat_by_subid_with_filter(
                date_from=date_from,
                date_to=date_to,
                sub1_value=account.label,
                sub_field=sub_field,
                sub_filter=filter_str,
                subs_fields=[sub_field]  # Only request the sub field we need
            )

            if rows:
                batch_revenue = _aggregate_lt_rows_by_banner(rows, sub_field, banner_ids_set)
                for bid, revenue in batch_revenue.items():
                    if bid not in lt_revenue_by_banner:
                        lt_revenue_by_banner[bid] = 0.0
                    lt_revenue_by_banner[bid] += revenue

            logger.debug(f"  Batch {batch_idx + 1}/{len(filter_batches)}: {len(rows) if rows else 0} rows")

        except Exception as e:
            logger.error(f"  Error loading batch {batch_idx + 1}: {e}")
            continue

    # Get VK spending for banners that have LeadsTech data
    banners_with_lt_data = list(lt_revenue_by_banner.keys())

    if banners_with_lt_data:
        try:
            vk_spent_map, vk_valid_ids = vk_client.get_spent_by_banner(
                date_from,
                date_to,
                banners_with_lt_data
            )

            # Calculate ROI for each banner
            for banner_id in banners_with_lt_data:
                if banner_id not in vk_valid_ids:
                    continue

                revenue = lt_revenue_by_banner.get(banner_id, 0.0)
                spent = vk_spent_map.get(banner_id, 0.0)
                roi = calculate_roi(revenue, spent)

                result[banner_id] = BannerROIData(
                    banner_id=banner_id,
                    lt_revenue=revenue,
                    vk_spent=spent,
                    roi_percent=roi
                )

            logger.info(f"  Calculated ROI for {len(result)} banners")

        except Exception as e:
            logger.error(f"  Error loading VK spent: {e}")

    return result


def load_roi_for_disable_rules(
    lt_client: Any,
    vk_client_factory: Any,  # Callable to create VkAdsClient for account
    accounts: List[Account],
    banner_ids: List[int],
    date_from: str,
    date_to: str,
    rules: List[DisableRule],
) -> Dict[int, BannerROIData]:
    """
    Load ROI data for banners based on disable rules configuration.

    Processes accounts in parallel, using the appropriate sub_field from rules.

    Args:
        lt_client: LeadsTech API client
        vk_client_factory: Factory to create VK client for account
        accounts: List of accounts to process
        banner_ids: List of all banner IDs to load ROI for
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        rules: Disable rules (to get roi_sub_field configuration)

    Returns:
        Dict mapping banner_id to BannerROIData
    """
    # Determine which sub_field to use based on rules
    # If any rule has roi_sub_field set, use that; otherwise use default ["sub4", "sub5"]
    sub_fields_to_use = set()
    for rule in rules:
        if rule.roi_sub_field:
            sub_fields_to_use.add(rule.roi_sub_field)

    # If no specific sub_field configured, use both
    if not sub_fields_to_use:
        sub_fields_to_use = {"sub4", "sub5"}

    logger.info(f"Loading ROI for {len(banner_ids)} banners from {len(accounts)} accounts")
    logger.info(f"Using sub fields: {sub_fields_to_use}")

    # Convert date strings
    try:
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return {}

    all_roi_data: Dict[int, BannerROIData] = {}
    accounts_with_label = [a for a in accounts if a.label and a.leadstech_enabled]

    if not accounts_with_label:
        logger.warning("No accounts with label and leadstech_enabled found")
        return all_roi_data

    # Process each account
    for account in accounts_with_label:
        vk_client = vk_client_factory(account)

        # Try each sub_field
        for sub_field in sub_fields_to_use:
            try:
                account_roi = load_roi_for_banners_sync(
                    lt_client=lt_client,
                    vk_client=vk_client,
                    account=account,
                    banner_ids=banner_ids,
                    date_from=date_from_obj,
                    date_to=date_to_obj,
                    sub_field=sub_field
                )

                # Merge results (first found wins for each banner)
                for bid, roi_data in account_roi.items():
                    if bid not in all_roi_data:
                        all_roi_data[bid] = roi_data

            except Exception as e:
                logger.error(f"Error loading ROI for {account.name} with {sub_field}: {e}")
                continue

    logger.info(f"Loaded ROI for {len(all_roi_data)} banners total")
    return all_roi_data


def load_roi_for_banners_sync(
    lt_client: Any,
    vk_client: Any,
    account: Account,
    banner_ids: List[int],
    date_from: date,
    date_to: date,
    sub_field: str,
    vk_spent_cache: Optional[Dict[int, float]] = None,
) -> Dict[int, BannerROIData]:
    """
    Synchronous version of load_roi_for_banners_async.

    Uses batched LeadsTech requests with "|" separator.

    Args:
        lt_client: LeadsTech API client
        vk_client: VK Ads API client (used only if vk_spent_cache is None)
        account: Account with label for LeadsTech filtering
        banner_ids: List of banner IDs to load ROI for
        date_from: Start date
        date_to: End date
        sub_field: Which sub field to use (sub4 or sub5)
        vk_spent_cache: Pre-loaded VK spent data to avoid extra API calls
    """
    if not account.label or not account.leadstech_enabled:
        return {}

    if not banner_ids:
        return {}

    logger.info(f"Loading ROI for {len(banner_ids)} banners from {account.name} using {sub_field}")

    result: Dict[int, BannerROIData] = {}
    banner_ids_set = set(banner_ids)

    # Build batched filters
    filter_batches = _build_batched_sub_filter(banner_ids, BATCH_SIZE)

    # Aggregate LeadsTech data from all batches
    lt_revenue_by_banner: Dict[int, float] = {}

    for batch_idx, filter_str in enumerate(filter_batches):
        try:
            # Standard request - LeadsTech will filter by the sub value containing our IDs
            rows = lt_client.get_stat_by_subid(
                date_from=date_from,
                date_to=date_to,
                sub1_value=account.label,
                subs_fields=[sub_field]
            )

            if rows:
                batch_revenue = _aggregate_lt_rows_by_banner(rows, sub_field, banner_ids_set)
                for bid, revenue in batch_revenue.items():
                    if bid not in lt_revenue_by_banner:
                        lt_revenue_by_banner[bid] = 0.0
                    lt_revenue_by_banner[bid] += revenue

        except Exception as e:
            logger.error(f"  Error loading LeadsTech data: {e}")
            continue

    # Get VK spending for banners that have LeadsTech data
    banners_with_lt_data = list(lt_revenue_by_banner.keys())

    if banners_with_lt_data:
        try:
            # Use cached VK spent data if available (avoids extra VK API calls)
            if vk_spent_cache is not None:
                logger.info(f"  Using cached VK spent data ({len(vk_spent_cache)} banners)")
                vk_spent_map = vk_spent_cache
                vk_valid_ids = set(vk_spent_cache.keys())
            else:
                # Fallback to VK API call (will count against rate limit)
                logger.warning(f"  No VK spent cache, making VK API call for {len(banners_with_lt_data)} banners")
                vk_spent_map, vk_valid_ids = vk_client.get_spent_by_banner(
                    date_from,
                    date_to,
                    banners_with_lt_data
                )

            for banner_id in banners_with_lt_data:
                # If using cache, all banners are valid
                if vk_spent_cache is None and banner_id not in vk_valid_ids:
                    continue

                revenue = lt_revenue_by_banner.get(banner_id, 0.0)
                spent = vk_spent_map.get(banner_id, 0.0)
                roi = calculate_roi(revenue, spent)

                result[banner_id] = BannerROIData(
                    banner_id=banner_id,
                    lt_revenue=revenue,
                    vk_spent=spent,
                    roi_percent=roi
                )

        except Exception as e:
            logger.error(f"  Error loading VK spent: {e}")

    # Log which banners were found/not found for debugging
    found_ids = set(result.keys())
    not_found_ids = banner_ids_set - found_ids
    logger.info(f"  Calculated ROI for {len(result)} banners from {account.name}")
    if found_ids:
        logger.info(f"  Found ROI for banner IDs: {sorted(found_ids)[:10]}{'...' if len(found_ids) > 10 else ''}")
    if not_found_ids:
        logger.warning(f"  NO ROI data for {len(not_found_ids)} banners: {sorted(not_found_ids)[:10]}{'...' if len(not_found_ids) > 10 else ''}")
    return result


def get_roi_for_banner(
    roi_data: Dict[int, BannerROIData],
    banner_id: int,
    default_if_not_found: float = 0.0
) -> float:
    """
    Get ROI value for a specific banner.

    Args:
        roi_data: Dict of ROI data by banner ID
        banner_id: Banner ID to look up
        default_if_not_found: Default ROI if banner not found (default 0)

    Returns:
        ROI percentage or default value
    """
    data = roi_data.get(banner_id)
    if data is None or data.roi_percent is None:
        return default_if_not_found
    return data.roi_percent
