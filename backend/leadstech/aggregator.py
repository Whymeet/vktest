"""
LeadsTech Data Aggregator

Aggregates LeadsTech statistics by banner and calculates ROI.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from utils.logging_setup import get_logger

logger = get_logger(service="leadstech", function="aggregator")


@dataclass
class BannerAggregation:
    """Aggregated LeadsTech data for a single banner."""
    banner_id: int
    lt_revenue: float = 0.0
    lt_clicks: int = 0
    lt_conversions: int = 0
    lt_inprogress: int = 0
    lt_approved: int = 0
    lt_rejected: int = 0


@dataclass
class AnalysisResult:
    """Result of ROI analysis for a single banner."""
    cabinet_name: str
    leadstech_label: str
    banner_id: int
    vk_spent: float
    lt_revenue: float
    profit: float
    roi_percent: Optional[float]
    lt_clicks: int
    lt_conversions: int
    lt_approved: int
    lt_inprogress: int
    lt_rejected: int
    date_from: str
    date_to: str
    user_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "cabinet_name": self.cabinet_name,
            "leadstech_label": self.leadstech_label,
            "banner_id": self.banner_id,
            "vk_spent": round(self.vk_spent, 2),
            "lt_revenue": round(self.lt_revenue, 2),
            "profit": round(self.profit, 2),
            "roi_percent": round(self.roi_percent, 2) if self.roi_percent is not None else None,
            "lt_clicks": self.lt_clicks,
            "lt_conversions": self.lt_conversions,
            "lt_approved": self.lt_approved,
            "lt_inprogress": self.lt_inprogress,
            "lt_rejected": self.lt_rejected,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "user_id": self.user_id,
        }


def aggregate_leadstech_by_banner(
    rows: List[Dict[str, Any]],
    banner_sub_fields: Optional[List[str]] = None,
) -> Dict[int, BannerAggregation]:
    """
    Aggregate LeadsTech data by banner ID from ALL enabled sub fields.

    For each row, extracts banner IDs from ALL specified sub fields and aggregates
    data for each ID separately. This allows tracking the same conversion data
    under multiple banner IDs if they exist in different sub fields.

    Args:
        rows: Raw rows from LeadsTech API
        banner_sub_fields: List of sub fields to extract banner IDs from

    Returns:
        Dictionary mapping banner ID to aggregated data
    """
    if banner_sub_fields is None:
        banner_sub_fields = ["sub4", "sub5"]

    logger.info(f"Aggregating LeadsTech by fields: {banner_sub_fields}")

    result: Dict[int, BannerAggregation] = {}

    for row in rows:
        # Extract ALL banner IDs from ALL enabled sub fields
        banner_ids_from_row: List[int] = []
        for sub_field in banner_sub_fields:
            sub_value = row.get(sub_field)
            if sub_value:
                try:
                    banner_id = int(str(sub_value))
                    if banner_id not in banner_ids_from_row:
                        banner_ids_from_row.append(banner_id)
                except (TypeError, ValueError):
                    continue

        if not banner_ids_from_row:
            continue

        # Get stats from this row
        revenue = float(row.get("sumwebmaster", 0) or 0)
        clicks = int(row.get("clicks", 0) or 0)
        conversions = int(row.get("conversions", 0) or 0)
        inprogress = int(row.get("inprogress", 0) or 0)
        approved = int(row.get("approved", 0) or 0)
        rejected = int(row.get("rejected", 0) or 0)

        # Add stats to EACH banner ID found in this row
        for banner_id in banner_ids_from_row:
            if banner_id not in result:
                result[banner_id] = BannerAggregation(banner_id=banner_id)

            agg = result[banner_id]
            agg.lt_revenue += revenue
            agg.lt_clicks += clicks
            agg.lt_conversions += conversions
            agg.lt_inprogress += inprogress
            agg.lt_approved += approved
            agg.lt_rejected += rejected

    logger.info(f"Aggregated {len(result)} unique banner IDs from LeadsTech")
    return result


def calculate_roi(lt_revenue: float, vk_spent: float) -> Optional[float]:
    """
    Calculate ROI percentage.

    Args:
        lt_revenue: Revenue from LeadsTech
        vk_spent: Spending from VK Ads

    Returns:
        ROI percentage or None if spent is 0
    """
    if vk_spent <= 0:
        return None
    profit = lt_revenue - vk_spent
    return (profit / vk_spent) * 100.0


def merge_data_and_calculate_roi(
    lt_by_banner: Dict[int, BannerAggregation],
    vk_spent_by_banner: Dict[int, float],
    vk_valid_ids: set,
    cabinet_name: str,
    lt_label: str,
    date_from: date,
    date_to: date,
    user_id: Optional[int] = None,
) -> List[AnalysisResult]:
    """
    Merge LeadsTech and VK Ads data, calculate ROI for each banner.

    Includes banners that VK API returned data for (even if spent=0).
    Skips banners that VK API returned an error for (not in vk_valid_ids).

    Args:
        lt_by_banner: Aggregated LeadsTech data by banner ID
        vk_spent_by_banner: VK Ads spending by banner ID (including zero values)
        vk_valid_ids: Set of banner IDs that VK API successfully returned data for
        cabinet_name: Name of the VK Ads cabinet
        lt_label: LeadsTech label for this cabinet
        date_from: Start date of analysis period
        date_to: End date of analysis period
        user_id: User ID for database storage

    Returns:
        List of analysis results
    """
    results: List[AnalysisResult] = []
    valid_banners = 0
    skipped_banners = 0

    for banner_id, lt_data in lt_by_banner.items():
        # Skip banners that VK API didn't return data for (not valid VK banner IDs)
        if banner_id not in vk_valid_ids:
            skipped_banners += 1
            continue

        valid_banners += 1
        # Get spent (0.0 if not in dict means VK returned empty/zero data)
        vk_spent = vk_spent_by_banner.get(banner_id, 0.0)
        lt_revenue = lt_data.lt_revenue

        profit = lt_revenue - vk_spent
        roi_percent = calculate_roi(lt_revenue, vk_spent)

        result = AnalysisResult(
            cabinet_name=cabinet_name,
            leadstech_label=lt_label,
            banner_id=banner_id,
            vk_spent=vk_spent,
            lt_revenue=lt_revenue,
            profit=profit,
            roi_percent=roi_percent,
            lt_clicks=lt_data.lt_clicks,
            lt_conversions=lt_data.lt_conversions,
            lt_approved=lt_data.lt_approved,
            lt_inprogress=lt_data.lt_inprogress,
            lt_rejected=lt_data.lt_rejected,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            user_id=user_id,
        )
        results.append(result)

    logger.info(
        f"Cabinet {cabinet_name}: {valid_banners} valid banners, "
        f"{skipped_banners} skipped (not found in VK)"
    )

    return results
