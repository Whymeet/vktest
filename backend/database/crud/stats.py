"""
CRUD operations for Statistics and Process State
Includes: DailyAccountStats, ProcessState
"""
from typing import List, Optional
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from utils.time_utils import get_moscow_time
from database.models import DailyAccountStats, ProcessState


# ===== Process State =====

def get_process_state(db: Session, name: str) -> Optional[ProcessState]:
    """Get process state by name"""
    return db.query(ProcessState).filter(ProcessState.name == name).first()


def get_all_process_states(db: Session) -> List[ProcessState]:
    """Get all process states"""
    return db.query(ProcessState).all()


def get_autostart_process_states(db: Session, process_type: str = None) -> List[ProcessState]:
    """Get all process states with auto_start=True, optionally filtered by process type"""
    query = db.query(ProcessState).filter(ProcessState.auto_start == True)
    if process_type:
        # Filter by process type (e.g., 'scheduler' matches 'scheduler_1', 'scheduler_2')
        query = query.filter(ProcessState.name.like(f"{process_type}%"))
    return query.all()


def set_process_running(
    db: Session,
    name: str,
    pid: int,
    script_path: Optional[str] = None,
    user_id: Optional[int] = None,
    auto_start: bool = False
) -> ProcessState:
    """Mark process as running with PID"""
    state = get_process_state(db, name)
    now = get_moscow_time()

    if state:
        state.pid = pid
        state.script_path = script_path
        state.status = 'running'
        state.started_at = now
        state.stopped_at = None
        state.last_error = None
        state.updated_at = now
        state.auto_start = auto_start
        if user_id:
            state.user_id = user_id
    else:
        state = ProcessState(
            name=name,
            pid=pid,
            script_path=script_path,
            status='running',
            started_at=now,
            user_id=user_id,
            auto_start=auto_start
        )
        db.add(state)

    db.commit()
    db.refresh(state)
    return state


def set_process_stopped(db: Session, name: str, error: Optional[str] = None, disable_autostart: bool = True) -> Optional[ProcessState]:
    """Mark process as stopped

    Args:
        db: Database session
        name: Process name
        error: Optional error message
        disable_autostart: If True, sets auto_start=False (user manually stopped).
                          If False, keeps auto_start unchanged (server restart/crash).
    """
    state = get_process_state(db, name)
    if not state:
        return None

    now = get_moscow_time()
    state.pid = None
    state.status = 'crashed' if error else 'stopped'
    state.stopped_at = now
    state.last_error = error
    state.updated_at = now

    # Only disable auto_start if explicitly requested (user clicked Stop)
    if disable_autostart:
        state.auto_start = False

    db.commit()
    db.refresh(state)
    return state


def update_process_status(db: Session, name: str, status: str) -> Optional[ProcessState]:
    """Update process status"""
    state = get_process_state(db, name)
    if not state:
        return None

    state.status = status
    state.updated_at = get_moscow_time()

    db.commit()
    db.refresh(state)
    return state


def clear_all_process_states(db: Session) -> int:
    """Clear all process states (on startup if needed)"""
    count = db.query(ProcessState).delete()
    db.commit()
    return count


# ===== Daily Account Stats =====

def save_account_stats(
    db: Session,
    account_name: str,
    stats_date: str,
    active_banners: int = 0,
    disabled_banners: int = 0,
    over_limit_banners: int = 0,
    under_limit_banners: int = 0,
    no_activity_banners: int = 0,
    total_spend: float = 0.0,
    total_clicks: int = 0,
    total_shows: int = 0,
    total_conversions: int = 0,
    spent_limit: Optional[float] = None,
    lookback_days: Optional[int] = None,
    vk_account_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> DailyAccountStats:
    """Save daily account statistics"""
    stats = DailyAccountStats(
        user_id=user_id,
        account_name=account_name,
        vk_account_id=vk_account_id,
        stats_date=stats_date,
        active_banners=active_banners,
        disabled_banners=disabled_banners,
        over_limit_banners=over_limit_banners,
        under_limit_banners=under_limit_banners,
        no_activity_banners=no_activity_banners,
        total_spend=total_spend,
        total_clicks=total_clicks,
        total_shows=total_shows,
        total_conversions=total_conversions,
        spent_limit=spent_limit,
        lookback_days=lookback_days
    )
    db.add(stats)
    db.commit()
    db.refresh(stats)
    return stats


def get_account_stats(
    db: Session,
    account_name: Optional[str] = None,
    stats_date: Optional[str] = None,
    limit: int = 100
) -> List[DailyAccountStats]:
    """Get account statistics with optional filters"""
    query = db.query(DailyAccountStats)

    if account_name:
        query = query.filter(DailyAccountStats.account_name == account_name)
    if stats_date:
        query = query.filter(DailyAccountStats.stats_date == stats_date)

    return query.order_by(desc(DailyAccountStats.created_at)).limit(limit).all()


def get_today_stats(db: Session, account_name: Optional[str] = None) -> List[DailyAccountStats]:
    """Get today's statistics for all or specific account"""
    today = get_moscow_time().strftime('%Y-%m-%d')
    return get_account_stats(db, account_name=account_name, stats_date=today, limit=100)


def get_stats_by_date_range(
    db: Session,
    date_from: str,
    date_to: str,
    account_name: Optional[str] = None
) -> List[DailyAccountStats]:
    """Get statistics for date range"""
    query = db.query(DailyAccountStats).filter(
        and_(
            DailyAccountStats.stats_date >= date_from,
            DailyAccountStats.stats_date <= date_to
        )
    )

    if account_name:
        query = query.filter(DailyAccountStats.account_name == account_name)

    return query.order_by(desc(DailyAccountStats.stats_date), desc(DailyAccountStats.created_at)).all()


def get_account_stats_summary(db: Session, days: int = 7) -> dict:
    """Get aggregated summary for last N days"""
    end_date = get_moscow_time().date()
    start_date = end_date - timedelta(days=days)

    stats = get_stats_by_date_range(
        db,
        date_from=start_date.isoformat(),
        date_to=end_date.isoformat()
    )

    accounts_summary = {}
    for s in stats:
        if s.account_name not in accounts_summary:
            accounts_summary[s.account_name] = {
                'account_name': s.account_name,
                'total_spend': 0,
                'total_disabled': 0,
                'total_active': 0,
                'runs': 0
            }
        accounts_summary[s.account_name]['total_spend'] += s.total_spend or 0
        accounts_summary[s.account_name]['total_disabled'] += s.disabled_banners or 0
        accounts_summary[s.account_name]['total_active'] = max(
            accounts_summary[s.account_name]['total_active'],
            s.active_banners or 0
        )
        accounts_summary[s.account_name]['runs'] += 1

    return {
        'period_days': days,
        'date_from': start_date.isoformat(),
        'date_to': end_date.isoformat(),
        'accounts': list(accounts_summary.values()),
        'total_runs': len(stats)
    }
