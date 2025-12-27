"""
Core config loader - Load analysis configuration from database
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from database import SessionLocal
from database import crud


@dataclass
class AccountConfig:
    """Configuration for a single VK Ads account"""
    api_token: str
    trigger_id: Optional[int] = None
    spent_limit_rub: float = 100.0


@dataclass
class TelegramConfig:
    """Telegram notification settings"""
    bot_token: str = ""
    chat_ids: List[str] = field(default_factory=list)
    enabled: bool = False


@dataclass
class StatisticsTriggerConfig:
    """Statistics refresh trigger settings"""
    enabled: bool = False
    wait_seconds: int = 10


@dataclass
class AnalysisSettings:
    """Analysis parameters"""
    lookback_days: int = 10
    spent_limit_rub: float = 100.0
    dry_run: bool = False
    sleep_between_calls: float = 0.25


@dataclass
class AnalysisConfig:
    """Complete configuration for analysis run"""
    base_url: str
    accounts: Dict[str, AccountConfig]
    settings: AnalysisSettings
    telegram: TelegramConfig
    statistics_trigger: StatisticsTriggerConfig
    whitelist: Set[int]
    user_id: int

    def get_effective_lookback_days(self, extra_days: int = 0) -> int:
        """Get lookback days with optional extra days added"""
        return self.settings.lookback_days + extra_days


def get_user_id_from_env() -> int:
    """Get user_id from environment variable"""
    user_id = os.environ.get('VK_ADS_USER_ID')
    if not user_id:
        raise ValueError("VK_ADS_USER_ID environment variable is required")
    return int(user_id)


def get_extra_lookback_days() -> int:
    """Get extra lookback days from environment variable"""
    return int(os.environ.get("VK_EXTRA_LOOKBACK_DAYS", "0"))


def load_whitelist_from_db(user_id: int) -> Set[int]:
    """
    Load banner whitelist from database.

    Args:
        user_id: User ID

    Returns:
        Set of whitelisted banner IDs
    """
    db = SessionLocal()
    try:
        banner_ids = crud.get_whitelist(db, user_id)
        whitelist_set = set()
        for v in banner_ids:
            try:
                whitelist_set.add(int(v))
            except (ValueError, TypeError):
                continue
        return whitelist_set
    finally:
        db.close()


def load_config_from_db(user_id: Optional[int] = None) -> AnalysisConfig:
    """
    Load complete analysis configuration from PostgreSQL.

    Args:
        user_id: User ID (if None, gets from environment)

    Returns:
        AnalysisConfig with all settings
    """
    if user_id is None:
        user_id = get_user_id_from_env()

    db = SessionLocal()
    try:
        # Get all user settings
        all_settings = crud.get_all_user_settings(db, user_id)
        analysis_settings_dict = all_settings.get('analysis_settings', {})
        telegram_settings = all_settings.get('telegram', {})
        statistics_trigger = all_settings.get('statistics_trigger', {})

        # Get user accounts
        accounts_db = crud.get_accounts(db, user_id)
        accounts = {}
        for acc in accounts_db:
            accounts[acc.name] = AccountConfig(
                api_token=acc.api_token,
                trigger_id=getattr(acc, 'trigger_id', None),
                spent_limit_rub=100.0  # Default, can be added to model later
            )

        # Build config objects
        settings = AnalysisSettings(
            lookback_days=analysis_settings_dict.get("lookback_days", 10),
            spent_limit_rub=analysis_settings_dict.get("spent_limit_rub", 100.0),
            dry_run=analysis_settings_dict.get("dry_run", False),
            sleep_between_calls=analysis_settings_dict.get("sleep_between_calls", 0.25)
        )

        telegram = TelegramConfig(
            bot_token=telegram_settings.get("bot_token", ""),
            chat_ids=telegram_settings.get("chat_id", []),
            enabled=telegram_settings.get("enabled", False)
        )

        trigger = StatisticsTriggerConfig(
            enabled=statistics_trigger.get("enabled", False),
            wait_seconds=statistics_trigger.get("wait_seconds", 10)
        )

        # Load whitelist
        whitelist = load_whitelist_from_db(user_id)

        return AnalysisConfig(
            base_url="https://ads.vk.com/api/v2",
            accounts=accounts,
            settings=settings,
            telegram=telegram,
            statistics_trigger=trigger,
            whitelist=whitelist,
            user_id=user_id
        )
    finally:
        db.close()


def config_to_legacy_dict(config: AnalysisConfig) -> dict:
    """
    Convert AnalysisConfig to legacy dictionary format for backward compatibility.

    Args:
        config: AnalysisConfig object

    Returns:
        Dictionary in the old format expected by existing code
    """
    accounts_dict = {}
    for name, acc in config.accounts.items():
        accounts_dict[name] = {
            "api": acc.api_token,
            "trigger": acc.trigger_id,
            "spent_limit_rub": acc.spent_limit_rub
        }

    return {
        "vk_ads_api": {
            "base_url": config.base_url,
            "accounts": accounts_dict
        },
        "analysis_settings": {
            "lookback_days": config.settings.lookback_days,
            "spent_limit_rub": config.settings.spent_limit_rub,
            "dry_run": config.settings.dry_run,
            "sleep_between_calls": config.settings.sleep_between_calls
        },
        "telegram": {
            "bot_token": config.telegram.bot_token,
            "chat_id": config.telegram.chat_ids,
            "enabled": config.telegram.enabled
        },
        "statistics_trigger": {
            "enabled": config.statistics_trigger.enabled,
            "wait_seconds": config.statistics_trigger.wait_seconds
        }
    }
