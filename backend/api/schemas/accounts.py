"""
Account schemas
"""
from typing import Optional
from pydantic import BaseModel


class AccountModel(BaseModel):
    name: str
    api: str
    trigger: Optional[int] = None
    spent_limit_rub: float = 100.0
    label: Optional[str] = None


class AccountCreate(BaseModel):
    name: str
    api: str
    trigger: Optional[int] = None
    spent_limit_rub: Optional[float] = 100.0
    label: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    api: Optional[str] = None
    trigger: Optional[int] = None
    spent_limit_rub: Optional[float] = None
    label: Optional[str] = None
