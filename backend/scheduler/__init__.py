"""
VK Ads Manager Scheduler Package

Modular scheduler for automatic ad analysis and banner management.
"""
from scheduler.scheduler_main import VKAdsScheduler, main
from scheduler.config import (
    SchedulerSettings,
    QuietHoursSettings,
    ReenableSettings,
    get_default_settings,
)
from scheduler.event_logger import log_scheduler_event, EventType
from scheduler.analysis import run_analysis
from scheduler.reenable import run_reenable_analysis
from scheduler.stats import get_fresh_stats, get_fresh_stats_batch
from scheduler.notifications import send_telegram_message, send_reenable_notification

__all__ = [
    # Main class and entry point
    "VKAdsScheduler",
    "main",
    # Settings
    "SchedulerSettings",
    "QuietHoursSettings",
    "ReenableSettings",
    "get_default_settings",
    # Event logging
    "log_scheduler_event",
    "EventType",
    # Analysis
    "run_analysis",
    # Reenable
    "run_reenable_analysis",
    # Stats
    "get_fresh_stats",
    "get_fresh_stats_batch",
    # Notifications
    "send_telegram_message",
    "send_reenable_notification",
]
