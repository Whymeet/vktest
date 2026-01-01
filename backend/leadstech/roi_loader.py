"""
ROI Loader for Scaling Engine

Loads LeadsTech data and VK spent for ROI calculation during scaling.
Only called when scaling conditions include ROI metric.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from database.models import Account
from utils.logging_setup import get_logger

# Logger will inherit user_id from context set by scaling_engine
logger = get_logger(service="roi_loader", function="scaling")


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


def _group_accounts_by_label(accounts: List[Account]) -> Dict[str, List[Account]]:
    """
    Group accounts by their label value.

    Args:
        accounts: List of accounts to group

    Returns:
        Dict mapping label to list of accounts with that label
    """
    from collections import defaultdict
    accounts_by_label: Dict[str, List[Account]] = defaultdict(list)

    for account in accounts:
        if account.label:
            accounts_by_label[account.label].append(account)

    return dict(accounts_by_label)


def load_roi_data_for_accounts(
    lt_client: Any,  # LeadstechClient
    vk_client_factory: Any,  # Callable to create VkAdsClient
    accounts: List[Account],
    date_from: str,
    date_to: str,
    banner_sub_fields: List[str],
    progress_callback: Optional[callable] = None,
    cancel_check_fn: Optional[callable] = None
) -> Dict[int, BannerROIData]:
    """
    Load ROI data for all accounts with labels.

    Flow:
    1. For each account with label:
       a. Load LeadsTech data by label -> {banner_id: {revenue, ...}}
       b. Load VK spent ONLY for these banner_ids -> {banner_id: spent}
       c. Calculate ROI = (revenue - spent) / spent * 100
    2. Return combined {banner_id: BannerROIData}

    Args:
        lt_client: LeadsTech API client
        vk_client_factory: Factory function to create VK client for account
        accounts: List of accounts to process
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        banner_sub_fields: List of sub fields to extract banner IDs from
        progress_callback: Optional callback for progress updates

    Returns:
        Dict mapping banner_id to BannerROIData
    """
    from leadstech.aggregator import aggregate_leadstech_by_banner

    all_roi_data: Dict[int, BannerROIData] = {}
    accounts_with_label = [a for a in accounts if a.label]

    if not accounts_with_label:
        logger.warning("No accounts with label found, ROI data will be empty")
        return all_roi_data

    # Group accounts by label to avoid duplicate LeadsTech requests
    accounts_by_label = _group_accounts_by_label(accounts_with_label)

    logger.info(f"Loading ROI data for {len(accounts_with_label)} accounts with {len(accounts_by_label)} unique labels")
    logger.info(f"Date range: {date_from} to {date_to}")
    logger.info(f"Banner sub fields: {banner_sub_fields}")

    # Convert date strings to date objects
    try:
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return all_roi_data

    # Process each unique label
    label_idx = 0
    total_accounts_processed = 0

    for label, label_accounts in accounts_by_label.items():
        # Check for cancellation before processing each label
        if cancel_check_fn and cancel_check_fn():
            logger.warning("ROI loading cancelled by user")
            break

        label_idx += 1

        if progress_callback:
            progress_callback(f"Loading ROI for label '{label}' ({label_idx}/{len(accounts_by_label)}, {len(label_accounts)} accounts)")

        logger.info(f"")
        logger.info(f"Processing label '{label}' ({len(label_accounts)} accounts)")

        try:
            # 1. Load LeadsTech data ONCE for this label
            lt_rows = lt_client.get_stat_by_subid(
                date_from=date_from_obj,
                date_to=date_to_obj,
                sub1_value=label,
                subs_fields=banner_sub_fields
            )

            if not lt_rows:
                logger.info(f"  No LeadsTech data for label '{label}'")
                continue

            # 2. Aggregate by banner_id
            lt_by_banner = aggregate_leadstech_by_banner(lt_rows, banner_sub_fields)

            if not lt_by_banner:
                logger.info(f"  No banner IDs extracted from LeadsTech data")
                continue

            logger.info(f"  Found {len(lt_by_banner)} unique banners in LeadsTech for label '{label}'")

            # 3. For each account with this label, load VK spent and calculate ROI
            # Use a set of remaining banner_ids - remove found ones to avoid duplicate checks
            remaining_banner_ids = set(lt_by_banner.keys())

            for account in label_accounts:
                # Check for cancellation before processing each account
                if cancel_check_fn and cancel_check_fn():
                    logger.warning("ROI loading cancelled by user")
                    break

                # Skip if no more banners to check
                if not remaining_banner_ids:
                    logger.info(f"  Skipping {account.name} - all banners already found")
                    continue

                total_accounts_processed += 1
                logger.info(f"  Processing account: {account.name} ({len(remaining_banner_ids)} banners to check)")

                vk_client = vk_client_factory(account)

                try:
                    vk_spent_map, vk_valid_ids = vk_client.get_spent_by_banner(
                        date_from_obj,
                        date_to_obj,
                        list(remaining_banner_ids)
                    )
                except Exception as e:
                    logger.error(f"    Failed to load VK spent for {account.name}: {e}")
                    continue

                logger.info(f"    VK returned data for {len(vk_valid_ids)}/{len(remaining_banner_ids)} banners")

                # 4. Calculate ROI for each banner found in this account
                banners_with_roi = 0
                for banner_id in vk_valid_ids:
                    lt_data = lt_by_banner.get(banner_id)
                    if not lt_data:
                        continue

                    spent = vk_spent_map.get(banner_id, 0.0)
                    revenue = lt_data.lt_revenue
                    roi = calculate_roi(revenue, spent)

                    all_roi_data[banner_id] = BannerROIData(
                        banner_id=banner_id,
                        lt_revenue=revenue,
                        vk_spent=spent,
                        roi_percent=roi
                    )

                    if roi is not None:
                        banners_with_roi += 1

                # Remove found banners from remaining set (they belong to this account only)
                remaining_banner_ids -= vk_valid_ids

                logger.info(f"    Calculated ROI for {banners_with_roi} banners in {account.name}, {len(remaining_banner_ids)} remaining")

        except Exception as e:
            logger.error(f"  Error processing label '{label}': {e}")
            continue

    logger.info(f"")
    logger.info(f"Total: loaded ROI data for {len(all_roi_data)} banners across {total_accounts_processed} accounts")
    return all_roi_data
