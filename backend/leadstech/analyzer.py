"""
LeadsTech Analyzer - Main Entry Point

Orchestrates analysis across all cabinets:
1. Loads configuration from database
2. Groups cabinets by label to avoid duplicate LeadsTech requests
3. Fetches data from LeadsTech API (once per unique label)
4. Fetches spending from VK Ads API with incremental processing
5. Calculates ROI and saves results

Optimizations (same as scaling ROI loader):
- Accounts are grouped by label - one LeadsTech request per unique label
- Incremental processing: found banners removed from remaining set
- Skip accounts when all banners already found
"""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from database import crud
from utils.logging_setup import get_logger, setup_logging as init_logging

from leadstech.leadstech_client import LeadstechClient
from leadstech.vk_client import VkAdsClient, VkAdsConfig
from leadstech.aggregator import (
    AnalysisResult,
    BannerAggregation,
    aggregate_leadstech_by_banner,
    calculate_roi,
)
from leadstech.config_loader import (
    CabinetConfig,
    LeadstechAnalysisConfig,
    get_user_id_from_env,
    load_analysis_config,
)

logger = get_logger(service="leadstech")


def setup_logging():
    """Setup logging configuration (backwards compatibility)."""
    init_logging()
    logger.info("LeadsTech Analyzer initialized")


def _group_cabinets_by_label(cabinets: List[CabinetConfig]) -> Dict[str, List[CabinetConfig]]:
    """
    Group cabinets by their label value to avoid duplicate LeadsTech requests.

    Args:
        cabinets: List of cabinet configurations

    Returns:
        Dict mapping label to list of cabinets with that label
    """
    cabinets_by_label: Dict[str, List[CabinetConfig]] = defaultdict(list)
    for cabinet in cabinets:
        if cabinet.leadstech_label:
            cabinets_by_label[cabinet.leadstech_label].append(cabinet)
    return dict(cabinets_by_label)


def _create_result(
    lt_data: BannerAggregation,
    vk_spent: float,
    cabinet_name: str,
    lt_label: str,
    date_from: str,
    date_to: str,
    user_id: int,
) -> AnalysisResult:
    """Create an AnalysisResult from LeadsTech and VK data."""
    lt_revenue = lt_data.lt_revenue
    profit = lt_revenue - vk_spent
    roi_percent = calculate_roi(lt_revenue, vk_spent)

    return AnalysisResult(
        cabinet_name=cabinet_name,
        leadstech_label=lt_label,
        banner_id=lt_data.banner_id,
        vk_spent=vk_spent,
        lt_revenue=lt_revenue,
        profit=profit,
        roi_percent=roi_percent,
        lt_clicks=lt_data.lt_clicks,
        lt_conversions=lt_data.lt_conversions,
        lt_approved=lt_data.lt_approved,
        lt_inprogress=lt_data.lt_inprogress,
        lt_rejected=lt_data.lt_rejected,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
    )


def analyze_all_cabinets(
    lt_client: LeadstechClient,
    config: LeadstechAnalysisConfig,
) -> Tuple[List[AnalysisResult], Dict[str, float]]:
    """
    Analyze all cabinets with optimized grouping by label.

    Optimizations:
    1. Group cabinets by label - one LeadsTech request per unique label
    2. Incremental processing - found banners removed from remaining set
    3. Skip cabinets when all banners already found

    Args:
        lt_client: LeadsTech API client
        config: Analysis configuration

    Returns:
        Tuple of:
        - List of analysis results for all cabinets
        - Dict mapping cabinet_name to total VK spent for that cabinet
    """
    all_results: List[AnalysisResult] = []
    cabinet_totals: Dict[str, float] = {}  # Total VK spent per cabinet

    # Group cabinets by label to avoid duplicate LeadsTech requests
    cabinets_by_label = _group_cabinets_by_label(config.cabinets)

    # First, collect total VK spent for each cabinet (one request per cabinet)
    logger.info("")
    logger.info("=== Collecting total VK spent for each cabinet ===")
    for cabinet in config.cabinets:
        vk_cfg = VkAdsConfig(
            base_url="https://ads.vk.com/api/v2",
            api_token=cabinet.api_token,
        )
        vk_client = VkAdsClient(vk_cfg)
        try:
            cabinet_total = vk_client.get_total_spent(config.date_from, config.date_to)
            cabinet_totals[cabinet.account_name] = cabinet_total
            logger.info(f"  {cabinet.account_name}: total VK spent = {cabinet_total:.2f}")
        except Exception as e:
            logger.error(f"  Failed to get total spent for {cabinet.account_name}: {e}")
            cabinet_totals[cabinet.account_name] = 0.0

    total_all_cabinets = sum(cabinet_totals.values())
    logger.info(f"Total VK spent across all cabinets: {total_all_cabinets:.2f}")

    logger.info(f"Processing {len(config.cabinets)} cabinets with {len(cabinets_by_label)} unique labels")
    logger.info(f"Date range: {config.date_from} to {config.date_to}")
    logger.info(f"Banner sub fields: {config.banner_sub_fields}")

    date_from_str = config.date_from.isoformat()
    date_to_str = config.date_to.isoformat()

    # Process each unique label
    for label_idx, (label, label_cabinets) in enumerate(cabinets_by_label.items(), 1):
        logger.info("")
        logger.info(f"=== Processing label '{label}' ({label_idx}/{len(cabinets_by_label)}, {len(label_cabinets)} cabinets) ===")

        # 1. Fetch LeadsTech data ONCE for this label
        try:
            lt_rows = lt_client.get_stat_by_subid(
                date_from=config.date_from,
                date_to=config.date_to,
                sub1_value=label,
                subs_fields=config.banner_sub_fields,
            )
        except Exception as e:
            logger.error(f"Failed to fetch LeadsTech data for label '{label}': {repr(str(e))}")
            continue

        # 2. Aggregate by banner_id
        lt_by_banner = aggregate_leadstech_by_banner(lt_rows, config.banner_sub_fields)

        if not lt_by_banner:
            logger.warning(f"No LeadsTech data for label '{label}', skipping")
            continue

        logger.info(f"Found {len(lt_by_banner)} unique banners in LeadsTech for label '{label}'")

        # 3. For each cabinet with this label, load VK spent with incremental processing
        # Use a set of remaining banner_ids - remove found ones to avoid duplicate processing
        remaining_banner_ids = set(lt_by_banner.keys())

        for cabinet in label_cabinets:
            # Skip if no more banners to check
            if not remaining_banner_ids:
                logger.info(f"  Skipping {cabinet.account_name} - all banners already found")
                continue

            logger.info(f"  Processing cabinet: {cabinet.account_name} ({len(remaining_banner_ids)} banners to check)")

            # Create VK client for this cabinet
            vk_cfg = VkAdsConfig(
                base_url="https://ads.vk.com/api/v2",
                api_token=cabinet.api_token,
            )
            vk_client = VkAdsClient(vk_cfg)

            try:
                vk_spent_by_banner, vk_valid_ids = vk_client.get_spent_by_banner(
                    config.date_from,
                    config.date_to,
                    list(remaining_banner_ids),
                )
            except Exception as e:
                logger.error(f"    Failed to fetch VK Ads data for {cabinet.account_name}: {e}")
                continue

            logger.info(f"    VK returned data for {len(vk_valid_ids)}/{len(remaining_banner_ids)} banners")

            # 4. Create results for each banner found in this cabinet
            banners_with_results = 0
            for banner_id in vk_valid_ids:
                lt_data = lt_by_banner.get(banner_id)
                if not lt_data:
                    continue

                vk_spent = vk_spent_by_banner.get(banner_id, 0.0)

                result = _create_result(
                    lt_data=lt_data,
                    vk_spent=vk_spent,
                    cabinet_name=cabinet.account_name,
                    lt_label=label,
                    date_from=date_from_str,
                    date_to=date_to_str,
                    user_id=config.user_id,
                )
                all_results.append(result)
                banners_with_results += 1

            # Remove found banners from remaining set (they belong to this cabinet)
            remaining_banner_ids -= vk_valid_ids

            logger.info(f"    Created {banners_with_results} results for {cabinet.account_name}, {len(remaining_banner_ids)} banners remaining")

        # Log remaining banners that weren't found in any cabinet
        if remaining_banner_ids:
            logger.warning(f"  {len(remaining_banner_ids)} banners from label '{label}' not found in any VK cabinet")

    logger.info("")
    logger.info(f"Total: {len(all_results)} analysis results created")
    return all_results, cabinet_totals


def save_results(db, results: List[AnalysisResult], user_id: int) -> int:
    """
    Save analysis results to database.

    Args:
        db: Database session
        results: List of analysis results
        user_id: User ID

    Returns:
        Number of saved results
    """
    if not results:
        logger.warning("No results to save")
        return 0

    # Convert to dicts for database storage
    results_dicts = [r.to_dict() for r in results]

    logger.info(f"Clearing old results and saving {len(results_dicts)} new results...")
    count = crud.replace_leadstech_analysis_results(db, results_dicts, user_id=user_id)
    logger.info(f"Saved {count} results to database (replaced all previous)")

    return count


def run_analysis():
    """Main analysis function."""
    setup_logging()
    logger.info("=== LeadsTech Analysis Starting ===")

    # Get user_id from environment
    try:
        user_id = get_user_id_from_env()
    except ValueError as e:
        logger.error(str(e))
        return

    logger.info(f"Running analysis for user_id={user_id}")

    db = SessionLocal()

    try:
        # 1. Load configuration
        try:
            config = load_analysis_config(db, user_id)
        except ValueError as e:
            logger.error(str(e))
            return

        # 2. Create LeadsTech client
        lt_client = LeadstechClient(config.leadstech)

        # 3. Analyze all cabinets with optimized grouping by label
        all_results, cabinet_totals = analyze_all_cabinets(lt_client, config)

        # 4. Save results
        save_results(db, all_results, user_id)

        # 5. Save cabinet totals (total VK spent per cabinet)
        crud.save_leadstech_cabinet_totals(
            db, user_id, cabinet_totals,
            config.date_from.isoformat(), config.date_to.isoformat()
        )

        logger.info("=== LeadsTech Analysis Complete ===")

    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_analysis()
