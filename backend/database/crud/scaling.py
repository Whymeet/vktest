"""
CRUD operations for Auto-Scaling system
Includes: ScalingConfig, ScalingCondition, ScalingLog, ScalingTask, ManualScalingGroup
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from utils.time_utils import get_moscow_time
from database.models import (
    ScalingConfig, ScalingCondition, ScalingLog, ScalingTask,
    ScalingConfigAccount, ManualScalingGroup
)


# ===== Scaling Configs =====

def get_scaling_configs(db: Session, user_id: int) -> List[ScalingConfig]:
    """Get all scaling configurations for a user"""
    return db.query(ScalingConfig).filter(ScalingConfig.user_id == user_id).order_by(ScalingConfig.created_at.desc()).all()


def get_scaling_config_by_id(db: Session, config_id: int) -> Optional[ScalingConfig]:
    """Get scaling configuration by ID"""
    return db.query(ScalingConfig).filter(ScalingConfig.id == config_id).first()


def get_enabled_scaling_configs(db: Session, user_id: Optional[int] = None) -> List[ScalingConfig]:
    """Get all scaling configurations with scheduled_enabled=True, optionally filtered by user_id"""
    query = db.query(ScalingConfig).filter(ScalingConfig.scheduled_enabled == True)
    if user_id is not None:
        query = query.filter(ScalingConfig.user_id == user_id)
    return query.all()


def get_scaling_config_account_ids(db: Session, config_id: int) -> List[int]:
    """Get list of account IDs linked to a scaling config"""
    links = db.query(ScalingConfigAccount).filter(
        ScalingConfigAccount.config_id == config_id
    ).all()
    return [link.account_id for link in links]


def set_scaling_config_accounts(db: Session, config_id: int, account_ids: List[int]) -> None:
    """Set accounts for a scaling config (replaces existing links)"""
    # Get config to retrieve user_id
    config = get_scaling_config_by_id(db, config_id)
    if not config:
        return

    # Delete existing links
    db.query(ScalingConfigAccount).filter(
        ScalingConfigAccount.config_id == config_id
    ).delete()

    # Create new links
    for account_id in account_ids:
        link = ScalingConfigAccount(
            user_id=config.user_id,
            config_id=config_id,
            account_id=account_id
        )
        db.add(link)

    db.commit()


# ===== Manual Scaling Groups =====

def get_manual_scaling_groups(db: Session, config_id: int) -> List[int]:
    """Get VK ad_group_id list for manual scaling config"""
    groups = db.query(ManualScalingGroup).filter(
        ManualScalingGroup.config_id == config_id
    ).all()
    return [g.vk_ad_group_id for g in groups]


def set_manual_scaling_groups(db: Session, config_id: int, vk_group_ids: List[int], user_id: int) -> None:
    """Set VK ad_group_id list for manual scaling config (replaces existing)"""
    # Delete existing
    db.query(ManualScalingGroup).filter(
        ManualScalingGroup.config_id == config_id
    ).delete()

    # Add new
    for gid in vk_group_ids:
        db.add(ManualScalingGroup(
            user_id=user_id,
            config_id=config_id,
            vk_ad_group_id=gid
        ))

    db.commit()


def create_scaling_config(
    db: Session,
    user_id: int,
    name: str,
    schedule_time: str = "08:00",
    scheduled_enabled: bool = True,
    account_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    new_budget: Optional[float] = None,
    new_name: Optional[str] = None,
    auto_activate: bool = False,
    lookback_days: int = 7,
    duplicates_count: int = 1,
    enabled: bool = False,
    vk_ad_group_ids: Optional[List[int]] = None,
    use_leadstech_roi: bool = False,
    # New banner-level scaling options
    activate_positive_banners: bool = True,
    duplicate_negative_banners: bool = True,
    activate_negative_banners: bool = False
) -> ScalingConfig:
    """Create new scaling configuration

    Args:
        scheduled_enabled: TRUE = run by schedule, FALSE = manual only
        new_name: New name for duplicated groups (NULL = use original name)
        vk_ad_group_ids: List of VK ad_group_id for manual scaling
        use_leadstech_roi: Enable LeadsTech ROI for conditions
        activate_positive_banners: Activate positive banners (status=active)
        duplicate_negative_banners: Duplicate negative banners in group
        activate_negative_banners: Activate negative banners (status=active)
    """
    config = ScalingConfig(
        user_id=user_id,
        name=name,
        schedule_time=schedule_time,
        scheduled_enabled=scheduled_enabled,
        account_id=account_id,
        new_budget=new_budget,
        new_name=new_name if new_name and new_name.strip() else None,
        auto_activate=auto_activate,
        lookback_days=lookback_days,
        duplicates_count=duplicates_count,
        enabled=enabled,
        use_leadstech_roi=use_leadstech_roi,
        activate_positive_banners=activate_positive_banners,
        duplicate_negative_banners=duplicate_negative_banners,
        activate_negative_banners=activate_negative_banners
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    # Set account links if provided
    if account_ids:
        set_scaling_config_accounts(db, config.id, account_ids)

    # Set manual scaling groups if provided
    if vk_ad_group_ids:
        set_manual_scaling_groups(db, config.id, vk_ad_group_ids, user_id)

    return config


def update_scaling_config(
    db: Session,
    config_id: int,
    name: Optional[str] = None,
    schedule_time: Optional[str] = None,
    scheduled_enabled: Optional[bool] = None,
    account_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    new_budget: Optional[float] = None,
    new_name: Optional[str] = None,
    auto_activate: Optional[bool] = None,
    lookback_days: Optional[int] = None,
    duplicates_count: Optional[int] = None,
    enabled: Optional[bool] = None,
    vk_ad_group_ids: Optional[List[int]] = None,
    use_leadstech_roi: Optional[bool] = None,
    # New banner-level scaling options
    activate_positive_banners: Optional[bool] = None,
    duplicate_negative_banners: Optional[bool] = None,
    activate_negative_banners: Optional[bool] = None
) -> Optional[ScalingConfig]:
    """Update scaling configuration

    Args:
        scheduled_enabled: TRUE = run by schedule, FALSE = manual only
        new_name: New name for duplicated groups (empty string or NULL = use original name)
        vk_ad_group_ids: List of VK ad_group_id for manual scaling
        use_leadstech_roi: Enable LeadsTech ROI for conditions
        activate_positive_banners: Activate positive banners (status=active)
        duplicate_negative_banners: Duplicate negative banners in group
        activate_negative_banners: Activate negative banners (status=active)
    """
    config = get_scaling_config_by_id(db, config_id)
    if not config:
        return None

    if name is not None:
        config.name = name
    if schedule_time is not None:
        config.schedule_time = schedule_time
    if scheduled_enabled is not None:
        config.scheduled_enabled = scheduled_enabled
    if account_id is not None:
        config.account_id = account_id if account_id > 0 else None
    if new_budget is not None:
        config.new_budget = new_budget if new_budget > 0 else None
    if new_name is not None:
        # Empty string means "use original name" (set to NULL)
        config.new_name = new_name.strip() if new_name.strip() else None
    if auto_activate is not None:
        config.auto_activate = auto_activate
    if lookback_days is not None:
        config.lookback_days = lookback_days
    if duplicates_count is not None:
        config.duplicates_count = max(1, min(100, duplicates_count))  # 1-100
    if enabled is not None:
        config.enabled = enabled
    if use_leadstech_roi is not None:
        config.use_leadstech_roi = use_leadstech_roi
    if activate_positive_banners is not None:
        config.activate_positive_banners = activate_positive_banners
    if duplicate_negative_banners is not None:
        config.duplicate_negative_banners = duplicate_negative_banners
    if activate_negative_banners is not None:
        config.activate_negative_banners = activate_negative_banners

    config.updated_at = get_moscow_time()
    db.commit()
    db.refresh(config)

    # Update account links if provided
    if account_ids is not None:
        set_scaling_config_accounts(db, config_id, account_ids)

    # Update manual scaling groups if provided
    if vk_ad_group_ids is not None:
        set_manual_scaling_groups(db, config_id, vk_ad_group_ids, config.user_id)

    return config


def delete_scaling_config(db: Session, config_id: int) -> bool:
    """Delete scaling configuration"""
    config = get_scaling_config_by_id(db, config_id)
    if not config:
        return False

    db.delete(config)
    db.commit()
    return True


def update_scaling_config_last_run(db: Session, config_id: int) -> None:
    """Update last run time of scaling config"""
    config = get_scaling_config_by_id(db, config_id)
    if config:
        config.last_run_at = get_moscow_time()
        db.commit()


# ===== Scaling Conditions =====

def get_scaling_conditions(db: Session, config_id: int) -> List[ScalingCondition]:
    """Get all conditions for a scaling config"""
    return db.query(ScalingCondition).filter(
        ScalingCondition.config_id == config_id
    ).order_by(ScalingCondition.order).all()


def create_scaling_condition(
    db: Session,
    config_id: int,
    metric: str,
    operator: str,
    value: float,
    order: int = 0
) -> ScalingCondition:
    """Create new scaling condition"""
    condition = ScalingCondition(
        config_id=config_id,
        metric=metric,
        operator=operator,
        value=value,
        order=order
    )
    db.add(condition)
    db.commit()
    db.refresh(condition)
    return condition


def update_scaling_condition(
    db: Session,
    condition_id: int,
    metric: Optional[str] = None,
    operator: Optional[str] = None,
    value: Optional[float] = None,
    order: Optional[int] = None
) -> Optional[ScalingCondition]:
    """Update scaling condition"""
    condition = db.query(ScalingCondition).filter(ScalingCondition.id == condition_id).first()
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


def delete_scaling_condition(db: Session, condition_id: int) -> bool:
    """Delete scaling condition"""
    condition = db.query(ScalingCondition).filter(ScalingCondition.id == condition_id).first()
    if not condition:
        return False

    db.delete(condition)
    db.commit()
    return True


def delete_all_scaling_conditions(db: Session, config_id: int) -> int:
    """Delete all conditions for a scaling config"""
    count = db.query(ScalingCondition).filter(
        ScalingCondition.config_id == config_id
    ).delete()
    if count > 0:
        db.commit()
    return count


def set_scaling_conditions(
    db: Session,
    config_id: int,
    conditions: List[dict]
) -> List[ScalingCondition]:
    """Replace all conditions for a config with new ones"""
    try:
        # Delete existing conditions (only if there are any)
        existing_count = db.query(ScalingCondition).filter(
            ScalingCondition.config_id == config_id
        ).count()
        if existing_count > 0:
            delete_all_scaling_conditions(db, config_id)

        # If no conditions to add, return empty list
        if not conditions:
            return []

        # Create new conditions (batch create for better performance)
        result = []
        for i, cond in enumerate(conditions):
            # Ensure value is float
            value = cond.get("value", 0)
            if isinstance(value, (int, str)):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = 0.0

            # Get operator, default to ">" if not provided
            operator = cond.get("operator", ">")

            condition = ScalingCondition(
                config_id=config_id,
                metric=cond.get("metric", "goals"),
                operator=operator,
                value=value,
                order=i
            )
            db.add(condition)
            result.append(condition)

        # Commit all conditions at once
        db.commit()

        # Refresh all conditions to get IDs
        for condition in result:
            db.refresh(condition)

        return result
    except Exception as e:
        print(f"❌ Error setting scaling conditions: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise


# ===== Scaling Logs =====

def get_scaling_logs(
    db: Session,
    user_id: int,
    config_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple[List[ScalingLog], int]:
    """Get scaling logs with pagination"""
    query = db.query(ScalingLog).filter(ScalingLog.user_id == user_id)

    if config_id:
        query = query.filter(ScalingLog.config_id == config_id)

    total = query.count()
    items = query.order_by(ScalingLog.created_at.desc()).offset(offset).limit(limit).all()

    return items, total


def create_scaling_log(
    db: Session,
    user_id: int,
    config_id: Optional[int],
    config_name: Optional[str],
    account_name: Optional[str],
    original_group_id: int,
    original_group_name: Optional[str],
    new_group_id: Optional[int] = None,
    new_group_name: Optional[str] = None,
    requested_name: Optional[str] = None,
    stats_snapshot: Optional[dict] = None,
    success: bool = False,
    error_message: Optional[str] = None,
    total_banners: int = 0,
    duplicated_banners: int = 0,
    duplicated_banner_ids: Optional[list] = None
) -> ScalingLog:
    """Create new scaling log entry

    Args:
        requested_name: Requested name from config (NULL = used original name)
    """
    log = ScalingLog(
        user_id=user_id,
        config_id=config_id,
        config_name=config_name,
        account_name=account_name,
        original_group_id=original_group_id,
        original_group_name=original_group_name,
        new_group_id=new_group_id,
        new_group_name=new_group_name,
        requested_name=requested_name,
        stats_snapshot=stats_snapshot,
        success=success,
        error_message=error_message,
        total_banners=total_banners,
        duplicated_banners=duplicated_banners,
        duplicated_banner_ids=duplicated_banner_ids
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def check_group_conditions(stats: dict, conditions: List[ScalingCondition], logger=None) -> bool:
    """
    Check if ad group stats match all conditions.
    Uses the same logic as check_banner_against_rules for consistency.

    Args:
        stats: Dict with keys: spent, shows, clicks, goals, cost_per_goal, ctr, cpc, roi
        conditions: List of ScalingCondition objects
        logger: Optional logger object with info() method

    Returns:
        True if ALL conditions are satisfied
    """
    def log(msg):
        if logger:
            logger.info(msg)
        else:
            print(msg)

    if not conditions:
        log(f"         ⚠️  Нет условий для проверки")
        return False  # No conditions = don't match anything

    for idx, condition in enumerate(conditions):
        metric = condition.metric
        operator = condition.operator
        threshold = condition.value

        # Get metric value from stats
        actual_value = stats.get(metric)
        log(f"         [{idx+1}] Проверяем: {metric} {operator} {threshold} (начальное значение: {actual_value})")

        # Handle None and special cases (same logic as check_banner_against_rules)
        if actual_value is None:
            if metric == "cost_per_goal":
                # If no goals, cost_per_goal is infinite
                goals = stats.get("goals", 0) or stats.get("vk_goals", 0)
                if goals == 0:
                    actual_value = float('inf')
                    log(f"            → cost_per_goal = ∞ (нет целей)")
                else:
                    spent = stats.get("spent", 0) or 0
                    actual_value = spent / goals if goals > 0 else float('inf')
                    log(f"            → cost_per_goal = {actual_value:.2f} (spent={spent}, goals={goals})")
            elif metric == "ctr":
                shows = stats.get("shows", 0) or 0
                clicks = stats.get("clicks", 0) or 0
                actual_value = (clicks / shows * 100) if shows > 0 else 0
                log(f"            → ctr = {actual_value:.2f}% (clicks={clicks}, shows={shows})")
            elif metric == "cpc":
                clicks = stats.get("clicks", 0) or 0
                spent = stats.get("spent", 0) or 0
                actual_value = (spent / clicks) if clicks > 0 else float('inf')
                log(f"            → cpc = {actual_value:.2f} (spent={spent}, clicks={clicks})")
            elif metric == "roi":
                # ROI from LeadsTech - None means no data available
                log(f"            → roi = нет данных LeadsTech для этой группы")
                return False  # Skip group if no ROI data when ROI condition is used
            else:
                actual_value = 0
                log(f"            → значение отсутствует, используем 0")

        # Normalize goals field name
        if metric == "goals" and actual_value == 0:
            vk_goals = stats.get("vk_goals", 0) or 0
            if vk_goals > 0:
                actual_value = vk_goals
                log(f"            → используем vk_goals = {actual_value}")

        # Check condition based on operator (same syntax as disable rules)
        condition_met = False

        # FIX: If cost_per_goal is infinite (0 goals), handle specially
        if metric == "cost_per_goal" and actual_value == float('inf'):
            if operator in ("not_equals", "!="):
                condition_met = True
            else:
                condition_met = False
            log(f"            → cost_per_goal=∞: условие {'✓ выполнено' if condition_met else '✗ НЕ выполнено'}")
        elif operator in ("equals", "=", "=="):
            condition_met = (actual_value == threshold)
            log(f"            → {actual_value} == {threshold} = {condition_met}")
        elif operator in ("not_equals", "!=", "<>"):
            condition_met = (actual_value != threshold)
            log(f"            → {actual_value} != {threshold} = {condition_met}")
        elif operator in ("greater_than", ">"):
            condition_met = (actual_value > threshold)
            log(f"            → {actual_value} > {threshold} = {condition_met}")
        elif operator in ("less_than", "<"):
            condition_met = (actual_value < threshold)
            log(f"            → {actual_value} < {threshold} = {condition_met}")
        elif operator in ("greater_or_equal", ">="):
            condition_met = (actual_value >= threshold)
            log(f"            → {actual_value} >= {threshold} = {condition_met}")
        elif operator in ("less_or_equal", "<="):
            condition_met = (actual_value <= threshold)
            log(f"            → {actual_value} <= {threshold} = {condition_met}")
        else:
            # Unknown operator - FAIL the condition
            condition_met = False
            log(f"            → ⚠️  НЕИЗВЕСТНЫЙ ОПЕРАТОР '{operator}'")

        if not condition_met:
            log(f"            ✗ Условие НЕ выполнено, пропускаем группу")
            return False
        else:
            log(f"            ✓ Условие выполнено")

    log(f"         ✅ ВСЕ условия выполнены!")
    return True


# ===== Scaling Tasks =====

def create_scaling_task(
    db: Session,
    user_id: int,
    task_type: str = 'manual',
    config_id: Optional[int] = None,
    config_name: Optional[str] = None,
    account_name: Optional[str] = None,
    total_operations: int = 0
) -> ScalingTask:
    """Create a new scaling task"""
    task = ScalingTask(
        user_id=user_id,
        task_type=task_type,
        config_id=config_id,
        config_name=config_name,
        account_name=account_name,
        status='pending',
        total_operations=total_operations,
        completed_operations=0,
        successful_operations=0,
        failed_operations=0
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_scaling_task(db: Session, task_id: int) -> Optional[ScalingTask]:
    """Get scaling task by ID"""
    return db.query(ScalingTask).filter(ScalingTask.id == task_id).first()


def get_active_scaling_tasks(db: Session, user_id: int) -> List[ScalingTask]:
    """Get all active (pending/running) scaling tasks for a user"""
    return db.query(ScalingTask).filter(
        ScalingTask.user_id == user_id,
        ScalingTask.status.in_(['pending', 'running'])
    ).order_by(ScalingTask.created_at.desc()).all()


def get_recent_scaling_tasks(db: Session, user_id: int, limit: int = 10) -> List[ScalingTask]:
    """Get recent scaling tasks for a user"""
    return db.query(ScalingTask).filter(
        ScalingTask.user_id == user_id
    ).order_by(ScalingTask.created_at.desc()).limit(limit).all()


def start_scaling_task(db: Session, task_id: int) -> Optional[ScalingTask]:
    """Mark task as running"""
    task = get_scaling_task(db, task_id)
    if not task:
        return None

    task.status = 'running'
    task.started_at = get_moscow_time()
    db.commit()
    db.refresh(task)
    return task


def update_scaling_task_progress(
    db: Session,
    task_id: int,
    completed: int = None,
    successful: int = None,
    failed: int = None,
    current_group_id: int = None,
    current_group_name: str = None,
    last_error: str = None
) -> Optional[ScalingTask]:
    """Update task progress"""
    task = get_scaling_task(db, task_id)
    if not task:
        return None

    if completed is not None:
        task.completed_operations = completed
    if successful is not None:
        task.successful_operations = successful
    if failed is not None:
        task.failed_operations = failed
    if current_group_id is not None:
        task.current_group_id = current_group_id
    if current_group_name is not None:
        task.current_group_name = current_group_name
    if last_error is not None:
        task.last_error = last_error

    db.commit()
    db.refresh(task)
    return task


def complete_scaling_task(
    db: Session,
    task_id: int,
    status: str = 'completed',
    last_error: str = None
) -> Optional[ScalingTask]:
    """Mark task as completed/failed"""
    task = get_scaling_task(db, task_id)
    if not task:
        return None

    task.status = status
    task.completed_at = get_moscow_time()
    task.current_group_id = None
    task.current_group_name = None
    if last_error:
        task.last_error = last_error

    db.commit()
    db.refresh(task)
    return task


def cancel_scaling_task(db: Session, task_id: int) -> Optional[ScalingTask]:
    """Cancel a pending/running task"""
    task = get_scaling_task(db, task_id)
    if not task:
        return None

    if task.status in ['pending', 'running']:
        task.status = 'cancelled'
        task.completed_at = get_moscow_time()
        db.commit()
        db.refresh(task)

    return task


def cleanup_old_scaling_tasks(db: Session, max_age_hours: int = 24) -> int:
    """Remove old completed/failed tasks"""
    from datetime import timedelta
    cutoff = get_moscow_time() - timedelta(hours=max_age_hours)

    count = db.query(ScalingTask).filter(
        ScalingTask.status.in_(['completed', 'failed', 'cancelled']),
        ScalingTask.completed_at < cutoff
    ).delete()

    db.commit()
    return count
