"""
LeadsTech schemas
"""
from typing import List, Optional
from pydantic import BaseModel


class LeadsTechConfigCreate(BaseModel):
    login: str
    password: Optional[str] = None
    base_url: str = "https://api.leads.tech"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    banner_sub_fields: List[str] = ["sub4", "sub5"]


class LeadsTechCabinetCreate(BaseModel):
    account_id: int
    leadstech_label: str
    enabled: bool = True


class LeadsTechCabinetUpdate(BaseModel):
    leadstech_label: Optional[str] = None
    enabled: Optional[bool] = None


class LeadsTechAnalysisSettings(BaseModel):
    """Settings for LeadsTech analysis"""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    banner_sub_fields: List[str] = ["sub4", "sub5"]
    min_spent_rub: float = 0.0
    target_cost_per_goal: Optional[float] = None
