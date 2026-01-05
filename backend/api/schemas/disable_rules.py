"""
Disable Rules schemas
"""
from typing import List, Literal, Optional
from pydantic import BaseModel


class DisableRuleConditionModel(BaseModel):
    """Single condition for disable rule"""
    metric: str  # goals, spent, clicks, shows, ctr, cpc, cost_per_goal, roi
    operator: str  # equals, not_equals, greater_than, less_than, greater_or_equal, less_or_equal
    value: float
    order: int = 0


class DisableRuleCreate(BaseModel):
    """Create new disable rule"""
    name: str
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    conditions: List[DisableRuleConditionModel] = []
    account_ids: List[int] = []
    # ROI settings - какое sub поле использовать для поиска banner_id в LeadsTech
    roi_sub_field: Optional[Literal["sub4", "sub5"]] = None


class DisableRuleUpdate(BaseModel):
    """Update disable rule"""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    conditions: Optional[List[DisableRuleConditionModel]] = None
    account_ids: Optional[List[int]] = None
    roi_sub_field: Optional[Literal["sub4", "sub5"]] = None


class DisableRuleResponse(BaseModel):
    """Response with rule data"""
    id: int
    name: str
    description: Optional[str]
    enabled: bool
    priority: int
    roi_sub_field: Optional[str]
    created_at: str
    updated_at: str
    conditions: List[dict]
    account_ids: List[int]
    account_names: List[str]

    class Config:
        from_attributes = True
