"""
VK Ads API - Modular API client

This package provides functions for working with VK Ads API.
All functions are re-exported here for backward compatibility.
"""

# Core utilities and constants
from utils.vk_api.core import (
    API_MAX_RETRIES,
    API_RETRY_DELAY_SECONDS,
    API_RETRY_STATUS_CODES,
    VK_MIN_DAILY_BUDGET,
    _interruptible_sleep,
    _headers,
    _request_with_retries,
)

# Banner operations
from utils.vk_api.banners import (
    get_banners_active,
    get_banners_stats_day,
    get_banner_info,
    disable_banner,
    toggle_banner_status,
)

# Ad group operations
from utils.vk_api.ad_groups import (
    get_ad_groups_active,
    get_ad_groups_all,
    get_ad_group_full,
    disable_ad_group,
    toggle_ad_group_status,
    create_ad_group,
    update_ad_group,
)

# Campaign operations
from utils.vk_api.campaigns import (
    get_campaign_full,
    toggle_campaign_status,
)

# Statistics operations
from utils.vk_api.stats import (
    get_ad_groups_with_stats,
)

# Scaling / duplication operations
from utils.vk_api.scaling import (
    get_banners_by_ad_group,
    create_banner,
    _generate_copy_name,
    duplicate_ad_group_full,
)


__all__ = [
    # Core
    "API_MAX_RETRIES",
    "API_RETRY_DELAY_SECONDS",
    "API_RETRY_STATUS_CODES",
    "VK_MIN_DAILY_BUDGET",
    "_interruptible_sleep",
    "_headers",
    "_request_with_retries",
    # Banners
    "get_banners_active",
    "get_banners_stats_day",
    "get_banner_info",
    "disable_banner",
    "toggle_banner_status",
    # Ad groups
    "get_ad_groups_active",
    "get_ad_groups_all",
    "get_ad_group_full",
    "disable_ad_group",
    "toggle_ad_group_status",
    "create_ad_group",
    "update_ad_group",
    # Campaigns
    "get_campaign_full",
    "toggle_campaign_status",
    # Stats
    "get_ad_groups_with_stats",
    # Scaling
    "get_banners_by_ad_group",
    "create_banner",
    "_generate_copy_name",
    "duplicate_ad_group_full",
]
