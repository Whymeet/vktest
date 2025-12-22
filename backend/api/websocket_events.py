"""
WebSocket Event Types and Broadcast Functions
"""
from enum import Enum
from typing import Optional
from .websocket_manager import manager


class EventType(str, Enum):
    """WebSocket event types for real-time updates"""

    # Process status updates (high frequency)
    PROCESS_STATUS = "process_status"
    SCALING_TASK_UPDATE = "scaling_task_update"
    ANALYSIS_STATUS = "analysis_status"
    WHITELIST_STATUS = "whitelist_status"

    # Data updates (medium frequency)
    DASHBOARD_UPDATE = "dashboard_update"
    DISABLED_BANNERS_UPDATE = "disabled_banners_update"
    LOG_UPDATE = "log_update"
    LEADSTECH_RESULTS_UPDATE = "leadstech_results_update"

    # Configuration changes (low frequency, triggered by mutations)
    ACCOUNTS_CHANGED = "accounts_changed"
    SETTINGS_CHANGED = "settings_changed"
    WHITELIST_CHANGED = "whitelist_changed"
    SCALING_CONFIG_CHANGED = "scaling_config_changed"
    DISABLE_RULES_CHANGED = "disable_rules_changed"

    # Notifications
    TOAST = "toast"


# === Process Status Events ===

async def emit_process_status(user_id: int, status: dict):
    """Emit process status update to user"""
    await manager.send_to_user(user_id, EventType.PROCESS_STATUS, status)


async def emit_scaling_task_update(user_id: int, task_data: dict):
    """Emit scaling task update to user"""
    await manager.send_to_user(user_id, EventType.SCALING_TASK_UPDATE, task_data)


async def emit_analysis_status(user_id: int, status: dict):
    """Emit analysis status update to user"""
    await manager.send_to_user(user_id, EventType.ANALYSIS_STATUS, status)


async def emit_whitelist_status(user_id: int, status: dict):
    """Emit whitelist status update to user"""
    await manager.send_to_user(user_id, EventType.WHITELIST_STATUS, status)


# === Data Updates ===

async def emit_dashboard_update(user_id: int, dashboard_data: dict):
    """Emit dashboard data update to user"""
    await manager.send_to_user(user_id, EventType.DASHBOARD_UPDATE, dashboard_data)


async def emit_disabled_banners_update(user_id: int, data: dict):
    """Emit disabled banners update to user"""
    await manager.send_to_user(user_id, EventType.DISABLED_BANNERS_UPDATE, data)


async def emit_leadstech_results_update(user_id: int, data: dict):
    """Emit leadstech results update to user"""
    await manager.send_to_user(user_id, EventType.LEADSTECH_RESULTS_UPDATE, data)


# === Configuration Changes (invalidation triggers) ===

async def emit_accounts_changed(user_id: int, action: str = "updated"):
    """Notify client that accounts have changed - triggers refetch"""
    await manager.send_to_user(user_id, EventType.ACCOUNTS_CHANGED, {"action": action})


async def emit_settings_changed(user_id: int, section: Optional[str] = None):
    """Notify client that settings have changed - triggers refetch"""
    await manager.send_to_user(user_id, EventType.SETTINGS_CHANGED, {"section": section})


async def emit_whitelist_changed(user_id: int, action: str = "updated"):
    """Notify client that whitelist has changed - triggers refetch"""
    await manager.send_to_user(user_id, EventType.WHITELIST_CHANGED, {"action": action})


async def emit_scaling_config_changed(user_id: int, action: str = "updated"):
    """Notify client that scaling config has changed - triggers refetch"""
    await manager.send_to_user(user_id, EventType.SCALING_CONFIG_CHANGED, {"action": action})


async def emit_disable_rules_changed(user_id: int, action: str = "updated"):
    """Notify client that disable rules have changed - triggers refetch"""
    await manager.send_to_user(user_id, EventType.DISABLE_RULES_CHANGED, {"action": action})


# === Toast Notifications ===

async def emit_toast(user_id: int, toast_type: str, title: str, message: Optional[str] = None):
    """
    Send toast notification to user

    Args:
        user_id: Target user
        toast_type: 'success', 'error', 'warning', 'info'
        title: Toast title
        message: Optional toast message
    """
    await manager.send_to_user(user_id, EventType.TOAST, {
        "type": toast_type,
        "title": title,
        "message": message
    })


async def emit_toast_success(user_id: int, title: str, message: Optional[str] = None):
    """Send success toast to user"""
    await emit_toast(user_id, "success", title, message)


async def emit_toast_error(user_id: int, title: str, message: Optional[str] = None):
    """Send error toast to user"""
    await emit_toast(user_id, "error", title, message)


async def emit_toast_warning(user_id: int, title: str, message: Optional[str] = None):
    """Send warning toast to user"""
    await emit_toast(user_id, "warning", title, message)


async def emit_toast_info(user_id: int, title: str, message: Optional[str] = None):
    """Send info toast to user"""
    await emit_toast(user_id, "info", title, message)
