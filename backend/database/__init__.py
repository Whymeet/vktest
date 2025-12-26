"""
Database package
"""
from .database import engine, SessionLocal, get_db, init_db, drop_db
from .models import (
    Base,
    User,
    UserFeature,
    RefreshToken,
    UserSettings,
    Account,
    WhitelistBanner,
    BannerAction,
    ActiveBanner,
    Settings,
    ProcessState,
    DailyAccountStats,
    LeadsTechConfig,
    LeadsTechCabinet,
    LeadsTechAnalysisResult,
    ScalingConfig,
    ScalingConfigAccount,
    ScalingCondition,
    ScalingLog,
    ScalingTask,
    ManualScalingGroup,
    DisableRule,
    DisableRuleCondition,
    DisableRuleAccount,
)

# Backward compatibility: allow `from database import crud`
from database import crud

__all__ = [
    # Database
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "drop_db",
    # Models
    "Base",
    "User",
    "UserFeature",
    "RefreshToken",
    "UserSettings",
    "Account",
    "WhitelistBanner",
    "BannerAction",
    "ActiveBanner",
    "Settings",
    "ProcessState",
    "DailyAccountStats",
    "LeadsTechConfig",
    "LeadsTechCabinet",
    "LeadsTechAnalysisResult",
    "ScalingConfig",
    "ScalingConfigAccount",
    "ScalingCondition",
    "ScalingLog",
    "ScalingTask",
    "ManualScalingGroup",
    "DisableRule",
    "DisableRuleCondition",
    "DisableRuleAccount",
    # CRUD module
    "crud",
]
