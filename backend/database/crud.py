"""
CRUD operations for database models
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from utils.time_utils import get_moscow_time

from .models import (
    Account,
    WhitelistBanner,
    BannerAction,
    ActiveBanner,
    Settings,
    ProcessState,
    DailyAccountStats,
    LeadsTechConfig,
    LeadsTechCabinet,
    LeadsTechAnalysisResult,
)


# ===== Accounts =====

def get_accounts(db: Session) -> List[Account]:
    """Get all accounts"""
    return db.query(Account).all()


def get_account_by_id(db: Session, account_id: int) -> Optional[Account]:
    """Get account by VK account ID"""
    return db.query(Account).filter(Account.account_id == account_id).first()


def create_account(
    db: Session,
    account_id: int,
    name: str,
    api_token: str,
    client_id: int
) -> Account:
    """Create new account"""
    db_account = Account(
        account_id=account_id,
        name=name,
        api_token=api_token,
        client_id=client_id
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def update_account(
    db: Session,
    account_id: int,
    name: Optional[str] = None,
    api_token: Optional[str] = None,
    client_id: Optional[int] = None
) -> Optional[Account]:
    """Update account"""
    account = get_account_by_id(db, account_id)
    if not account:
        return None

    if name is not None:
        account.name = name
    if api_token is not None:
        account.api_token = api_token
    if client_id is not None:
        account.client_id = client_id

    account.updated_at = get_moscow_time()
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, account_id: int) -> bool:
    """Delete account"""
    account = get_account_by_id(db, account_id)
    if not account:
        return False

    db.delete(account)
    db.commit()
    return True


# ===== Whitelist =====

def get_whitelist(db: Session) -> List[int]:
    """Get all whitelisted banner IDs"""
    banners = db.query(WhitelistBanner).all()
    return [b.banner_id for b in banners]


def add_to_whitelist(db: Session, banner_id: int, note: Optional[str] = None) -> WhitelistBanner:
    """Add banner to whitelist"""
    # Check if already exists
    existing = db.query(WhitelistBanner).filter(WhitelistBanner.banner_id == banner_id).first()
    if existing:
        return existing

    db_banner = WhitelistBanner(banner_id=banner_id, note=note)
    db.add(db_banner)
    db.commit()
    db.refresh(db_banner)
    return db_banner


def remove_from_whitelist(db: Session, banner_id: int) -> bool:
    """Remove banner from whitelist"""
    banner = db.query(WhitelistBanner).filter(WhitelistBanner.banner_id == banner_id).first()
    if not banner:
        return False

    db.delete(banner)
    db.commit()
    return True


def is_whitelisted(db: Session, banner_id: int) -> bool:
    """Check if banner is whitelisted"""
    return db.query(WhitelistBanner).filter(WhitelistBanner.banner_id == banner_id).first() is not None


def replace_whitelist(db: Session, banner_ids: List[int]) -> List[int]:
    """Replace entire whitelist"""
    # Delete all existing
    db.query(WhitelistBanner).delete()

    # Add new ones
    for banner_id in banner_ids:
        db.add(WhitelistBanner(banner_id=banner_id))

    db.commit()
    return banner_ids


# ===== Banner Actions (History) =====

def create_banner_action(
    db: Session,
    banner_id: int,
    action: str,  # 'disabled' or 'enabled'
    # Account info
    account_name: Optional[str] = None,
    vk_account_id: Optional[int] = None,
    # Banner info
    banner_name: Optional[str] = None,
    ad_group_id: Optional[int] = None,
    ad_group_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
    campaign_name: Optional[str] = None,
    # Status info
    banner_status: Optional[str] = None,
    delivery_status: Optional[str] = None,
    moderation_status: Optional[str] = None,
    # Financial data
    spend: Optional[float] = None,
    clicks: int = 0,
    shows: int = 0,
    ctr: Optional[float] = None,
    cpc: Optional[float] = None,
    # Conversions
    conversions: int = 0,
    cost_per_conversion: Optional[float] = None,
    # Analysis info
    spent_limit: Optional[float] = None,
    lookback_days: Optional[int] = None,
    analysis_date_from: Optional[str] = None,
    analysis_date_to: Optional[str] = None,
    # Other
    reason: Optional[str] = None,
    stats: Optional[dict] = None,
    is_dry_run: bool = False
) -> BannerAction:
    """Log a banner action (enable/disable) with full details"""
    # Try to get account DB ID if vk_account_id provided
    account_db_id = None
    if vk_account_id:
        account = get_account_by_id(db, vk_account_id)
        if account:
            account_db_id = account.id

    db_action = BannerAction(
        banner_id=banner_id,
        banner_name=banner_name,
        ad_group_id=ad_group_id,
        ad_group_name=ad_group_name,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        account_id=account_db_id,
        vk_account_id=vk_account_id,
        account_name=account_name,
        action=action,
        reason=reason,
        stats=stats,
        spend=spend,
        clicks=clicks,
        shows=shows,
        ctr=ctr,
        cpc=cpc,
        conversions=conversions,
        cost_per_conversion=cost_per_conversion,
        banner_status=banner_status,
        delivery_status=delivery_status,
        moderation_status=moderation_status,
        spent_limit=spent_limit,
        lookback_days=lookback_days,
        analysis_date_from=analysis_date_from,
        analysis_date_to=analysis_date_to,
        is_dry_run=is_dry_run
    )
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    return db_action


def log_disabled_banner(
    db: Session,
    banner_data: dict,
    account_name: str,
    spent_limit: float,
    lookback_days: int,
    date_from: str,
    date_to: str,
    is_dry_run: bool = False,
    disable_success: bool = True
) -> BannerAction:
    """
    Удобная функция для логирования отключённого баннера.
    banner_data - словарь с данными баннера из анализа.
    """
    spend = banner_data.get("spent", 0.0)
    clicks = banner_data.get("clicks", 0)
    shows = banner_data.get("shows", 0)
    vk_goals = banner_data.get("vk_goals", 0)

    # Вычисляем CTR и CPC
    ctr = (clicks / shows * 100) if shows > 0 else None
    cpc = (spend / clicks) if clicks > 0 else None
    cost_per_conversion = (spend / vk_goals) if vk_goals > 0 else None

    reason = f"Потрачено {spend:.2f}₽ без конверсий (лимит {spent_limit}₽)"
    if not disable_success:
        reason = f"[ОШИБКА ОТКЛЮЧЕНИЯ] {reason}"

    return create_banner_action(
        db=db,
        banner_id=banner_data.get("id"),
        action="disabled",
        account_name=account_name,
        banner_name=banner_data.get("name"),
        ad_group_id=banner_data.get("ad_group_id"),
        banner_status=banner_data.get("status"),
        delivery_status=banner_data.get("delivery"),
        moderation_status=banner_data.get("moderation_status"),
        spend=spend,
        clicks=int(clicks),
        shows=int(shows),
        ctr=ctr,
        cpc=cpc,
        conversions=int(vk_goals),
        cost_per_conversion=cost_per_conversion,
        spent_limit=spent_limit,
        lookback_days=lookback_days,
        analysis_date_from=date_from,
        analysis_date_to=date_to,
        reason=reason,
        stats=banner_data,
        is_dry_run=is_dry_run
    )


def get_banner_history(
    db: Session,
    banner_id: Optional[int] = None,
    vk_account_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 100
) -> List[BannerAction]:
    """Get banner action history with filters"""
    query = db.query(BannerAction)

    if banner_id is not None:
        query = query.filter(BannerAction.banner_id == banner_id)
    if vk_account_id is not None:
        query = query.filter(BannerAction.vk_account_id == vk_account_id)
    if action is not None:
        query = query.filter(BannerAction.action == action)

    return query.order_by(desc(BannerAction.created_at)).limit(limit).all()


def get_disabled_banners(db: Session, limit: int = 100) -> List[BannerAction]:
    """Get recently disabled banners"""
    return get_banner_history(db, action='disabled', limit=limit)


# ===== Active Banners =====

def get_active_banners(db: Session, vk_account_id: Optional[int] = None) -> List[ActiveBanner]:
    """Get all active banners"""
    query = db.query(ActiveBanner)
    if vk_account_id is not None:
        query = query.filter(ActiveBanner.vk_account_id == vk_account_id)
    return query.all()


def add_active_banner(
    db: Session,
    banner_id: int,
    vk_account_id: int,
    banner_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
    campaign_name: Optional[str] = None,
    current_spend: float = 0.0,
    current_conversions: int = 0
) -> ActiveBanner:
    """Add or update active banner"""
    # Check if exists
    existing = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if existing:
        # Update existing
        existing.banner_name = banner_name or existing.banner_name
        existing.campaign_id = campaign_id or existing.campaign_id
        existing.campaign_name = campaign_name or existing.campaign_name
        existing.current_spend = current_spend
        existing.current_conversions = current_conversions
        existing.updated_at = get_moscow_time()
        db.commit()
        db.refresh(existing)
        return existing

    # Check if whitelisted
    is_wl = is_whitelisted(db, banner_id)

    db_banner = ActiveBanner(
        banner_id=banner_id,
        banner_name=banner_name,
        vk_account_id=vk_account_id,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        current_spend=current_spend,
        current_conversions=current_conversions,
        is_whitelisted=is_wl
    )
    db.add(db_banner)
    db.commit()
    db.refresh(db_banner)
    return db_banner


def remove_active_banner(db: Session, banner_id: int) -> bool:
    """Remove banner from active list"""
    banner = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if not banner:
        return False

    db.delete(banner)
    db.commit()
    return True


def update_active_banner_stats(
    db: Session,
    banner_id: int,
    spend: float,
    conversions: int
) -> Optional[ActiveBanner]:
    """Update banner statistics"""
    banner = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if not banner:
        return None

    banner.current_spend = spend
    banner.current_conversions = conversions
    banner.last_checked = get_moscow_time()
    db.commit()
    db.refresh(banner)
    return banner


# ===== Settings =====

def get_setting(db: Session, key: str) -> Optional[dict]:
    """Get setting by key"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        return setting.value
    return None


def set_setting(db: Session, key: str, value: dict, description: Optional[str] = None) -> Settings:
    """Set or update setting"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        setting.value = value
        setting.updated_at = get_moscow_time()
        if description:
            setting.description = description
    else:
        setting = Settings(key=key, value=value, description=description)
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return setting


def get_all_settings(db: Session) -> dict:
    """Get all settings as dict"""
    settings = db.query(Settings).all()
    return {s.key: s.value for s in settings}


def delete_setting(db: Session, key: str) -> bool:
    """Delete setting"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if not setting:
        return False

    db.delete(setting)
    db.commit()
    return True


# ===== Process State =====

def get_process_state(db: Session, name: str) -> Optional[ProcessState]:
    """Get process state by name"""
    return db.query(ProcessState).filter(ProcessState.name == name).first()


def get_all_process_states(db: Session) -> List[ProcessState]:
    """Get all process states"""
    return db.query(ProcessState).all()


def set_process_running(
    db: Session,
    name: str,
    pid: int,
    script_path: Optional[str] = None
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
    else:
        state = ProcessState(
            name=name,
            pid=pid,
            script_path=script_path,
            status='running',
            started_at=now
        )
        db.add(state)

    db.commit()
    db.refresh(state)
    return state


def set_process_stopped(db: Session, name: str, error: Optional[str] = None) -> Optional[ProcessState]:
    """Mark process as stopped"""
    state = get_process_state(db, name)
    if not state:
        return None

    now = get_moscow_time()
    state.pid = None
    state.status = 'crashed' if error else 'stopped'
    state.stopped_at = now
    state.last_error = error
    state.updated_at = now

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
    vk_account_id: Optional[int] = None
) -> DailyAccountStats:
    """Save daily account statistics"""
    stats = DailyAccountStats(
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
    from datetime import timedelta

    end_date = get_moscow_time().date()
    start_date = end_date - timedelta(days=days)

    stats = get_stats_by_date_range(
        db,
        date_from=start_date.isoformat(),
        date_to=end_date.isoformat()
    )

    # Aggregate by account
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


# ===== LeadsTech Config =====

def get_leadstech_config(db: Session) -> Optional[LeadsTechConfig]:
    """Get LeadsTech configuration (singleton)"""
    return db.query(LeadsTechConfig).first()


def create_or_update_leadstech_config(
    db: Session,
    login: str,
    password: str,
    base_url: str = "https://api.leads.tech",
    lookback_days: int = 10,
    banner_sub_field: str = "sub4"
) -> LeadsTechConfig:
    """Create or update LeadsTech configuration"""
    config = get_leadstech_config(db)

    if config:
        config.login = login
        config.password = password
        config.base_url = base_url
        config.lookback_days = lookback_days
        config.banner_sub_field = banner_sub_field
        config.updated_at = get_moscow_time()
    else:
        config = LeadsTechConfig(
            login=login,
            password=password,
            base_url=base_url,
            lookback_days=lookback_days,
            banner_sub_field=banner_sub_field
        )
        db.add(config)

    db.commit()
    db.refresh(config)
    return config


def delete_leadstech_config(db: Session) -> bool:
    """Delete LeadsTech configuration"""
    config = get_leadstech_config(db)
    if not config:
        return False
    db.delete(config)
    db.commit()
    return True


# ===== LeadsTech Cabinets =====

def get_leadstech_cabinets(db: Session, enabled_only: bool = False) -> List[LeadsTechCabinet]:
    """Get all LeadsTech cabinets with their linked accounts"""
    query = db.query(LeadsTechCabinet)
    if enabled_only:
        query = query.filter(LeadsTechCabinet.enabled == True)
    return query.all()


def get_leadstech_cabinet_by_account(db: Session, account_id: int) -> Optional[LeadsTechCabinet]:
    """Get LeadsTech cabinet by VK account ID"""
    return db.query(LeadsTechCabinet).filter(LeadsTechCabinet.account_id == account_id).first()


def create_leadstech_cabinet(
    db: Session,
    account_id: int,
    leadstech_label: str,
    enabled: bool = True
) -> LeadsTechCabinet:
    """Create LeadsTech cabinet mapping"""
    # Check if already exists
    existing = get_leadstech_cabinet_by_account(db, account_id)
    if existing:
        # Update existing
        existing.leadstech_label = leadstech_label
        existing.enabled = enabled
        existing.updated_at = get_moscow_time()
        db.commit()
        db.refresh(existing)
        return existing

    cabinet = LeadsTechCabinet(
        account_id=account_id,
        leadstech_label=leadstech_label,
        enabled=enabled
    )
    db.add(cabinet)
    db.commit()
    db.refresh(cabinet)
    return cabinet


def update_leadstech_cabinet(
    db: Session,
    cabinet_id: int,
    leadstech_label: Optional[str] = None,
    enabled: Optional[bool] = None
) -> Optional[LeadsTechCabinet]:
    """Update LeadsTech cabinet"""
    cabinet = db.query(LeadsTechCabinet).filter(LeadsTechCabinet.id == cabinet_id).first()
    if not cabinet:
        return None

    if leadstech_label is not None:
        cabinet.leadstech_label = leadstech_label
    if enabled is not None:
        cabinet.enabled = enabled
    cabinet.updated_at = get_moscow_time()

    db.commit()
    db.refresh(cabinet)
    return cabinet


def delete_leadstech_cabinet(db: Session, cabinet_id: int) -> bool:
    """Delete LeadsTech cabinet"""
    cabinet = db.query(LeadsTechCabinet).filter(LeadsTechCabinet.id == cabinet_id).first()
    if not cabinet:
        return False
    db.delete(cabinet)
    db.commit()
    return True


# ===== LeadsTech Analysis Results =====

def save_leadstech_analysis_result(
    db: Session,
    analysis_id: str,
    cabinet_name: str,
    leadstech_label: str,
    banner_id: int,
    vk_spent: float,
    lt_revenue: float,
    profit: float,
    roi_percent: Optional[float],
    lt_clicks: int,
    lt_conversions: int,
    lt_approved: int,
    lt_inprogress: int,
    lt_rejected: int,
    date_from: str,
    date_to: str
) -> LeadsTechAnalysisResult:
    """Save a single banner analysis result"""
    result = LeadsTechAnalysisResult(
        analysis_id=analysis_id,
        cabinet_name=cabinet_name,
        leadstech_label=leadstech_label,
        banner_id=banner_id,
        vk_spent=vk_spent,
        lt_revenue=lt_revenue,
        profit=profit,
        roi_percent=roi_percent,
        lt_clicks=lt_clicks,
        lt_conversions=lt_conversions,
        lt_approved=lt_approved,
        lt_inprogress=lt_inprogress,
        lt_rejected=lt_rejected,
        date_from=date_from,
        date_to=date_to
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def save_leadstech_analysis_results_bulk(
    db: Session,
    results: List[dict]
) -> int:
    """Save multiple banner analysis results"""
    count = 0
    for r in results:
        result = LeadsTechAnalysisResult(
            analysis_id=r['analysis_id'],
            cabinet_name=r['cabinet_name'],
            leadstech_label=r['leadstech_label'],
            banner_id=r['banner_id'],
            vk_spent=r.get('vk_spent', 0.0),
            lt_revenue=r.get('lt_revenue', 0.0),
            profit=r.get('profit', 0.0),
            roi_percent=r.get('roi_percent'),
            lt_clicks=r.get('lt_clicks', 0),
            lt_conversions=r.get('lt_conversions', 0),
            lt_approved=r.get('lt_approved', 0),
            lt_inprogress=r.get('lt_inprogress', 0),
            lt_rejected=r.get('lt_rejected', 0),
            date_from=r['date_from'],
            date_to=r['date_to']
        )
        db.add(result)
        count += 1
    db.commit()
    return count


def get_leadstech_analysis_results(
    db: Session,
    analysis_id: Optional[str] = None,
    cabinet_name: Optional[str] = None,
    limit: int = 500
) -> List[LeadsTechAnalysisResult]:
    """Get LeadsTech analysis results with filters"""
    query = db.query(LeadsTechAnalysisResult)

    if analysis_id:
        query = query.filter(LeadsTechAnalysisResult.analysis_id == analysis_id)
    if cabinet_name:
        query = query.filter(LeadsTechAnalysisResult.cabinet_name == cabinet_name)

    return query.order_by(desc(LeadsTechAnalysisResult.created_at)).limit(limit).all()


def get_latest_leadstech_analysis(db: Session) -> Optional[str]:
    """Get the latest analysis_id"""
    result = db.query(LeadsTechAnalysisResult).order_by(
        desc(LeadsTechAnalysisResult.created_at)
    ).first()
    return result.analysis_id if result else None


def get_leadstech_analysis_runs(db: Session, limit: int = 10) -> List[dict]:
    """Get list of analysis runs with summary"""
    from sqlalchemy import func

    # Get unique analysis runs
    subquery = db.query(
        LeadsTechAnalysisResult.analysis_id,
        func.min(LeadsTechAnalysisResult.created_at).label('created_at'),
        func.count(LeadsTechAnalysisResult.id).label('banners_count'),
        func.sum(LeadsTechAnalysisResult.vk_spent).label('total_spent'),
        func.sum(LeadsTechAnalysisResult.lt_revenue).label('total_revenue'),
        func.sum(LeadsTechAnalysisResult.profit).label('total_profit')
    ).group_by(LeadsTechAnalysisResult.analysis_id).order_by(
        desc(func.min(LeadsTechAnalysisResult.created_at))
    ).limit(limit).all()

    runs = []
    for row in subquery:
        runs.append({
            'analysis_id': row.analysis_id,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'banners_count': row.banners_count,
            'total_spent': round(row.total_spent or 0, 2),
            'total_revenue': round(row.total_revenue or 0, 2),
            'total_profit': round(row.total_profit or 0, 2)
        })

    return runs


def delete_leadstech_analysis_results(db: Session, analysis_id: str) -> int:
    """Delete all results for a specific analysis run"""
    count = db.query(LeadsTechAnalysisResult).filter(
        LeadsTechAnalysisResult.analysis_id == analysis_id
    ).delete()
    db.commit()
    return count
