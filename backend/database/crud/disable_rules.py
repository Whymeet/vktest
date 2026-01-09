"""
CRUD operations for Disable Rules (auto-disable banners)
Includes: DisableRule, DisableRuleCondition, DisableRuleAccount
"""
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from utils.time_utils import get_moscow_time
from database.models import DisableRule, DisableRuleCondition, DisableRuleAccount, Account


# ===== Disable Rules =====

def get_disable_rules(db: Session, user_id: int = None, enabled_only: bool = False) -> List[DisableRule]:
    """Get all disable rules, optionally filtered by user_id and enabled status"""
    query = db.query(DisableRule).options(
        joinedload(DisableRule.conditions)
    )
    if user_id is not None:
        query = query.filter(DisableRule.user_id == user_id)
    if enabled_only:
        query = query.filter(DisableRule.enabled == True)
    return query.order_by(desc(DisableRule.priority), DisableRule.id).all()


def get_disable_rule_by_id(db: Session, rule_id: int) -> Optional[DisableRule]:
    """Get a specific disable rule by ID"""
    return db.query(DisableRule).filter(DisableRule.id == rule_id).first()


def create_disable_rule(
    db: Session,
    user_id: int,
    name: str,
    description: Optional[str] = None,
    enabled: bool = True,
    priority: int = 0,
    roi_sub_field: Optional[str] = None
) -> DisableRule:
    """Create a new disable rule for user"""
    rule = DisableRule(
        user_id=user_id,
        name=name,
        description=description,
        enabled=enabled,
        priority=priority,
        roi_sub_field=roi_sub_field
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_disable_rule(
    db: Session,
    rule_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
    priority: Optional[int] = None,
    roi_sub_field: Optional[str] = None
) -> Optional[DisableRule]:
    """Update an existing disable rule"""
    rule = get_disable_rule_by_id(db, rule_id)
    if not rule:
        return None

    if name is not None:
        rule.name = name
    if description is not None:
        rule.description = description
    if enabled is not None:
        rule.enabled = enabled
    if priority is not None:
        rule.priority = priority
    if roi_sub_field is not None:
        rule.roi_sub_field = roi_sub_field

    rule.updated_at = get_moscow_time()
    db.commit()
    db.refresh(rule)
    return rule


def delete_disable_rule(db: Session, rule_id: int) -> bool:
    """Delete a disable rule and all its conditions/accounts"""
    rule = get_disable_rule_by_id(db, rule_id)
    if not rule:
        return False

    db.delete(rule)
    db.commit()
    return True


# ===== Disable Rule Conditions =====

def get_rule_conditions(db: Session, rule_id: int) -> List[DisableRuleCondition]:
    """Get all conditions for a specific rule"""
    return db.query(DisableRuleCondition).filter(
        DisableRuleCondition.rule_id == rule_id
    ).order_by(DisableRuleCondition.order).all()


def add_rule_condition(
    db: Session,
    rule_id: int,
    metric: str,
    operator: str,
    value: float,
    order: int = 0
) -> DisableRuleCondition:
    """Add a condition to a disable rule"""
    condition = DisableRuleCondition(
        rule_id=rule_id,
        metric=metric,
        operator=operator,
        value=value,
        order=order
    )
    db.add(condition)
    db.commit()
    db.refresh(condition)
    return condition


def update_rule_condition(
    db: Session,
    condition_id: int,
    metric: Optional[str] = None,
    operator: Optional[str] = None,
    value: Optional[float] = None,
    order: Optional[int] = None
) -> Optional[DisableRuleCondition]:
    """Update an existing condition"""
    condition = db.query(DisableRuleCondition).filter(
        DisableRuleCondition.id == condition_id
    ).first()
    if not condition:
        return None

    if metric is not None:
        condition.metric = metric
    if operator is not None:
        condition.operator = operator
    if value is not None:
        condition.value = value
    if order is not None:
        condition.order = order

    db.commit()
    db.refresh(condition)
    return condition


def delete_rule_condition(db: Session, condition_id: int) -> bool:
    """Delete a condition from a rule"""
    condition = db.query(DisableRuleCondition).filter(
        DisableRuleCondition.id == condition_id
    ).first()
    if not condition:
        return False

    db.delete(condition)
    db.commit()
    return True


def replace_rule_conditions(
    db: Session,
    rule_id: int,
    conditions: List[dict]
) -> List[DisableRuleCondition]:
    """Replace all conditions for a rule"""
    # Delete existing conditions
    db.query(DisableRuleCondition).filter(
        DisableRuleCondition.rule_id == rule_id
    ).delete()

    # Add new conditions
    new_conditions = []
    for i, cond in enumerate(conditions):
        condition = DisableRuleCondition(
            rule_id=rule_id,
            metric=cond['metric'],
            operator=cond['operator'],
            value=cond['value'],
            order=cond.get('order', i)
        )
        db.add(condition)
        new_conditions.append(condition)

    db.commit()
    for cond in new_conditions:
        db.refresh(cond)

    return new_conditions


# ===== Disable Rule Accounts =====

def get_rule_accounts(db: Session, rule_id: int) -> List[Account]:
    """Get all accounts linked to a specific rule"""
    links = db.query(DisableRuleAccount).filter(
        DisableRuleAccount.rule_id == rule_id
    ).all()

    account_ids = [link.account_id for link in links]
    if not account_ids:
        return []

    return db.query(Account).filter(Account.id.in_(account_ids)).all()


def get_rule_account_ids(db: Session, rule_id: int) -> List[int]:
    """Get account IDs linked to a specific rule"""
    links = db.query(DisableRuleAccount).filter(
        DisableRuleAccount.rule_id == rule_id
    ).all()
    return [link.account_id for link in links]


def add_rule_account(db: Session, rule_id: int, account_id: int) -> DisableRuleAccount:
    """Link an account to a rule"""
    # Check if already exists
    existing = db.query(DisableRuleAccount).filter(
        DisableRuleAccount.rule_id == rule_id,
        DisableRuleAccount.account_id == account_id
    ).first()
    if existing:
        return existing

    link = DisableRuleAccount(rule_id=rule_id, account_id=account_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def remove_rule_account(db: Session, rule_id: int, account_id: int) -> bool:
    """Unlink an account from a rule"""
    link = db.query(DisableRuleAccount).filter(
        DisableRuleAccount.rule_id == rule_id,
        DisableRuleAccount.account_id == account_id
    ).first()
    if not link:
        return False

    db.delete(link)
    db.commit()
    return True


def replace_rule_accounts(db: Session, rule_id: int, account_ids: List[int], user_id: int = None) -> List[int]:
    """Replace all account links for a rule"""
    # Delete existing links
    db.query(DisableRuleAccount).filter(
        DisableRuleAccount.rule_id == rule_id
    ).delete()

    # Add new links
    for account_id in account_ids:
        link = DisableRuleAccount(rule_id=rule_id, account_id=account_id, user_id=user_id)
        db.add(link)

    db.commit()
    return account_ids


def get_rules_for_account(db: Session, account_id: int, enabled_only: bool = True) -> List[DisableRule]:
    """Get all rules that apply to a specific account (by account table id)"""
    links = db.query(DisableRuleAccount).filter(
        DisableRuleAccount.account_id == account_id
    ).all()

    rule_ids = [link.rule_id for link in links]
    if not rule_ids:
        return []

    query = db.query(DisableRule).options(
        joinedload(DisableRule.conditions)
    ).filter(DisableRule.id.in_(rule_ids))
    if enabled_only:
        query = query.filter(DisableRule.enabled == True)

    return query.order_by(desc(DisableRule.priority), DisableRule.id).all()


def get_rules_for_account_by_vk_id(db: Session, vk_account_id: int, enabled_only: bool = True) -> List[DisableRule]:
    """Get all rules that apply to a specific VK account ID"""
    account = db.query(Account).filter(Account.account_id == vk_account_id).first()
    if not account:
        return []

    return get_rules_for_account(db, account.id, enabled_only)


def get_rules_for_account_by_name(db: Session, account_name: str, enabled_only: bool = True) -> List[DisableRule]:
    """Get all rules that apply to a specific account by name"""
    account = db.query(Account).filter(Account.name == account_name).first()
    if not account:
        return []

    return get_rules_for_account(db, account.id, enabled_only)


# ===== Check Banner Against Rules =====

def check_banner_against_rules(
    stats: dict,
    rules: List[DisableRule],
    roi_data: Optional[dict] = None
) -> Optional[DisableRule]:
    """
    Check if banner stats match any disable rule.
    Returns the first matching rule (highest priority first), or None.

    Args:
        stats: Dict with keys: goals, spent, clicks, shows, ctr, cpc, cost_per_goal
        rules: List of DisableRule objects (should be pre-filtered for account)
        roi_data: Optional dict mapping banner_id -> BannerROIData for ROI metric

    Returns:
        The first matching DisableRule, or None if no rules match
    """
    banner_id = stats.get("id") or stats.get("banner_id")

    for rule in rules:
        if not rule.enabled:
            continue

        conditions = rule.conditions
        if not conditions:
            continue  # Skip rules without conditions

        all_conditions_met = True

        for condition in conditions:
            metric = condition.metric
            operator = condition.operator
            threshold = condition.value

            # Get metric value from stats
            actual_value = stats.get(metric)

            # Handle None and special cases
            if actual_value is None:
                if metric == "cost_per_goal":
                    # If no goals, cost_per_goal is infinite
                    goals = stats.get("goals", 0) or stats.get("vk_goals", 0)
                    if goals == 0:
                        actual_value = float('inf')
                    else:
                        spent = stats.get("spent", 0) or 0
                        actual_value = spent / goals if goals > 0 else float('inf')
                elif metric == "ctr":
                    shows = stats.get("shows", 0) or 0
                    clicks = stats.get("clicks", 0) or 0
                    actual_value = (clicks / shows * 100) if shows > 0 else 0
                elif metric == "cpc":
                    clicks = stats.get("clicks", 0) or 0
                    spent = stats.get("spent", 0) or 0
                    actual_value = (spent / clicks) if clicks > 0 else float('inf')
                elif metric == "roi":
                    # Get ROI from roi_data if available
                    if roi_data and banner_id:
                        roi_info = roi_data.get(banner_id)
                        if roi_info:
                            actual_value = roi_info.roi_percent if hasattr(roi_info, 'roi_percent') else roi_info.get('roi_percent')
                            if actual_value is None:
                                actual_value = 0.0  # No spent = ROI 0
                        else:
                            # No LeadsTech data - check if banner has spending
                            spent = stats.get("spent", 0) or 0
                            if spent > 0:
                                # Есть траты, но нет дохода в LeadsTech = очень плохой ROI
                                actual_value = -100000000.0
                            else:
                                actual_value = 0.0  # No spent, no LeadsTech = ROI 0
                    else:
                        # No ROI data available - check if banner has spending
                        spent = stats.get("spent", 0) or 0
                        if spent > 0:
                            # Есть траты, но нет ROI данных = очень плохой ROI
                            actual_value = -100000000.0
                        else:
                            actual_value = 0.0  # No spent = ROI 0
                else:
                    actual_value = 0

            # Normalize goals field name
            if metric == "goals" and actual_value == 0:
                actual_value = stats.get("vk_goals", 0) or 0

            # Check condition based on operator
            condition_met = False

            # FIX: Если CPA = бесконечности (0 целей), игнорируем правила "CPA > X"
            # Это нужно, чтобы не отключать объявления с 0 целей по правилу высокой стоимости,
            # так как для 0 целей обычно есть отдельные правила (Goals = 0).
            if metric == "cost_per_goal" and actual_value == float('inf'):
                if operator in ("not_equals", "!="):
                    condition_met = True
                else:
                    condition_met = False
            elif operator in ("equals", "=", "=="):
                condition_met = (actual_value == threshold)
            elif operator in ("not_equals", "!=", "<>"):
                condition_met = (actual_value != threshold)
            elif operator in ("greater_than", ">"):
                condition_met = (actual_value > threshold)
            elif operator in ("less_than", "<"):
                condition_met = (actual_value < threshold)
            elif operator in ("greater_or_equal", ">="):
                condition_met = (actual_value >= threshold)
            elif operator in ("less_or_equal", "<="):
                condition_met = (actual_value <= threshold)
            else:
                # Unknown operator - FAIL the condition (don't skip!)
                # This prevents rules from matching when operators are broken
                condition_met = False

            if not condition_met:
                all_conditions_met = False
                break

        if all_conditions_met:
            return rule  # First matching rule wins

    return None


def format_rule_match_reason(rule: DisableRule, stats: dict, roi_data: Optional[dict] = None) -> str:
    """
    Format a human-readable reason for why a banner matched a rule.

    Args:
        rule: The matched DisableRule
        stats: Banner statistics
        roi_data: Optional dict mapping banner_id -> BannerROIData for ROI metric

    Returns:
        Human-readable string explaining the match
    """
    metric_names = {
        "goals": "результатов",
        "spent": "потрачено",
        "clicks": "кликов",
        "shows": "показов",
        "ctr": "CTR",
        "cpc": "цена клика",
        "cost_per_goal": "цена результата",
        "roi": "ROI"
    }

    operator_names = {
        "equals": "=",
        "not_equals": "≠",
        "greater_than": ">",
        "less_than": "<",
        "greater_or_equal": "≥",
        "less_or_equal": "≤"
    }

    parts = [f"Правило \"{rule.name}\":"]
    banner_id = stats.get("id") or stats.get("banner_id")

    for condition in rule.conditions:
        metric_name = metric_names.get(condition.metric, condition.metric)
        op_name = operator_names.get(condition.operator, condition.operator)

        # Get actual value
        actual = stats.get(condition.metric)
        if actual is None:
            if condition.metric == "goals":
                actual = stats.get("vk_goals", 0)
            elif condition.metric == "cost_per_goal":
                goals = stats.get("goals", 0) or stats.get("vk_goals", 0)
                spent = stats.get("spent", 0) or 0
                actual = (spent / goals) if goals > 0 else "∞"
            elif condition.metric == "roi":
                if roi_data and banner_id:
                    roi_info = roi_data.get(banner_id)
                    if roi_info:
                        actual = roi_info.roi_percent if hasattr(roi_info, 'roi_percent') else roi_info.get('roi_percent')
                        if actual is None:
                            actual = 0.0
                    else:
                        actual = 0.0
                else:
                    actual = 0.0
            else:
                actual = 0

        if isinstance(actual, float) and actual != float('inf'):
            actual = f"{actual:.2f}"

        parts.append(f"  {metric_name} {op_name} {condition.value} (факт: {actual})")

    return "\n".join(parts)