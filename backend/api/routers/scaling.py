"""
Scaling and Auto-Disable endpoints
"""
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user, require_feature
from api.schemas.scaling import (
    ScalingConfigCreate,
    ScalingConfigUpdate,
    ManualDuplicateRequest,
)
from api.services.scaling_worker import run_duplication_task, run_auto_scaling_task

router = APIRouter(prefix="/api/scaling", tags=["Scaling"])


# === Scaling Configs ===

@router.get("/configs")
async def get_scaling_configs_endpoint(
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Get all scaling configurations"""
    configs = crud.get_scaling_configs(db, user_id=current_user.id)
    result = []

    for config in configs:
        conditions = crud.get_scaling_conditions(db, config.id)
        account_ids = crud.get_scaling_config_account_ids(db, config.id)
        manual_groups = crud.get_manual_scaling_groups(db, config.id)
        result.append({
            "id": config.id,
            "name": config.name,
            "enabled": config.enabled,
            "schedule_time": config.schedule_time,
            "scheduled_enabled": getattr(config, 'scheduled_enabled', True),
            "account_id": config.account_id,
            "account_ids": account_ids,
            "new_budget": config.new_budget,
            "new_name": getattr(config, 'new_name', None),
            "auto_activate": config.auto_activate,
            "lookback_days": config.lookback_days,
            "duplicates_count": config.duplicates_count or 1,
            "vk_ad_group_ids": manual_groups,
            "use_leadstech_roi": getattr(config, 'use_leadstech_roi', False),
            # Banner-level scaling toggles
            "activate_positive_banners": getattr(config, 'activate_positive_banners', True),
            "duplicate_negative_banners": getattr(config, 'duplicate_negative_banners', True),
            "activate_negative_banners": getattr(config, 'activate_negative_banners', False),
            "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
            "created_at": config.created_at.isoformat(),
            "conditions": [
                {"id": c.id, "metric": c.metric, "operator": c.operator, "value": c.value}
                for c in conditions
            ]
        })

    return result


@router.get("/configs/{config_id}")
async def get_scaling_config_endpoint(
    config_id: int,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Get a single scaling configuration by ID"""
    config = crud.get_scaling_config_by_id(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if config.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    conditions = crud.get_scaling_conditions(db, config_id)
    account_ids = crud.get_scaling_config_account_ids(db, config_id)
    manual_groups = crud.get_manual_scaling_groups(db, config_id)

    return {
        "id": config.id,
        "name": config.name,
        "enabled": config.enabled,
        "schedule_time": config.schedule_time,
        "scheduled_enabled": getattr(config, 'scheduled_enabled', True),
        "account_id": config.account_id,
        "account_ids": account_ids,
        "new_budget": config.new_budget,
        "new_name": getattr(config, 'new_name', None),
        "auto_activate": config.auto_activate,
        "lookback_days": config.lookback_days,
        "duplicates_count": config.duplicates_count or 1,
        "vk_ad_group_ids": manual_groups,
        "use_leadstech_roi": getattr(config, 'use_leadstech_roi', False),
        # Banner-level scaling toggles
        "activate_positive_banners": getattr(config, 'activate_positive_banners', True),
        "duplicate_negative_banners": getattr(config, 'duplicate_negative_banners', True),
        "activate_negative_banners": getattr(config, 'activate_negative_banners', False),
        "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
        "created_at": config.created_at.isoformat(),
        "conditions": [
            {"id": c.id, "metric": c.metric, "operator": c.operator, "value": c.value}
            for c in conditions
        ]
    }


@router.post("/configs")
async def create_scaling_config_endpoint(
    data: ScalingConfigCreate,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Create new scaling configuration"""
    try:
        config = crud.create_scaling_config(
            db,
            user_id=current_user.id,
            name=data.name,
            schedule_time=data.schedule_time,
            account_id=data.account_id,
            account_ids=data.account_ids,
            new_budget=data.new_budget,
            new_name=data.new_name,
            auto_activate=data.auto_activate,
            lookback_days=data.lookback_days,
            duplicates_count=data.duplicates_count,
            enabled=data.enabled,
            scheduled_enabled=data.scheduled_enabled,
            vk_ad_group_ids=data.vk_ad_group_ids,
            use_leadstech_roi=data.use_leadstech_roi,
            # Banner-level scaling toggles
            activate_positive_banners=data.activate_positive_banners,
            duplicate_negative_banners=data.duplicate_negative_banners,
            activate_negative_banners=data.activate_negative_banners
        )

        if data.conditions:
            conditions_data = [c.model_dump() for c in data.conditions]
            crud.set_scaling_conditions(db, config.id, conditions_data)

        db.refresh(config)
        return {"id": int(config.id), "message": "Configuration created"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create configuration: {str(e)}")


@router.put("/configs/{config_id}")
async def update_scaling_config_endpoint(
    config_id: int,
    data: ScalingConfigUpdate,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Update scaling configuration"""
    try:
        config = crud.update_scaling_config(
            db,
            config_id,
            name=data.name,
            schedule_time=data.schedule_time,
            account_id=data.account_id,
            account_ids=data.account_ids,
            new_budget=data.new_budget,
            new_name=data.new_name,
            auto_activate=data.auto_activate,
            lookback_days=data.lookback_days,
            duplicates_count=data.duplicates_count,
            enabled=data.enabled,
            scheduled_enabled=data.scheduled_enabled,
            vk_ad_group_ids=data.vk_ad_group_ids,
            use_leadstech_roi=data.use_leadstech_roi,
            # Banner-level scaling toggles
            activate_positive_banners=data.activate_positive_banners,
            duplicate_negative_banners=data.duplicate_negative_banners,
            activate_negative_banners=data.activate_negative_banners
        )

        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")

        if data.conditions is not None:
            conditions_data = [c.model_dump() for c in data.conditions]
            crud.set_scaling_conditions(db, config_id, conditions_data)

        db.refresh(config)
        return {"message": "Configuration updated"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.delete("/configs/{config_id}")
async def delete_scaling_config_endpoint(
    config_id: int,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Delete scaling configuration"""
    if not crud.delete_scaling_config(db, config_id):
        raise HTTPException(status_code=404, detail="Configuration not found")
    return {"message": "Configuration deleted"}


@router.get("/logs")
async def get_scaling_logs_endpoint(
    config_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Get scaling logs"""
    logs, total = crud.get_scaling_logs(db, user_id=current_user.id, config_id=config_id, limit=limit, offset=offset)

    return {
        "items": [
            {
                "id": log.id,
                "config_id": log.config_id,
                "config_name": log.config_name,
                "account_name": log.account_name,
                "original_group_id": log.original_group_id,
                "original_group_name": log.original_group_name,
                "new_group_id": log.new_group_id,
                "new_group_name": log.new_group_name,
                "stats_snapshot": log.stats_snapshot,
                "success": log.success,
                "error_message": log.error_message,
                "total_banners": log.total_banners,
                "duplicated_banners": log.duplicated_banners,
                "duplicated_banner_ids": log.duplicated_banner_ids,
                # Banner-level classification data
                "positive_banner_ids": getattr(log, 'positive_banner_ids', None),
                "negative_banner_ids": getattr(log, 'negative_banner_ids', None),
                "positive_count": getattr(log, 'positive_count', 0),
                "negative_count": getattr(log, 'negative_count', 0),
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "total": total
    }


# === Scaling Tasks ===

@router.get("/tasks")
async def get_scaling_tasks(
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Get active and recent scaling tasks"""
    active_tasks = crud.get_active_scaling_tasks(db, user_id=current_user.id)
    recent_tasks = crud.get_recent_scaling_tasks(db, user_id=current_user.id, limit=5)

    def task_to_dict(task):
        return {
            "id": task.id,
            "task_type": task.task_type,
            "config_id": task.config_id,
            "config_name": task.config_name,
            "account_name": task.account_name,
            "status": task.status,
            "total_operations": task.total_operations,
            "completed_operations": task.completed_operations,
            "successful_operations": task.successful_operations,
            "failed_operations": task.failed_operations,
            "current_group_id": task.current_group_id,
            "current_group_name": task.current_group_name,
            "last_error": task.last_error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    return {
        "active": [task_to_dict(t) for t in active_tasks],
        "recent": [task_to_dict(t) for t in recent_tasks if t.status not in ['pending', 'running']]
    }


@router.get("/tasks/{task_id}")
async def get_scaling_task(
    task_id: int,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Get specific scaling task"""
    task = crud.get_scaling_task(db, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "id": task.id,
        "task_type": task.task_type,
        "config_id": task.config_id,
        "config_name": task.config_name,
        "account_name": task.account_name,
        "status": task.status,
        "total_operations": task.total_operations,
        "completed_operations": task.completed_operations,
        "successful_operations": task.successful_operations,
        "failed_operations": task.failed_operations,
        "current_group_id": task.current_group_id,
        "current_group_name": task.current_group_name,
        "last_error": task.last_error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_scaling_task(
    task_id: int,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Cancel a scaling task"""
    task = crud.get_scaling_task(db, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ['pending', 'running']:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")

    crud.cancel_scaling_task(db, task_id)
    return {"message": "Task cancelled"}


@router.get("/ad-groups/{account_name}")
async def get_account_ad_groups_with_stats(
    account_name: str,
    lookback_days: int = 7,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Get ad groups with statistics for an account"""
    from utils.vk_api import get_ad_groups_with_stats

    accounts = crud.get_accounts(db, user_id=current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == account_name:
            target_account = acc
            break

    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    base_url = "https://ads.vk.com/api/v2"

    try:
        groups = get_ad_groups_with_stats(
            token=target_account.api_token,
            base_url=base_url,
            date_from=date_from,
            date_to=date_to
        )

        return {
            "account_name": account_name,
            "date_from": date_from,
            "date_to": date_to,
            "groups": groups
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ad groups: {str(e)}")


@router.post("/duplicate")
async def manual_duplicate_ad_group(
    data: ManualDuplicateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Manually duplicate ad groups (runs in background with progress tracking)"""
    target_account = crud.get_account_by_db_id(db, current_user.id, data.account_id)
    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    duplicates_count = max(1, min(data.duplicates_count, 100))
    total_operations = len(data.ad_group_ids) * duplicates_count

    task = crud.create_scaling_task(
        db,
        user_id=current_user.id,
        task_type='manual',
        account_name=target_account.name,
        total_operations=total_operations
    )

    background_tasks.add_task(
        run_duplication_task,
        task_id=task.id,
        user_id=current_user.id,
        account_token=target_account.api_token,
        account_name=target_account.name,
        ad_group_ids=data.ad_group_ids,
        duplicates_count=duplicates_count,
        new_budget=data.new_budget,
        new_name=data.new_name,
        auto_activate=data.auto_activate
    )

    return {
        "task_id": task.id,
        "message": "Duplication task started",
        "total_operations": total_operations
    }


@router.post("/run/{config_id}")
async def run_scaling_config(
    config_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """Manually run a scaling configuration (runs in background with progress tracking)"""
    config = crud.get_scaling_config_by_id(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    conditions = crud.get_scaling_conditions(db, config_id)
    if not conditions:
        raise HTTPException(status_code=400, detail="No conditions defined for this configuration")

    account_ids = crud.get_scaling_config_account_ids(db, config_id)

    if account_ids:
        all_accounts = crud.get_accounts(db, user_id=current_user.id)
        accounts = [a for a in all_accounts if a.id in account_ids]
    elif config.account_id:
        all_accounts = crud.get_accounts(db, user_id=current_user.id)
        accounts = [a for a in all_accounts if a.id == config.account_id]
    else:
        accounts = crud.get_accounts(db, user_id=current_user.id)

    if not accounts:
        raise HTTPException(status_code=404, detail="No accounts found")

    duplicates_count = config.duplicates_count or 1

    task = crud.create_scaling_task(
        db,
        user_id=current_user.id,
        task_type='auto',
        config_id=config.id,
        config_name=config.name,
        account_name=", ".join([a.name for a in accounts]),
        total_operations=0
    )

    accounts_data = [(acc.id, acc.name, acc.api_token) for acc in accounts]

    conditions_data = [
        {'metric': cond.metric, 'operator': cond.operator, 'value': cond.value}
        for cond in conditions
    ]

    background_tasks.add_task(
        run_auto_scaling_task,
        task_id=task.id,
        user_id=current_user.id,
        config_id=config.id,
        config_name=config.name,
        conditions=conditions_data,
        accounts=accounts_data,
        lookback_days=config.lookback_days,
        duplicates_count=duplicates_count,
        new_budget=config.new_budget,
        new_name=getattr(config, 'new_name', None),
        auto_activate=config.auto_activate
    )

    return {
        "task_id": task.id,
        "message": "Auto-scaling task started",
        "config_name": config.name
    }


@router.get("/leadstech-status")
async def get_leadstech_status_for_accounts(
    current_user: User = Depends(require_feature("scaling")),
    db: Session = Depends(get_db)
):
    """
    Get LeadsTech availability status for all user accounts.
    Returns dict mapping account_id to {enabled: bool, cabinet_name: str}.
    Used by frontend to enable/disable LeadsTech ROI checkbox.
    """
    accounts = crud.get_accounts(db, user_id=current_user.id)

    result = {}
    for account in accounts:
        lt_cabinet = crud.get_leadstech_cabinet_by_account(db, account.id)
        if lt_cabinet and lt_cabinet.enabled:
            result[account.id] = {
                "enabled": True,
                "label": lt_cabinet.leadstech_label,
            }
        else:
            result[account.id] = {
                "enabled": False,
                "label": None,
            }

    return result

