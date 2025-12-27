"""
LeadsTech Analyzer - Main Entry Point

Orchestrates analysis across all cabinets:
1. Loads configuration from database
2. Fetches data from LeadsTech API
3. Fetches spending from VK Ads API
4. Calculates ROI and saves results
"""

import sys
from pathlib import Path
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from database import crud
from utils.logging_setup import get_logger, setup_logging as init_logging

from leadstech.leadstech_client import LeadstechClient
from leadstech.vk_client import VkAdsClient, VkAdsConfig
from leadstech.aggregator import (
    AnalysisResult,
    aggregate_leadstech_by_banner,
    merge_data_and_calculate_roi,
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


def analyze_cabinet(
    lt_client: LeadstechClient,
    cabinet: CabinetConfig,
    config: LeadstechAnalysisConfig,
) -> List[AnalysisResult]:
    """
    Analyze a single cabinet.

    Args:
        lt_client: LeadsTech API client
        cabinet: Cabinet configuration
        config: Analysis configuration

    Returns:
        List of analysis results for this cabinet
    """
    cabinet_name = cabinet.account_name
    lt_label = cabinet.leadstech_label

    logger.info(f"--- Processing cabinet: {cabinet_name} (label={lt_label}) ---")

    # 1. Fetch LeadsTech data
    try:
        lt_rows = lt_client.get_stat_by_subid(
            date_from=config.date_from,
            date_to=config.date_to,
            sub1_value=lt_label,
            subs_fields=config.banner_sub_fields,
        )
    except Exception as e:
        logger.error(f"Failed to fetch LeadsTech data for {cabinet_name}: {repr(str(e))}")
        return []

    lt_by_banner = aggregate_leadstech_by_banner(lt_rows, config.banner_sub_fields)

    if not lt_by_banner:
        logger.warning(f"Cabinet {cabinet_name}: no LeadsTech data, skipping")
        return []

    banner_ids = sorted(lt_by_banner.keys())
    logger.info(f"Cabinet {cabinet_name}: {len(banner_ids)} banners from LeadsTech")
    logger.info(f"Cabinet {cabinet_name}: first 10 banner IDs: {banner_ids[:10]}")

    # 2. Fetch VK Ads spending
    token_prefix = cabinet.api_token[:25] if cabinet.api_token else "NONE"
    logger.info(f"Cabinet {cabinet_name}: using VK API token {token_prefix}...")

    vk_cfg = VkAdsConfig(
        base_url="https://ads.vk.com/api/v2",
        api_token=cabinet.api_token,
    )
    vk_client = VkAdsClient(vk_cfg)

    try:
        vk_spent_by_banner = vk_client.get_spent_by_banner(
            config.date_from,
            config.date_to,
            banner_ids,
        )
    except Exception as e:
        logger.error(f"Failed to fetch VK Ads data for {cabinet_name}: {e}")
        vk_spent_by_banner = {}

    # Log how many banners have spending data
    banners_with_spent = sum(1 for v in vk_spent_by_banner.values() if v > 0)
    logger.info(
        f"Cabinet {cabinet_name}: VK returned spend for "
        f"{len(vk_spent_by_banner)}/{len(banner_ids)} banners "
        f"({banners_with_spent} with non-zero spent)"
    )

    if len(vk_spent_by_banner) == 0:
        logger.warning(
            f"Cabinet {cabinet_name}: VK API returned NO data for any banners! "
            f"Check if banner IDs exist in this VK account."
        )

    # 3. Merge and calculate ROI
    results = merge_data_and_calculate_roi(
        lt_by_banner=lt_by_banner,
        vk_spent_by_banner=vk_spent_by_banner,
        cabinet_name=cabinet_name,
        lt_label=lt_label,
        date_from=config.date_from,
        date_to=config.date_to,
        user_id=config.user_id,
    )

    return results


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

        # 3. Analyze each cabinet
        all_results: List[AnalysisResult] = []
        for cabinet in config.cabinets:
            results = analyze_cabinet(lt_client, cabinet, config)
            all_results.extend(results)

        # 4. Save results
        save_results(db, all_results, user_id)

        logger.info("=== LeadsTech Analysis Complete ===")

    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_analysis()
