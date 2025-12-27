"""
VK Ads Manager Core Package

Modular analysis engine for VK advertising campaigns.
"""
from core.main import main, main_async
from core.config_loader import (
    load_config_from_db,
    load_whitelist_from_db,
    config_to_legacy_dict,
    get_user_id_from_env,
    get_extra_lookback_days,
    AnalysisConfig,
    AccountConfig,
    TelegramConfig,
    AnalysisSettings,
    StatisticsTriggerConfig,
)
from core.analyzer import analyze_account
from core.db_logger import (
    log_disabled_banners_to_db,
    save_account_stats_to_db,
    get_account_rules,
)
from core.telegram_notifier import (
    send_analysis_notifications,
    send_error_notification,
    send_summary_notification,
)
from core.results_exporter import (
    save_analysis_results,
    format_summary,
    collect_unprofitable_banners,
    get_results_totals,
)

__all__ = [
    # Main entry points
    "main",
    "main_async",
    # Config
    "load_config_from_db",
    "load_whitelist_from_db",
    "config_to_legacy_dict",
    "get_user_id_from_env",
    "get_extra_lookback_days",
    "AnalysisConfig",
    "AccountConfig",
    "TelegramConfig",
    "AnalysisSettings",
    "StatisticsTriggerConfig",
    # Analyzer
    "analyze_account",
    # DB Logger
    "log_disabled_banners_to_db",
    "save_account_stats_to_db",
    "get_account_rules",
    # Telegram
    "send_analysis_notifications",
    "send_error_notification",
    "send_summary_notification",
    # Results
    "save_analysis_results",
    "format_summary",
    "collect_unprofitable_banners",
    "get_results_totals",
]
