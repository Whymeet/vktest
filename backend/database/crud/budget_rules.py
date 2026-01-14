"""
CRUD operations for Budget Rules (auto-change ad group budgets)
Includes: BudgetRule, BudgetRuleCondition, BudgetRuleAccount, BudgetChangeLog
"""
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from utils.time_utils import get_moscow_time
from database.models import BudgetRule, BudgetRuleCondition, BudgetRuleAccount, BudgetChangeLog, BudgetRuleTask, Account


# ===== Budget Rules =====

def get_budget_rules(db: Session, user_id: int = None, enabled_only: bool = False) -> List[BudgetRule]:
    """Get all budget rules, optionally filtered by user_id and enabled status"""
    query = db.query(BudgetRule).options(
        joinedload(BudgetRule.conditions)
    )
    if user_id is not None:
        query = query.filter(BudgetRule.user_id == user_id)
    if enabled_only:
        query = query.filter(BudgetRule.enabled == True)
    return query.order_by(desc(BudgetRule.priority), BudgetRule.id).all()


def get_budget_rule_by_id(db: Session, rule_id: int) -> Optional[BudgetRule]:
    """Get a specific budget rule by ID with conditions eagerly loaded"""
    return db.query(BudgetRule).options(
        joinedload(BudgetRule.conditions)
    ).filter(BudgetRule.id == rule_id).first()


def create_budget_rule(
    db: Session,
    user_id: int,
    name: str,
    change_percent: float,
    change_direction: str,
    description: Optional[str] = None,
    enabled: bool = True,
    priority: int = 0,
    schedule_time: Optional[str] = None,
    scheduled_enabled: bool = False,
    roi_sub_field: Optional[str] = None,
    lookback_days: int = 7
) -> BudgetRule:
    """Create a new budget rule for user"""
    # Validate change_percent (1-20%)
    if change_percent < 1 or change_percent > 20:
        raise ValueError("change_percent must be between 1 and 20")
    
    # Validate change_direction
    if change_direction not in ("increase", "decrease"):
        raise ValueError("change_direction must be 'increase' or 'decrease'")
    
    rule = BudgetRule(
        user_id=user_id,
        name=name,
        description=description,
        enabled=enabled,
        priority=priority,
        schedule_time=schedule_time,
        scheduled_enabled=scheduled_enabled,
        change_percent=change_percent,
        change_direction=change_direction,
        roi_sub_field=roi_sub_field,
        lookback_days=lookback_days
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_budget_rule(
    db: Session,
    rule_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
    priority: Optional[int] = None,
    schedule_time: Optional[str] = None,
    scheduled_enabled: Optional[bool] = None,
    change_percent: Optional[float] = None,
    change_direction: Optional[str] = None,
    roi_sub_field: Optional[str] = None,
    lookback_days: Optional[int] = None
) -> Optional[BudgetRule]:
    """Update an existing budget rule"""
    rule = get_budget_rule_by_id(db, rule_id)
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
    if schedule_time is not None:
        rule.schedule_time = schedule_time
    if scheduled_enabled is not None:
        rule.scheduled_enabled = scheduled_enabled
    if change_percent is not None:
        if change_percent < 1 or change_percent > 20:
            raise ValueError("change_percent must be between 1 and 20")
        rule.change_percent = change_percent
    if change_direction is not None:
        if change_direction not in ("increase", "decrease"):
            raise ValueError("change_direction must be 'increase' or 'decrease'")
        rule.change_direction = change_direction
    if roi_sub_field is not None:
        rule.roi_sub_field = roi_sub_field
    if lookback_days is not None:
        rule.lookback_days = lookback_days

    rule.updated_at = get_moscow_time()
    db.commit()
    db.refresh(rule)
    return rule


def update_budget_rule_last_run(db: Session, rule_id: int) -> Optional[BudgetRule]:
    """Update the last_run_at timestamp for a budget rule"""
    rule = get_budget_rule_by_id(db, rule_id)
    if not rule:
        return None
    rule.last_run_at = get_moscow_time()
    db.commit()
    db.refresh(rule)
    return rule


def get_scheduled_budget_rules(db: Session, user_id: Optional[int] = None) -> List[BudgetRule]:
    """Get all budget rules with scheduling enabled"""
    query = db.query(BudgetRule).options(
        joinedload(BudgetRule.conditions)
    ).filter(
        BudgetRule.enabled == True,
        BudgetRule.scheduled_enabled == True,
        BudgetRule.schedule_time != None
    )
    if user_id is not None:
        query = query.filter(BudgetRule.user_id == user_id)
    return query.order_by(desc(BudgetRule.priority), BudgetRule.id).all()


def delete_budget_rule(db: Session, rule_id: int) -> bool:
    """Delete a budget rule and all its conditions/accounts"""
    rule = get_budget_rule_by_id(db, rule_id)
    if not rule:
        return False

    db.delete(rule)
    db.commit()
    return True


# ===== Budget Rule Conditions =====

def get_budget_rule_conditions(db: Session, rule_id: int) -> List[BudgetRuleCondition]:
    """Get all conditions for a specific rule"""
    return db.query(BudgetRuleCondition).filter(
        BudgetRuleCondition.rule_id == rule_id
    ).order_by(BudgetRuleCondition.order).all()


def add_budget_rule_condition(
    db: Session,
    rule_id: int,
    metric: str,
    operator: str,
    value: float,
    order: int = 0
) -> BudgetRuleCondition:
    """Add a condition to a budget rule"""
    condition = BudgetRuleCondition(
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


def replace_budget_rule_conditions(
    db: Session,
    rule_id: int,
    conditions: List[dict]
) -> List[BudgetRuleCondition]:
    """Replace all conditions for a rule"""
    # Delete existing conditions
    db.query(BudgetRuleCondition).filter(
        BudgetRuleCondition.rule_id == rule_id
    ).delete()

    # Add new conditions
    new_conditions = []
    for i, cond in enumerate(conditions):
        condition = BudgetRuleCondition(
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


# ===== Budget Rule Accounts =====

def get_budget_rule_accounts(db: Session, rule_id: int) -> List[Account]:
    """Get all accounts linked to a specific rule"""
    links = db.query(BudgetRuleAccount).filter(
        BudgetRuleAccount.rule_id == rule_id
    ).all()

    account_ids = [link.account_id for link in links]
    if not account_ids:
        return []

    return db.query(Account).filter(Account.id.in_(account_ids)).all()


def get_budget_rule_account_ids(db: Session, rule_id: int) -> List[int]:
    """Get account IDs linked to a specific rule"""
    links = db.query(BudgetRuleAccount).filter(
        BudgetRuleAccount.rule_id == rule_id
    ).all()
    return [link.account_id for link in links]


def replace_budget_rule_accounts(db: Session, rule_id: int, account_ids: List[int], user_id: int = None) -> List[int]:
    """Replace all account links for a rule"""
    # Delete existing links
    db.query(BudgetRuleAccount).filter(
        BudgetRuleAccount.rule_id == rule_id
    ).delete()

    # Add new links
    for account_id in account_ids:
        link = BudgetRuleAccount(rule_id=rule_id, account_id=account_id, user_id=user_id)
        db.add(link)

    db.commit()
    return account_ids


def get_budget_rules_for_account(db: Session, account_id: int, enabled_only: bool = True) -> List[BudgetRule]:
    """Get all budget rules that apply to a specific account (by account table id)"""
    from utils.logging_setup import get_logger
    logger = get_logger(service="crud", function="budget_rules")
    
    links = db.query(BudgetRuleAccount).filter(
        BudgetRuleAccount.account_id == account_id
    ).all()
    
    logger.debug(f"get_budget_rules_for_account: account_id={account_id}, found {len(links)} links")

    rule_ids = [link.rule_id for link in links]
    if not rule_ids:
        logger.debug(f"get_budget_rules_for_account: no rule links found for account_id={account_id}")
        return []

    query = db.query(BudgetRule).options(
        joinedload(BudgetRule.conditions)
    ).filter(BudgetRule.id.in_(rule_ids))
    if enabled_only:
        query = query.filter(BudgetRule.enabled == True)

    rules = query.order_by(desc(BudgetRule.priority), BudgetRule.id).all()
    logger.debug(f"get_budget_rules_for_account: found {len(rules)} rules (enabled_only={enabled_only})")
    return rules


def get_budget_rules_for_account_by_name(db: Session, account_name: str, user_id: int = None, enabled_only: bool = True) -> List[BudgetRule]:
    """Get all budget rules that apply to a specific account by name"""
    query = db.query(Account).filter(Account.name == account_name)
    if user_id:
        query = query.filter(Account.user_id == user_id)
    account = query.first()
    if not account:
        return []

    return get_budget_rules_for_account(db, account.id, enabled_only)


# ===== Check Banner Against Budget Rules =====

def check_banner_against_budget_rules(
    stats: dict,
    rules: List[BudgetRule],
    roi_data: Optional[dict] = None
) -> Optional[BudgetRule]:
    """
    Check if banner stats match any budget rule.
    Returns the first matching rule (highest priority first), or None.

    Args:
        stats: Dict with keys: goals, spent, clicks, shows, ctr, cpc, cost_per_goal
        rules: List of BudgetRule objects (should be pre-filtered for account)
        roi_data: Optional dict mapping banner_id -> BannerROIData for ROI metric

    Returns:
        The first matching BudgetRule, or None if no rules match
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
                elif metric == "cr":
                    clicks = stats.get("clicks", 0) or 0
                    goals = stats.get("goals", 0) or stats.get("vk_goals", 0)
                    actual_value = (goals / clicks * 100) if clicks > 0 else 0
                elif metric == "roi":
                    if roi_data and banner_id:
                        roi_info = roi_data.get(banner_id)
                        if roi_info:
                            actual_value = roi_info.roi_percent if hasattr(roi_info, 'roi_percent') else roi_info.get('roi_percent')
                            if actual_value is None:
                                actual_value = 0.0
                        else:
                            spent = stats.get("spent", 0) or 0
                            if spent > 0:
                                actual_value = -100000000.0
                            else:
                                actual_value = 0.0
                    else:
                        spent = stats.get("spent", 0) or 0
                        if spent > 0:
                            actual_value = -100000000.0
                        else:
                            actual_value = 0.0
                else:
                    actual_value = 0

            # Normalize goals field name
            if metric == "goals" and actual_value == 0:
                actual_value = stats.get("vk_goals", 0) or 0

            # Check condition based on operator
            condition_met = False

            # Handle infinite CPA specially
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
                condition_met = False

            if not condition_met:
                all_conditions_met = False
                break

        if all_conditions_met:
            return rule

    return None


def format_budget_rule_match_reason(rule: BudgetRule, stats: dict, roi_data: Optional[dict] = None) -> str:
    """
    Format a human-readable reason for why a banner matched a budget rule.
    """
    metric_names = {
        "goals": "результатов",
        "spent": "потрачено",
        "clicks": "кликов",
        "shows": "показов",
        "ctr": "CTR",
        "cpc": "цена клика",
        "cr": "CR",
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

    direction_names = {
        "increase": "увеличить",
        "decrease": "уменьшить"
    }

    parts = [f"Правило \"{rule.name}\": {direction_names.get(rule.change_direction, rule.change_direction)} бюджет на {rule.change_percent}%"]
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


# ===== Budget Change Logs =====

def create_budget_change_log(
    db: Session,
    user_id: int,
    ad_group_id: int,
    change_percent: float,
    change_direction: str,
    rule_id: Optional[int] = None,
    rule_name: Optional[str] = None,
    account_name: Optional[str] = None,
    vk_account_id: Optional[int] = None,
    ad_group_name: Optional[str] = None,
    banner_id: Optional[int] = None,
    banner_name: Optional[str] = None,
    old_budget: Optional[float] = None,
    new_budget: Optional[float] = None,
    stats_snapshot: Optional[dict] = None,
    success: bool = False,
    error_message: Optional[str] = None,
    is_dry_run: bool = False,
    lookback_days: Optional[int] = None,
    analysis_date_from: Optional[str] = None,
    analysis_date_to: Optional[str] = None
) -> BudgetChangeLog:
    """Create a log entry for budget change"""
    log = BudgetChangeLog(
        user_id=user_id,
        rule_id=rule_id,
        rule_name=rule_name,
        account_name=account_name,
        vk_account_id=vk_account_id,
        ad_group_id=ad_group_id,
        ad_group_name=ad_group_name,
        banner_id=banner_id,
        banner_name=banner_name,
        old_budget=old_budget,
        new_budget=new_budget,
        change_percent=change_percent,
        change_direction=change_direction,
        stats_snapshot=stats_snapshot,
        success=success,
        error_message=error_message,
        is_dry_run=is_dry_run,
        lookback_days=lookback_days,
        analysis_date_from=analysis_date_from,
        analysis_date_to=analysis_date_to
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_budget_change_logs(
    db: Session,
    user_id: int,
    rule_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[BudgetChangeLog], int]:
    """Get budget change logs for user"""
    query = db.query(BudgetChangeLog).filter(BudgetChangeLog.user_id == user_id)
    
    if rule_id is not None:
        query = query.filter(BudgetChangeLog.rule_id == rule_id)
    
    total = query.count()
    logs = query.order_by(desc(BudgetChangeLog.created_at)).offset(offset).limit(limit).all()
    
    return logs, total


# ===== Budget Rule Tasks =====

def create_budget_rule_task(
    db: Session,
    user_id: int,
    task_type: str = 'manual',
    rule_id: Optional[int] = None,
    rule_name: Optional[str] = None,
    account_name: Optional[str] = None,
    total_accounts: int = 0
) -> BudgetRuleTask:
    """Create a new budget rule task for tracking"""
    task = BudgetRuleTask(
        user_id=user_id,
        task_type=task_type,
        rule_id=rule_id,
        rule_name=rule_name,
        account_name=account_name,
        status='pending',
        total_accounts=total_accounts,
        completed_accounts=0,
        total_changes=0,
        successful_changes=0,
        failed_changes=0
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_budget_rule_task(db: Session, task_id: int) -> Optional[BudgetRuleTask]:
    """Get a specific task by ID"""
    return db.query(BudgetRuleTask).filter(BudgetRuleTask.id == task_id).first()


def start_budget_rule_task(db: Session, task_id: int) -> Optional[BudgetRuleTask]:
    """Mark task as running"""
    task = get_budget_rule_task(db, task_id)
    if task:
        task.status = 'running'
        task.started_at = get_moscow_time()
        db.commit()
        db.refresh(task)
    return task


def update_budget_rule_task_progress(
    db: Session,
    task_id: int,
    completed_accounts: Optional[int] = None,
    total_changes: Optional[int] = None,
    successful_changes: Optional[int] = None,
    failed_changes: Optional[int] = None,
    current_account: Optional[str] = None,
    current_step: Optional[str] = None,
    last_error: Optional[str] = None
) -> Optional[BudgetRuleTask]:
    """Update task progress"""
    task = get_budget_rule_task(db, task_id)
    if not task:
        return None
    
    if completed_accounts is not None:
        task.completed_accounts = completed_accounts
    if total_changes is not None:
        task.total_changes = total_changes
    if successful_changes is not None:
        task.successful_changes = successful_changes
    if failed_changes is not None:
        task.failed_changes = failed_changes
    if current_account is not None:
        task.current_account = current_account
    if current_step is not None:
        task.current_step = current_step
    if last_error is not None:
        task.last_error = last_error
    
    db.commit()
    db.refresh(task)
    return task


def complete_budget_rule_task(db: Session, task_id: int, status: str = 'completed') -> Optional[BudgetRuleTask]:
    """Mark task as completed/failed"""
    task = get_budget_rule_task(db, task_id)
    if task:
        task.status = status
        task.completed_at = get_moscow_time()
        task.current_step = None
        db.commit()
        db.refresh(task)
    return task


def cancel_budget_rule_task(db: Session, task_id: int) -> Optional[BudgetRuleTask]:
    """Cancel a running task"""
    return complete_budget_rule_task(db, task_id, status='cancelled')


def get_active_budget_rule_tasks(db: Session, user_id: int) -> List[BudgetRuleTask]:
    """Get all active (pending/running) tasks for user"""
    return db.query(BudgetRuleTask).filter(
        BudgetRuleTask.user_id == user_id,
        BudgetRuleTask.status.in_(['pending', 'running'])
    ).order_by(desc(BudgetRuleTask.created_at)).all()


def get_recent_budget_rule_tasks(db: Session, user_id: int, limit: int = 5) -> List[BudgetRuleTask]:
    """Get recent tasks (last N completed/failed)"""
    return db.query(BudgetRuleTask).filter(
        BudgetRuleTask.user_id == user_id
    ).order_by(desc(BudgetRuleTask.created_at)).limit(limit).all()
