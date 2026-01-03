"""
Scheduler configuration - constants, paths, and settings dataclasses
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Environment detection
IN_DOCKER = os.environ.get('IN_DOCKER', 'false').lower() == 'true'

# Paths
if IN_DOCKER:
    PROJECT_ROOT = Path("/app")
else:
    PROJECT_ROOT = Path(__file__).parent.parent

MAIN_SCRIPT = PROJECT_ROOT / "core" / "main.py"
LOGS_DIR = PROJECT_ROOT / "logs"
SCHEDULER_LOGS_DIR = LOGS_DIR / "scheduler"

# VK API
VK_API_BASE_URL = "https://ads.vk.com/api/v2"

# Batch processing
STATS_BATCH_SIZE = 100
BATCH_DELAY_SECONDS = 0.1  # Delay between batches (VK API: 35 req/s limit)

# Analysis
DEFAULT_LOOKBACK_DAYS = 7
EXTRA_LOOKBACK_DAYS_MIN = 5
EXTRA_LOOKBACK_DAYS_MAX = 30

# Telegram
BANNERS_PER_MESSAGE = 15
TELEGRAM_MESSAGE_DELAY = 0.3

# Retry settings
DEFAULT_MAX_RETRIES = 3
RATE_LIMIT_RETRY_MULTIPLIER = 3  # seconds per attempt for rate limit


@dataclass
class QuietHoursSettings:
    """Settings for quiet hours (no analysis during this period)"""
    enabled: bool = False
    start: str = "23:00"
    end: str = "08:00"


@dataclass
class ReenableSettings:
    """Settings for auto-enabling disabled banners"""
    enabled: bool = False
    interval_minutes: int = 120  # Run every 2 hours by default
    lookback_hours: int = 24  # Search for banners disabled in last 24 hours
    delay_after_analysis_seconds: int = 30
    dry_run: bool = True


@dataclass
class RoiReenableSettings:
    """Settings for ROI-based auto-enabling of disabled banners"""
    enabled: bool = False
    interval_minutes: int = 60  # Run every hour by default
    lookback_days: int = 7  # Analyze ROI for last 7 days
    roi_threshold: float = 50.0  # Enable banners with ROI >= 50%
    account_ids: List[int] = field(default_factory=list)  # Specific accounts to analyze
    dry_run: bool = True
    delay_after_analysis_seconds: int = 30


@dataclass
class SchedulerSettings:
    """Main scheduler settings loaded from database"""
    enabled: bool = True
    interval_minutes: int = 60
    max_runs: int = 0  # 0 = unlimited
    start_delay_seconds: int = 10
    retry_on_error: bool = True
    retry_delay_minutes: int = 5
    max_retries: int = 3
    quiet_hours: QuietHoursSettings = field(default_factory=QuietHoursSettings)
    reenable: ReenableSettings = field(default_factory=ReenableSettings)
    roi_reenable: RoiReenableSettings = field(default_factory=RoiReenableSettings)

    @classmethod
    def from_dict(cls, data: Dict) -> 'SchedulerSettings':
        """Create settings from dictionary (DB format)"""
        quiet_hours_data = data.get("quiet_hours", {})
        reenable_data = data.get("reenable", {})
        roi_reenable_data = data.get("roi_reenable", {})

        return cls(
            enabled=data.get("enabled", True),
            interval_minutes=data.get("interval_minutes", 60),
            max_runs=data.get("max_runs", 0),
            start_delay_seconds=data.get("start_delay_seconds", 10),
            retry_on_error=data.get("retry_on_error", True),
            retry_delay_minutes=data.get("retry_delay_minutes", 5),
            max_retries=data.get("max_retries", 3),
            quiet_hours=QuietHoursSettings(
                enabled=quiet_hours_data.get("enabled", False),
                start=quiet_hours_data.get("start", "23:00"),
                end=quiet_hours_data.get("end", "08:00"),
            ),
            reenable=ReenableSettings(
                enabled=reenable_data.get("enabled", False),
                interval_minutes=reenable_data.get("interval_minutes", 120),
                lookback_hours=reenable_data.get("lookback_hours", 24),
                delay_after_analysis_seconds=reenable_data.get("delay_after_analysis_seconds", 30),
                dry_run=reenable_data.get("dry_run", True),
            ),
            roi_reenable=RoiReenableSettings(
                enabled=roi_reenable_data.get("enabled", False),
                interval_minutes=roi_reenable_data.get("interval_minutes", 60),
                lookback_days=roi_reenable_data.get("lookback_days", 7),
                roi_threshold=roi_reenable_data.get("roi_threshold", 50.0),
                account_ids=roi_reenable_data.get("account_ids", []),
                dry_run=roi_reenable_data.get("dry_run", True),
                delay_after_analysis_seconds=roi_reenable_data.get("delay_after_analysis_seconds", 30),
            ),
        )

    def to_dict(self) -> Dict:
        """Convert settings to dictionary for DB storage"""
        return {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "max_runs": self.max_runs,
            "start_delay_seconds": self.start_delay_seconds,
            "retry_on_error": self.retry_on_error,
            "retry_delay_minutes": self.retry_delay_minutes,
            "max_retries": self.max_retries,
            "quiet_hours": {
                "enabled": self.quiet_hours.enabled,
                "start": self.quiet_hours.start,
                "end": self.quiet_hours.end,
            },
            "reenable": {
                "enabled": self.reenable.enabled,
                "interval_minutes": self.reenable.interval_minutes,
                "lookback_hours": self.reenable.lookback_hours,
                "delay_after_analysis_seconds": self.reenable.delay_after_analysis_seconds,
                "dry_run": self.reenable.dry_run,
            },
            "roi_reenable": {
                "enabled": self.roi_reenable.enabled,
                "interval_minutes": self.roi_reenable.interval_minutes,
                "lookback_days": self.roi_reenable.lookback_days,
                "roi_threshold": self.roi_reenable.roi_threshold,
                "account_ids": self.roi_reenable.account_ids,
                "dry_run": self.roi_reenable.dry_run,
                "delay_after_analysis_seconds": self.roi_reenable.delay_after_analysis_seconds,
            },
        }


def get_default_settings() -> Dict:
    """Get default scheduler settings as dictionary"""
    return SchedulerSettings().to_dict()
