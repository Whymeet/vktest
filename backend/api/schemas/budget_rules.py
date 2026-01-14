"""
Budget Rules schemas for auto-changing ad group budgets
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator


class BudgetRuleConditionModel(BaseModel):
    """Single condition for budget rule"""
    metric: str  # goals, spent, clicks, shows, ctr, cpc, cr, cost_per_goal, roi
    operator: str  # equals, not_equals, greater_than, less_than, greater_or_equal, less_or_equal
    value: float
    order: int = 0


class BudgetRuleCreate(BaseModel):
    """Create new budget rule"""
    name: str
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    # Scheduling
    schedule_time: Optional[str] = None  # "HH:MM" format, e.g. "07:00"
    scheduled_enabled: bool = False
    # Budget change settings
    change_percent: float  # 1-20%
    change_direction: Literal["increase", "decrease"]
    # Analysis settings
    lookback_days: int = 7
    # Conditions and accounts
    conditions: List[BudgetRuleConditionModel] = []
    account_ids: List[int] = []
    # ROI settings
    roi_sub_field: Optional[Literal["sub4", "sub5"]] = None

    @field_validator('change_percent')
    @classmethod
    def validate_change_percent(cls, v):
        if v < 1 or v > 20:
            raise ValueError('change_percent must be between 1 and 20')
        return v


class BudgetRuleUpdate(BaseModel):
    """Update budget rule"""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    schedule_time: Optional[str] = None
    scheduled_enabled: Optional[bool] = None
    change_percent: Optional[float] = None
    change_direction: Optional[Literal["increase", "decrease"]] = None
    lookback_days: Optional[int] = None
    conditions: Optional[List[BudgetRuleConditionModel]] = None
    account_ids: Optional[List[int]] = None
    roi_sub_field: Optional[Literal["sub4", "sub5"]] = None

    @field_validator('change_percent')
    @classmethod
    def validate_change_percent(cls, v):
        if v is not None and (v < 1 or v > 20):
            raise ValueError('change_percent must be between 1 and 20')
        return v


class BudgetRuleResponse(BaseModel):
    """Response with budget rule data"""
    id: int
    name: str
    description: Optional[str]
    enabled: bool
    priority: int
    schedule_time: Optional[str]
    scheduled_enabled: bool
    change_percent: float
    change_direction: str
    lookback_days: int
    roi_sub_field: Optional[str]
    last_run_at: Optional[str]
    created_at: str
    updated_at: str
    conditions: List[dict]
    account_ids: List[int]
    account_names: List[str]

    class Config:
        from_attributes = True


class BudgetChangeLogResponse(BaseModel):
    """Response with budget change log entry"""
    id: int
    rule_id: Optional[int]
    rule_name: Optional[str]
    account_name: Optional[str]
    ad_group_id: int
    ad_group_name: Optional[str]
    banner_id: Optional[int]
    banner_name: Optional[str]
    old_budget: Optional[float]
    new_budget: Optional[float]
    change_percent: float
    change_direction: str
    stats_snapshot: Optional[dict]
    success: bool
    error_message: Optional[str]
    is_dry_run: bool
    created_at: str

    class Config:
        from_attributes = True
