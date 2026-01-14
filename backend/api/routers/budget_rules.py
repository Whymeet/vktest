"""
Budget Rules management endpoints - auto-change ad group budgets
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import require_feature
from api.schemas.budget_rules import BudgetRuleCreate, BudgetRuleUpdate

router = APIRouter(prefix="/api/budget-rules", tags=["Budget Rules"])


def _format_rule_response(rule, db) -> dict:
    """Format budget rule with conditions and accounts"""
    conditions = [
        {
            "id": c.id,
            "metric": c.metric,
            "operator": c.operator,
            "value": c.value,
            "order": c.order
        }
        for c in rule.conditions
    ]

    account_ids = crud.get_budget_rule_account_ids(db, rule.id)
    accounts = crud.get_budget_rule_accounts(db, rule.id)
    account_names = [acc.name for acc in accounts]

    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "schedule_time": rule.schedule_time,
        "scheduled_enabled": rule.scheduled_enabled,
        "change_percent": rule.change_percent,
        "change_direction": rule.change_direction,
        "lookback_days": rule.lookback_days,
        "roi_sub_field": rule.roi_sub_field,
        "last_run_at": rule.last_run_at.isoformat() if rule.last_run_at else None,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "conditions": conditions,
        "account_ids": account_ids,
        "account_names": account_names
    }


@router.get("")
async def get_budget_rules(
    enabled_only: bool = False,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get all budget rules with their conditions and linked accounts for current user"""
    rules = crud.get_budget_rules(db, user_id=current_user.id, enabled_only=enabled_only)

    result = []
    for rule in rules:
        result.append(_format_rule_response(rule, db))

    return {"items": result, "total": len(result)}


@router.get("/metrics")
async def get_budget_rule_metrics(
    current_user: User = Depends(require_feature("auto_disable"))
):
    """Get available metrics and operators for budget rules"""
    return {
        "metrics": [
            {"value": "goals", "label": "Результаты (goals)", "description": "Количество конверсий/целей VK"},
            {"value": "spent", "label": "Потрачено (₽)", "description": "Сумма потраченных денег в рублях"},
            {"value": "clicks", "label": "Клики", "description": "Количество кликов по объявлению"},
            {"value": "shows", "label": "Показы", "description": "Количество показов объявления"},
            {"value": "ctr", "label": "CTR (%)", "description": "Click-through rate (клики/показы * 100)"},
            {"value": "cpc", "label": "CPC (₽)", "description": "Cost per click (цена за клик)"},
            {"value": "cr", "label": "CR (%)", "description": "Conversion Rate (конверсии/клики * 100)"},
            {"value": "cost_per_goal", "label": "Цена результата (₽)", "description": "Стоимость одной конверсии"},
            {"value": "roi", "label": "ROI (%)", "description": "Return on Investment из LeadsTech"}
        ],
        "operators": [
            {"value": "equals", "label": "=", "description": "Равно"},
            {"value": "not_equals", "label": "≠", "description": "Не равно"},
            {"value": "greater_than", "label": ">", "description": "Больше"},
            {"value": "less_than", "label": "<", "description": "Меньше"},
            {"value": "greater_or_equal", "label": "≥", "description": "Больше или равно"},
            {"value": "less_or_equal", "label": "≤", "description": "Меньше или равно"}
        ],
        "change_directions": [
            {"value": "increase", "label": "Увеличить", "description": "Увеличить бюджет на указанный процент"},
            {"value": "decrease", "label": "Уменьшить", "description": "Уменьшить бюджет на указанный процент"}
        ],
        "change_percent_limits": {
            "min": 1,
            "max": 20,
            "description": "Процент изменения бюджета (от 1% до 20%)"
        }
    }


@router.get("/logs")
async def get_budget_change_logs(
    rule_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get budget change logs"""
    logs, total = crud.get_budget_change_logs(db, current_user.id, rule_id, limit, offset)

    return {
        "items": [
            {
                "id": log.id,
                "rule_id": log.rule_id,
                "rule_name": log.rule_name,
                "account_name": log.account_name,
                "ad_group_id": log.ad_group_id,
                "ad_group_name": log.ad_group_name,
                "banner_id": log.banner_id,
                "banner_name": log.banner_name,
                "old_budget": log.old_budget,
                "new_budget": log.new_budget,
                "change_percent": log.change_percent,
                "change_direction": log.change_direction,
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


@router.get("/for-account/{account_id}")
async def get_budget_rules_for_account(
    account_id: int,
    enabled_only: bool = True,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get all budget rules that apply to a specific account"""
    rules = crud.get_budget_rules_for_account(db, account_id, enabled_only=enabled_only)

    result = []
    for rule in rules:
        conditions = [
            {
                "id": c.id,
                "metric": c.metric,
                "operator": c.operator,
                "value": c.value,
                "order": c.order
            }
            for c in rule.conditions
        ]

        result.append({
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "change_percent": rule.change_percent,
            "change_direction": rule.change_direction,
            "conditions": conditions
        })

    return {"items": result, "total": len(result)}


@router.get("/summary")
async def get_budget_rules_summary(
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get summary of budget rules and recent activity"""
    rules = crud.get_budget_rules(db, user_id=current_user.id)
    enabled_count = sum(1 for r in rules if r.enabled)

    logs, total_logs = crud.get_budget_change_logs(db, current_user.id, limit=10)

    # Count successful changes in last 24 hours
    from utils.time_utils import get_moscow_time
    now = get_moscow_time()
    recent_logs, _ = crud.get_budget_change_logs(db, current_user.id, limit=1000)
    changes_24h = sum(1 for log in recent_logs
                      if log.success and
                      not log.is_dry_run and
                      (now - log.created_at).total_seconds() < 86400)

    return {
        "total_rules": len(rules),
        "enabled_rules": enabled_count,
        "changes_24h": changes_24h,
        "total_logs": total_logs,
        "recent_logs": [
            {
                "id": log.id,
                "rule_name": log.rule_name,
                "ad_group_id": log.ad_group_id,
                "ad_group_name": log.ad_group_name,
                "account_name": log.account_name,
                "change_percent": log.change_percent,
                "change_direction": log.change_direction,
                "success": log.success,
                "is_dry_run": log.is_dry_run,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
    }


# ===== Tasks =====

@router.get("/tasks")
async def get_budget_rule_tasks(
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get active and recent budget rule tasks"""
    active_tasks = crud.get_active_budget_rule_tasks(db, user_id=current_user.id)
    recent_tasks = crud.get_recent_budget_rule_tasks(db, user_id=current_user.id, limit=5)
    
    def task_to_dict(task):
        progress = 0
        if task.total_accounts > 0:
            progress = int((task.completed_accounts / task.total_accounts) * 100)
        
        return {
            "id": task.id,
            "task_type": task.task_type,
            "rule_id": task.rule_id,
            "rule_name": task.rule_name,
            "account_name": task.account_name,
            "status": task.status,
            "total_accounts": task.total_accounts,
            "completed_accounts": task.completed_accounts,
            "total_changes": task.total_changes,
            "successful_changes": task.successful_changes,
            "failed_changes": task.failed_changes,
            "current_account": task.current_account,
            "current_step": task.current_step,
            "last_error": task.last_error,
            "progress": progress,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
    
    return {
        "active": [task_to_dict(t) for t in active_tasks],
        "recent": [task_to_dict(t) for t in recent_tasks if t.status not in ['pending', 'running']]
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_budget_rule_task(
    task_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Cancel a running budget rule task"""
    task = crud.get_budget_rule_task(db, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status not in ['pending', 'running']:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    
    crud.cancel_budget_rule_task(db, task_id)
    return {"message": "Task cancelled"}


# ===== Single Rule Operations (path parameter routes MUST be last) =====

@router.get("/{rule_id}")
async def get_budget_rule(
    rule_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get a specific budget rule by ID"""
    rule = crud.get_budget_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    return _format_rule_response(rule, db)


@router.post("")
async def create_budget_rule(
    data: BudgetRuleCreate,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Create a new budget rule for current user"""
    try:
        rule = crud.create_budget_rule(
            db,
            user_id=current_user.id,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            priority=data.priority,
            schedule_time=data.schedule_time,
            scheduled_enabled=data.scheduled_enabled,
            change_percent=data.change_percent,
            change_direction=data.change_direction,
            lookback_days=data.lookback_days,
            roi_sub_field=data.roi_sub_field
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if data.conditions:
        conditions_data = [c.model_dump() for c in data.conditions]
        crud.replace_budget_rule_conditions(db, rule.id, conditions_data)

    if data.account_ids:
        crud.replace_budget_rule_accounts(db, rule.id, data.account_ids, user_id=current_user.id)

    return _format_rule_response(rule, db)


@router.put("/{rule_id}")
async def update_budget_rule(
    rule_id: int,
    data: BudgetRuleUpdate,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Update an existing budget rule for current user"""
    rule = crud.get_budget_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    try:
        crud.update_budget_rule(
            db,
            rule_id,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            priority=data.priority,
            schedule_time=data.schedule_time,
            scheduled_enabled=data.scheduled_enabled,
            change_percent=data.change_percent,
            change_direction=data.change_direction,
            lookback_days=data.lookback_days,
            roi_sub_field=data.roi_sub_field
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if data.conditions is not None:
        conditions_data = [c.model_dump() for c in data.conditions]
        crud.replace_budget_rule_conditions(db, rule_id, conditions_data)

    if data.account_ids is not None:
        crud.replace_budget_rule_accounts(db, rule_id, data.account_ids, user_id=current_user.id)

    rule = crud.get_budget_rule_by_id(db, rule_id)
    return _format_rule_response(rule, db)


@router.delete("/{rule_id}")
async def delete_budget_rule(
    rule_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Delete a budget rule"""
    if not crud.delete_budget_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")

    return {"message": "Rule deleted successfully"}


# ===== Manual Run =====

async def _run_budget_rule_task(task_id: int, rule_id: int, user_id: int, dry_run: bool = False):
    """Background task to run a budget rule manually with tracking"""
    import aiohttp
    from database import SessionLocal
    from core.budget_changer import process_budget_rules_for_account
    from utils.logging_setup import get_logger
    
    logger = get_logger(service="api", function="budget_rules")
    
    db = SessionLocal()
    try:
        rule = crud.get_budget_rule_by_id(db, rule_id)
        if not rule:
            logger.error(f"Budget rule {rule_id} not found")
            crud.complete_budget_rule_task(db, task_id, status='failed')
            return
        
        # Start task
        crud.start_budget_rule_task(db, task_id)
        
        # Get accounts for this rule
        accounts = crud.get_budget_rule_accounts(db, rule_id)
        if not accounts:
            logger.warning(f"No accounts configured for budget rule {rule_id}")
            crud.complete_budget_rule_task(db, task_id, status='failed')
            return
        
        # Update total accounts
        crud.update_budget_rule_task_progress(db, task_id, current_step="initializing")
        
        # Get whitelist (returns List[int] of banner IDs)
        whitelist = set(crud.get_whitelist(db, user_id=user_id))
        
        logger.info(f"Starting manual run of budget rule '{rule.name}' (ID: {rule_id})")
        logger.info(f"Accounts: {[a.name for a in accounts]}")
        logger.info(f"Dry run: {dry_run}")
        
        base_url = "https://ads.vk.com/api/v2"
        
        total_changes = 0
        successful_changes = 0
        failed_changes = 0
        completed_accounts = 0
        
        async with aiohttp.ClientSession() as session:
            for i, account in enumerate(accounts):
                # Check if task was cancelled
                task_check = crud.get_budget_rule_task(db, task_id)
                if task_check and task_check.status == 'cancelled':
                    logger.warning(f"Task {task_id} was cancelled")
                    break
                
                crud.update_budget_rule_task_progress(
                    db, task_id,
                    current_account=account.name,
                    current_step="analyzing"
                )
                
                try:
                    result = await process_budget_rules_for_account(
                        session=session,
                        account_name=account.name,
                        access_token=account.api_token,
                        base_url=base_url,
                        user_id=user_id,
                        dry_run=dry_run,
                        whitelist=whitelist,
                        specific_rule_id=rule_id  # Pass specific rule for manual runs
                    )
                    
                    changes = result.get('total_changes', 0)
                    success = result.get('successful', 0)
                    failed = result.get('failed', 0)
                    
                    total_changes += changes
                    successful_changes += success
                    failed_changes += failed
                    completed_accounts += 1
                    
                    crud.update_budget_rule_task_progress(
                        db, task_id,
                        completed_accounts=completed_accounts,
                        total_changes=total_changes,
                        successful_changes=successful_changes,
                        failed_changes=failed_changes
                    )
                    
                    logger.info(f"Processed {account.name}: {changes} changes")
                except Exception as e:
                    logger.error(f"Error processing account {account.name}: {e}")
                    failed_changes += 1
                    completed_accounts += 1
                    crud.update_budget_rule_task_progress(
                        db, task_id,
                        completed_accounts=completed_accounts,
                        failed_changes=failed_changes,
                        last_error=str(e)
                    )
        
        # Update last_run_at
        crud.update_budget_rule_last_run(db, rule_id)
        
        # Complete task
        final_status = 'completed' if failed_changes == 0 else ('failed' if successful_changes == 0 else 'completed')
        crud.complete_budget_rule_task(db, task_id, status=final_status)
        
        logger.info(f"Budget rule '{rule.name}' run completed: {successful_changes} success, {failed_changes} failed")
        
    except Exception as e:
        logger.error(f"Error in budget rule task: {e}")
        crud.update_budget_rule_task_progress(db, task_id, last_error=str(e))
        crud.complete_budget_rule_task(db, task_id, status='failed')
    finally:
        db.close()


@router.post("/run/{rule_id}")
async def run_budget_rule(
    rule_id: int,
    dry_run: bool = False,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Manually run a budget rule (execute now)"""
    rule = crud.get_budget_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    if rule.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get accounts for response
    accounts = crud.get_budget_rule_accounts(db, rule_id)
    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts configured for this rule")
    
    # Create task for tracking
    account_names = ", ".join([a.name for a in accounts])
    task = crud.create_budget_rule_task(
        db,
        user_id=current_user.id,
        task_type='manual',
        rule_id=rule_id,
        rule_name=rule.name,
        account_name=account_names[:255] if len(account_names) > 255 else account_names,
        total_accounts=len(accounts)
    )
    
    # Run in background with task tracking
    background_tasks.add_task(_run_budget_rule_task, task.id, rule_id, current_user.id, dry_run)
    
    return {
        "message": f"Budget rule '{rule.name}' started",
        "task_id": task.id,
        "rule_id": rule_id,
        "accounts_count": len(accounts),
        "dry_run": dry_run
    }
