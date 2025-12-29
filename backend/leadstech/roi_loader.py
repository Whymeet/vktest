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

logger = get_logger(service="roi_loader")


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


def load_roi_data_for_accounts(
    lt_client: Any,  # LeadstechClient
    vk_client_factory: Any,  # Callable to create VkAdsClient
    accounts: List[Account],
    date_from: str,
    date_to: str,
    banner_sub_fields: List[str],
    progress_callback: Optional[callable] = None
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

    logger.info(f"Loading ROI data for {len(accounts_with_label)} accounts with labels")
    logger.info(f"Date range: {date_from} to {date_to}")
    logger.info(f"Banner sub fields: {banner_sub_fields}")

    # Convert date strings to date objects
    try:
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return all_roi_data

    for idx, account in enumerate(accounts_with_label):
        if progress_callback:
            progress_callback(f"Loading ROI data for {account.name} ({idx + 1}/{len(accounts_with_label)})")

        logger.info(f"Processing account: {account.name} (label={account.label})")

        try:
            # 1. Load LeadsTech data by label
            lt_rows = lt_client.get_stat_by_subid(
                date_from=date_from_obj,
                date_to=date_to_obj,
                sub1_value=account.label,
                subs_fields=banner_sub_fields
            )

            if not lt_rows:
                logger.info(f"  No LeadsTech data for label '{account.label}'")
                continue

            # 2. Aggregate by banner_id
            lt_by_banner = aggregate_leadstech_by_banner(lt_rows, banner_sub_fields)

            if not lt_by_banner:
                logger.info(f"  No banner IDs extracted from LeadsTech data")
                continue

            logger.info(f"  Found {len(lt_by_banner)} banners in LeadsTech")

            # 3. Load VK spent only for these banners
            banner_ids = list(lt_by_banner.keys())
            vk_client = vk_client_factory(account)

            try:
                vk_spent_map, vk_valid_ids = vk_client.get_spent_by_banner(
                    date_from_obj,
                    date_to_obj,
                    banner_ids
                )
            except Exception as e:
                logger.error(f"  Failed to load VK spent: {e}")
                vk_spent_map = {}
                vk_valid_ids = set()

            logger.info(f"  VK returned data for {len(vk_valid_ids)}/{len(banner_ids)} banners")

            # 4. Calculate ROI for each banner
            banners_with_roi = 0
            for banner_id, lt_data in lt_by_banner.items():
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

            logger.info(f"  Calculated ROI for {banners_with_roi}/{len(lt_by_banner)} banners")

        except Exception as e:
            logger.error(f"  Error processing account {account.name}: {e}")
            continue

    logger.info(f"Total: loaded ROI data for {len(all_roi_data)} banners")
    return all_roi_data
