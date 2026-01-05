"""
Disable Rules management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import require_feature
from api.schemas.disable_rules import DisableRuleCreate, DisableRuleUpdate

router = APIRouter(prefix="/api/disable-rules", tags=["Disable Rules"])


def _format_rule_response(rule, db) -> dict:
    """Format disable rule with conditions and accounts"""
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

    account_ids = crud.get_rule_account_ids(db, rule.id)
    accounts = crud.get_rule_accounts(db, rule.id)
    account_names = [acc.name for acc in accounts]

    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "roi_sub_field": rule.roi_sub_field,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "conditions": conditions,
        "account_ids": account_ids,
        "account_names": account_names
    }


@router.get("")
async def get_disable_rules(
    enabled_only: bool = False,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get all disable rules with their conditions and linked accounts for current user"""
    rules = crud.get_disable_rules(db, user_id=current_user.id, enabled_only=enabled_only)

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

        account_ids = crud.get_rule_account_ids(db, rule.id)
        accounts = crud.get_rule_accounts(db, rule.id)
        account_names = [acc.name for acc in accounts]

        result.append({
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "roi_sub_field": rule.roi_sub_field,
            "created_at": rule.created_at.isoformat(),
            "updated_at": rule.updated_at.isoformat(),
            "conditions": conditions,
            "account_ids": account_ids,
            "account_names": account_names
        })

    return {"items": result, "total": len(result)}


@router.get("/metrics")
async def get_disable_rule_metrics(
    current_user: User = Depends(require_feature("auto_disable"))
):
    """Get available metrics and operators for disable rules"""
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
            {"value": "roi", "label": "ROI (%)", "description": "Return on Investment ((доход - затраты) / затраты * 100). Если дохода нет или объявление не в Leadstech - ROI = 0"}
        ],
        "operators": [
            {"value": "equals", "label": "=", "description": "Равно"},
            {"value": "not_equals", "label": "≠", "description": "Не равно"},
            {"value": "greater_than", "label": ">", "description": "Больше"},
            {"value": "less_than", "label": "<", "description": "Меньше"},
            {"value": "greater_or_equal", "label": "≥", "description": "Больше или равно"},
            {"value": "less_or_equal", "label": "≤", "description": "Меньше или равно"}
        ]
    }


@router.get("/for-account/{account_id}")
async def get_rules_for_account(
    account_id: int,
    enabled_only: bool = True,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get all disable rules that apply to a specific account"""
    rules = crud.get_rules_for_account(db, account_id, enabled_only=enabled_only)

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
            "conditions": conditions
        })

    return {"items": result, "total": len(result)}


@router.get("/{rule_id}")
async def get_disable_rule(
    rule_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get a specific disable rule by ID"""
    rule = crud.get_disable_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    return _format_rule_response(rule, db)


@router.post("")
async def create_disable_rule(
    data: DisableRuleCreate,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Create a new disable rule for current user"""
    rule = crud.create_disable_rule(
        db,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        priority=data.priority,
        roi_sub_field=data.roi_sub_field
    )

    if data.conditions:
        conditions_data = [c.model_dump() for c in data.conditions]
        crud.replace_rule_conditions(db, rule.id, conditions_data)

    if data.account_ids:
        crud.replace_rule_accounts(db, rule.id, data.account_ids, user_id=current_user.id)

    return _format_rule_response(rule, db)


@router.put("/{rule_id}")
async def update_disable_rule(
    rule_id: int,
    data: DisableRuleUpdate,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Update an existing disable rule for current user"""
    rule = crud.get_disable_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    crud.update_disable_rule(
        db,
        rule_id,
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        priority=data.priority,
        roi_sub_field=data.roi_sub_field
    )

    if data.conditions is not None:
        conditions_data = [c.model_dump() for c in data.conditions]
        crud.replace_rule_conditions(db, rule_id, conditions_data)

    if data.account_ids is not None:
        crud.replace_rule_accounts(db, rule_id, data.account_ids, user_id=current_user.id)

    rule = crud.get_disable_rule_by_id(db, rule_id)
    return _format_rule_response(rule, db)


@router.delete("/{rule_id}")
async def delete_disable_rule(
    rule_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Delete a disable rule"""
    if not crud.delete_disable_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")

    return {"message": "Rule deleted successfully"}
