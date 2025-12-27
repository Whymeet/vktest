"""
Auto-Disable endpoints (separate from disable_rules)
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user, require_feature
from utils.time_utils import get_moscow_time

router = APIRouter(prefix="/api/auto-disable", tags=["Auto-Disable"])


# Pydantic models for this router
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


@router.get("/configs")
async def get_auto_disable_configs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all auto-disable configurations"""
    configs = crud.get_auto_disable_configs(db)
    result = []

    for config in configs:
        conditions = crud.get_auto_disable_conditions(db, config.id)
        account_ids = crud.get_auto_disable_config_account_ids(db, config.id)
        result.append({
            "id": config.id,
            "name": config.name,
            "enabled": config.enabled,
            "lookback_days": config.lookback_days,
            "account_ids": account_ids,
            "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
            "created_at": config.created_at.isoformat(),
            "conditions": [
                {"id": c.id, "metric": c.metric, "operator": c.operator, "value": c.value}
                for c in conditions
            ]
        })

    return result


@router.post("/configs")
async def create_auto_disable_config(
    data: AutoDisableConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new auto-disable configuration"""
    config = crud.create_auto_disable_config(
        db,
        name=data.name,
        enabled=data.enabled,
        lookback_days=data.lookback_days,
        account_ids=data.account_ids
    )

    if data.conditions:
        crud.set_auto_disable_conditions(
            db,
            config.id,
            [c.model_dump() for c in data.conditions]
        )

    return {"id": config.id, "message": "Configuration created"}


@router.put("/configs/{config_id}")
async def update_auto_disable_config(
    config_id: int,
    data: AutoDisableConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update auto-disable configuration"""
    config = crud.update_auto_disable_config(
        db,
        config_id,
        name=data.name,
        enabled=data.enabled,
        lookback_days=data.lookback_days,
        account_ids=data.account_ids
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if data.conditions is not None:
        crud.set_auto_disable_conditions(
            db,
            config_id,
            [c.model_dump() for c in data.conditions]
        )

    return {"message": "Configuration updated"}


@router.delete("/configs/{config_id}")
async def delete_auto_disable_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete auto-disable configuration"""
    if not crud.delete_auto_disable_config(db, config_id):
        raise HTTPException(status_code=404, detail="Configuration not found")
    return {"message": "Configuration deleted"}


@router.get("/logs")
async def get_auto_disable_logs(
    config_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get auto-disable logs"""
    logs, total = crud.get_auto_disable_logs(db, config_id, limit, offset)

    return {
        "items": [
            {
                "id": log.id,
                "config_id": log.config_id,
                "config_name": log.config_name,
                "account_name": log.account_name,
                "banner_id": log.banner_id,
                "banner_name": log.banner_name,
                "ad_group_id": log.ad_group_id,
                "ad_group_name": log.ad_group_name,
                "stats_snapshot": log.stats_snapshot,
                "success": log.success,
                "error_message": log.error_message,
                "is_dry_run": log.is_dry_run,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "total": total
    }


@router.get("/summary")
async def get_auto_disable_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get summary of auto-disable rules and recent activity"""
    configs = crud.get_auto_disable_configs(db)
    enabled_count = sum(1 for c in configs if c.enabled)

    logs, total_logs = crud.get_auto_disable_logs(db, limit=10)

    recent_logs, _ = crud.get_auto_disable_logs(db, limit=1000)
    now = get_moscow_time()
    disabled_24h = sum(1 for log in recent_logs
                       if log.success and
                       not log.is_dry_run and
                       (now - log.created_at).total_seconds() < 86400)

    return {
        "total_rules": len(configs),
        "enabled_rules": enabled_count,
        "disabled_24h": disabled_24h,
        "total_logs": total_logs,
        "recent_logs": [
            {
                "id": log.id,
                "config_name": log.config_name,
                "banner_id": log.banner_id,
                "banner_name": log.banner_name,
                "account_name": log.account_name,
                "success": log.success,
                "is_dry_run": log.is_dry_run,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
    }
