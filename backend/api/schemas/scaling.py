"""
Scaling and Auto-Disable schemas
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ScalingConditionModel(BaseModel):
    metric: str  # spent, shows, clicks, goals, cost_per_goal, ctr, cpc, roi
    operator: str  # >, <, >=, <=, ==, !=
    value: float


class ScalingConfigCreate(BaseModel):
    name: str
    schedule_time: str = "08:00"
    scheduled_enabled: bool = True
    account_id: Optional[int] = None
    account_ids: Optional[List[int]] = None
    new_budget: Optional[float] = None
    new_name: Optional[str] = None
    auto_activate: bool = False
    lookback_days: int = 7
    duplicates_count: int = Field(default=1, ge=1, le=100)
    enabled: bool = False
    conditions: List[ScalingConditionModel] = []
    vk_ad_group_ids: Optional[List[int]] = None
    use_leadstech_roi: bool = False  # Enable LeadsTech ROI for conditions
    # Banner-level scaling options
    activate_positive_banners: bool = True  # Activate positive banners (status=active)
    duplicate_negative_banners: bool = True  # Duplicate negative banners in group
    activate_negative_banners: bool = False  # Activate negative banners (status=active)


class ScalingConfigUpdate(BaseModel):
    name: Optional[str] = None
    schedule_time: Optional[str] = None
    scheduled_enabled: Optional[bool] = None
    account_id: Optional[int] = None
    account_ids: Optional[List[int]] = None
    new_budget: Optional[float] = None
    new_name: Optional[str] = None
    auto_activate: Optional[bool] = None
    lookback_days: Optional[int] = None
    duplicates_count: Optional[int] = Field(default=None, ge=1, le=100)
    enabled: Optional[bool] = None
    conditions: Optional[List[ScalingConditionModel]] = None
    vk_ad_group_ids: Optional[List[int]] = None
    use_leadstech_roi: Optional[bool] = None  # Enable LeadsTech ROI for conditions
    # Banner-level scaling options
    activate_positive_banners: Optional[bool] = None  # Activate positive banners (status=active)
    duplicate_negative_banners: Optional[bool] = None  # Duplicate negative banners in group
    activate_negative_banners: Optional[bool] = None  # Activate negative banners (status=active)


class ManualDuplicateRequest(BaseModel):
    account_id: int
    ad_group_ids: List[int]
    new_budget: Optional[float] = None
    new_name: Optional[str] = None
    auto_activate: bool = False
    duplicates_count: int = Field(default=1, ge=1, le=100)


# Auto-Disable models
class AutoDisableConditionModel(BaseModel):
    metric: str  # spent, shows, clicks, goals, cost_per_goal, ctr
    operator: str  # >, <, >=, <=, ==
    value: float


class AutoDisableConfigCreate(BaseModel):
    name: str
    lookback_days: int = 10
    account_ids: Optional[List[int]] = None
    enabled: bool = False
    conditions: List[AutoDisableConditionModel] = []


class AutoDisableConfigUpdate(BaseModel):
    name: Optional[str] = None
    lookback_days: Optional[int] = None
    account_ids: Optional[List[int]] = None
    enabled: Optional[bool] = None
    conditions: Optional[List[AutoDisableConditionModel]] = None
