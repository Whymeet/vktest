"""
LeadsTech Integration Module

Provides ROI analysis by combining LeadsTech revenue data with VK Ads spending.
"""

from leadstech.analyzer import run_analysis, analyze_all_cabinets, save_results
from leadstech.leadstech_client import LeadstechClient, LeadstechClientConfig
from leadstech.vk_client import VkAdsClient, VkAdsConfig
from leadstech.aggregator import (
    AnalysisResult,
    BannerAggregation,
    aggregate_leadstech_by_banner,
    merge_data_and_calculate_roi,
    calculate_roi,
)
from leadstech.config_loader import (
    LeadstechAnalysisConfig,
    CabinetConfig,
    get_user_id_from_env,
    load_analysis_config,
)

__all__ = [
    # Main entry point
    "run_analysis",
    "analyze_all_cabinets",
    "save_results",
    # LeadsTech client
    "LeadstechClient",
    "LeadstechClientConfig",
    # VK Ads client
    "VkAdsClient",
    "VkAdsConfig",
    # Aggregation
    "AnalysisResult",
    "BannerAggregation",
    "aggregate_leadstech_by_banner",
    "merge_data_and_calculate_roi",
    "calculate_roi",
    # Config
    "LeadstechAnalysisConfig",
    "CabinetConfig",
    "get_user_id_from_env",
    "load_analysis_config",
]
