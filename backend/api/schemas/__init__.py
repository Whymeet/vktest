"""
API Schemas - Pydantic models for request/response validation
"""
from api.schemas.accounts import (
    AccountModel,
    AccountCreate,
    AccountUpdate,
)
from api.schemas.settings import (
    AnalysisSettings,
    TelegramSettings,
    QuietHours,
    SecondPassSettings,
    ReEnableSettings,
    SchedulerSettings,
    StatisticsTriggerSettings,
    FullConfig,
    LeadsTechCredentialsUpdate,
)
from api.schemas.leadstech import (
    LeadsTechConfigCreate,
    LeadsTechCabinetCreate,
    LeadsTechCabinetUpdate,
    LeadsTechAnalysisSettings,
)
from api.schemas.scaling import (
    ScalingConditionModel,
    ScalingConfigCreate,
    ScalingConfigUpdate,
    ManualDuplicateRequest,
    AutoDisableConditionModel,
    AutoDisableConfigCreate,
    AutoDisableConfigUpdate,
)
from api.schemas.disable_rules import (
    DisableRuleConditionModel,
    DisableRuleCreate,
    DisableRuleUpdate,
    DisableRuleResponse,
)

__all__ = [
    # Accounts
    "AccountModel",
    "AccountCreate",
    "AccountUpdate",
    # Settings
    "AnalysisSettings",
    "TelegramSettings",
    "QuietHours",
    "SecondPassSettings",
    "ReEnableSettings",
    "SchedulerSettings",
    "StatisticsTriggerSettings",
    "FullConfig",
    "LeadsTechCredentialsUpdate",
    # LeadsTech
    "LeadsTechConfigCreate",
    "LeadsTechCabinetCreate",
    "LeadsTechCabinetUpdate",
    "LeadsTechAnalysisSettings",
    # Scaling
    "ScalingConditionModel",
    "ScalingConfigCreate",
    "ScalingConfigUpdate",
    "ManualDuplicateRequest",
    "AutoDisableConditionModel",
    "AutoDisableConfigCreate",
    "AutoDisableConfigUpdate",
    # Disable Rules
    "DisableRuleConditionModel",
    "DisableRuleCreate",
    "DisableRuleUpdate",
    "DisableRuleResponse",
]
