"""
Settings schemas
"""
from typing import List, Optional
from pydantic import BaseModel


class AnalysisSettings(BaseModel):
    lookback_days: int = 10
    spent_limit_rub: float = 100.0
    dry_run: bool = False
    sleep_between_calls: float = 3.0


class TelegramSettings(BaseModel):
    bot_token: str
    chat_id: List[str]
    enabled: bool = True


class QuietHours(BaseModel):
    enabled: bool = False
    start: str = "23:00"
    end: str = "08:00"


class SecondPassSettings(BaseModel):
    enabled: bool = True
    extra_days_min: int = 7
    extra_days_max: int = 50
    delay_seconds: int = 30


class ReEnableSettings(BaseModel):
    """Settings for auto re-enabling previously disabled banners (runs after main analysis)"""
    enabled: bool = False
    interval_minutes: int = 120
    lookback_hours: int = 24
    delay_after_analysis_seconds: int = 30
    dry_run: bool = True


class RoiReenableSettings(BaseModel):
    """Settings for ROI-based auto-enabling of disabled banners.
    Uses enabled LeadsTech cabinets (same as LeadsTech analysis).
    """
    enabled: bool = False
    interval_minutes: int = 60
    lookback_days: int = 7
    roi_threshold: float = 50.0
    dry_run: bool = True
    delay_after_analysis_seconds: int = 30


class SchedulerSettings(BaseModel):
    enabled: bool = True
    interval_minutes: float = 60
    max_runs: int = 0
    start_delay_seconds: int = 10
    retry_on_error: bool = True
    retry_delay_minutes: float = 5
    max_retries: int = 3
    quiet_hours: QuietHours = QuietHours()
    second_pass: SecondPassSettings = SecondPassSettings()
    reenable: ReEnableSettings = ReEnableSettings()
    roi_reenable: Optional[RoiReenableSettings] = None


class StatisticsTriggerSettings(BaseModel):
    enabled: bool = False
    wait_seconds: int = 10


class FullConfig(BaseModel):
    analysis_settings: AnalysisSettings
    telegram: TelegramSettings
    scheduler: SchedulerSettings
    statistics_trigger: StatisticsTriggerSettings


class LeadsTechCredentialsUpdate(BaseModel):
    """For updating LeadsTech credentials via settings endpoint"""
    login: Optional[str] = None
    password: Optional[str] = None
    base_url: Optional[str] = None
