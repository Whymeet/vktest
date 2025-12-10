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
    ScalingConfig,
    ScalingConfigAccount,
    ScalingCondition,
    ScalingLog,
    DisableRule,
    DisableRuleCondition,
    DisableRuleAccount,
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

    # Сначала удаляем связанные записи LeadsTechCabinet
    db.query(LeadsTechCabinet).filter(LeadsTechCabinet.account_id == account.id).delete()
    
    # Теперь удаляем сам аккаунт (остальные связи удалятся каскадно)
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
    lookback_days: int,
    date_from: str,
    date_to: str,
    is_dry_run: bool = False,
    disable_success: bool = True,
    reason: Optional[str] = None
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

    # Формируем причину отключения
    if reason is None:
        matched_rule = banner_data.get("matched_rule", "Не указано")
        reason = f"Сработало правило: {matched_rule}"
    
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
    limit: int = 500,
    offset: int = 0,
    sort_by: str = 'created_at',
    sort_order: str = 'desc'
) -> tuple[List[BannerAction], int]:
    """Get banner action history with filters, pagination and sorting"""
    query = db.query(BannerAction)

    if banner_id is not None:
        query = query.filter(BannerAction.banner_id == banner_id)
    if vk_account_id is not None:
        query = query.filter(BannerAction.vk_account_id == vk_account_id)
    if action is not None:
        query = query.filter(BannerAction.action == action)

    total = query.count()
    
    # Determine sort column
    sort_columns = {
        'created_at': BannerAction.created_at,
        'spend': BannerAction.spend,
        'clicks': BannerAction.clicks,
        'shows': BannerAction.shows,
        'ctr': BannerAction.ctr,
        'conversions': BannerAction.conversions,
        'cost_per_conversion': BannerAction.cost_per_conversion,
        'banner_id': BannerAction.banner_id,
    }
    
    sort_column = sort_columns.get(sort_by, BannerAction.created_at)
    
    if sort_order == 'asc':
        query = query.order_by(sort_column.asc().nullslast())
    else:
        query = query.order_by(sort_column.desc().nullslast())
    
    items = query.offset(offset).limit(limit).all()
    return items, total


def get_disabled_banners(
    db: Session, 
    limit: int = 500, 
    offset: int = 0,
    sort_by: str = 'created_at',
    sort_order: str = 'desc'
) -> tuple[List[BannerAction], int]:
    """Get recently disabled banners with sorting"""
    return get_banner_history(db, action='disabled', limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order)


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


def replace_leadstech_analysis_results(
    db: Session,
    results: List[dict]
) -> int:
    """Clear all existing results and save new ones"""
    # Delete all existing results
    db.query(LeadsTechAnalysisResult).delete()
    
    # Add new results
    count = 0
    for r in results:
        result = LeadsTechAnalysisResult(
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
    cabinet_name: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
    sort_by: str = 'created_at',
    sort_order: str = 'desc'
) -> tuple[List[LeadsTechAnalysisResult], int]:
    """Get LeadsTech analysis results with pagination and sorting"""
    query = db.query(LeadsTechAnalysisResult)

    if cabinet_name:
        query = query.filter(LeadsTechAnalysisResult.cabinet_name == cabinet_name)

    total = query.count()
    
    # Determine sort column
    sort_columns = {
        'created_at': LeadsTechAnalysisResult.created_at,
        'roi_percent': LeadsTechAnalysisResult.roi_percent,
        'profit': LeadsTechAnalysisResult.profit,
        'vk_spent': LeadsTechAnalysisResult.vk_spent,
        'lt_revenue': LeadsTechAnalysisResult.lt_revenue,
        'banner_id': LeadsTechAnalysisResult.banner_id,
    }
    
    sort_column = sort_columns.get(sort_by, LeadsTechAnalysisResult.created_at)
    
    if sort_order == 'asc':
        query = query.order_by(sort_column.asc().nullslast())
    else:
        query = query.order_by(sort_column.desc().nullslast())
    
    items = query.offset(offset).limit(limit).all()
    return items, total


def get_leadstech_analysis_cabinet_names(db: Session) -> List[str]:
    """Get all unique cabinet names from analysis results"""
    results = db.query(LeadsTechAnalysisResult.cabinet_name).distinct().all()
    return sorted([r[0] for r in results if r[0]])


def get_disabled_banners_account_names(db: Session) -> List[str]:
    """Get all unique account names from disabled banners"""
    results = db.query(BannerAction.account_name).filter(
        BannerAction.action == 'disabled'
    ).distinct().all()
    return sorted([r[0] for r in results if r[0]])


# ===== Auto-Scaling =====

def get_scaling_configs(db: Session) -> List[ScalingConfig]:
    """Get all scaling configurations"""
    return db.query(ScalingConfig).order_by(ScalingConfig.created_at.desc()).all()


def get_scaling_config_by_id(db: Session, config_id: int) -> Optional[ScalingConfig]:
    """Get scaling configuration by ID"""
    return db.query(ScalingConfig).filter(ScalingConfig.id == config_id).first()


def get_enabled_scaling_configs(db: Session) -> List[ScalingConfig]:
    """Get all enabled scaling configurations"""
    return db.query(ScalingConfig).filter(ScalingConfig.enabled == True).all()


def get_scaling_config_account_ids(db: Session, config_id: int) -> List[int]:
    """Get list of account IDs linked to a scaling config"""
    links = db.query(ScalingConfigAccount).filter(
        ScalingConfigAccount.config_id == config_id
    ).all()
    return [link.account_id for link in links]


def set_scaling_config_accounts(db: Session, config_id: int, account_ids: List[int]) -> None:
    """Set accounts for a scaling config (replaces existing links)"""
    # Delete existing links
    db.query(ScalingConfigAccount).filter(
        ScalingConfigAccount.config_id == config_id
    ).delete()
    
    # Create new links
    for account_id in account_ids:
        link = ScalingConfigAccount(config_id=config_id, account_id=account_id)
        db.add(link)
    
    db.commit()


def create_scaling_config(
    db: Session,
    name: str,
    schedule_time: str = "08:00",
    account_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    new_budget: Optional[float] = None,
    auto_activate: bool = False,
    lookback_days: int = 7,
    duplicates_count: int = 1,
    enabled: bool = False
) -> ScalingConfig:
    """Create new scaling configuration"""
    config = ScalingConfig(
        name=name,
        schedule_time=schedule_time,
        account_id=account_id,
        new_budget=new_budget,
        auto_activate=auto_activate,
        lookback_days=lookback_days,
        duplicates_count=duplicates_count,
        enabled=enabled
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    
    # Set account links if provided
    if account_ids:
        set_scaling_config_accounts(db, config.id, account_ids)
    
    return config


def update_scaling_config(
    db: Session,
    config_id: int,
    name: Optional[str] = None,
    schedule_time: Optional[str] = None,
    account_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    new_budget: Optional[float] = None,
    auto_activate: Optional[bool] = None,
    lookback_days: Optional[int] = None,
    duplicates_count: Optional[int] = None,
    enabled: Optional[bool] = None
) -> Optional[ScalingConfig]:
    """Update scaling configuration"""
    config = get_scaling_config_by_id(db, config_id)
    if not config:
        return None
    
    if name is not None:
        config.name = name
    if schedule_time is not None:
        config.schedule_time = schedule_time
    if account_id is not None:
        config.account_id = account_id if account_id > 0 else None
    if new_budget is not None:
        config.new_budget = new_budget if new_budget > 0 else None
    if auto_activate is not None:
        config.auto_activate = auto_activate
    if lookback_days is not None:
        config.lookback_days = lookback_days
    if duplicates_count is not None:
        config.duplicates_count = max(1, duplicates_count)
    if enabled is not None:
        config.enabled = enabled
    
    config.updated_at = get_moscow_time()
    db.commit()
    db.refresh(config)
    
    # Update account links if provided
    if account_ids is not None:
        set_scaling_config_accounts(db, config_id, account_ids)
    
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
    db.commit()
    return count


def set_scaling_conditions(
    db: Session,
    config_id: int,
    conditions: List[dict]
) -> List[ScalingCondition]:
    """Replace all conditions for a config with new ones"""
    # Delete existing conditions
    delete_all_scaling_conditions(db, config_id)
    
    # Create new conditions
    result = []
    for i, cond in enumerate(conditions):
        condition = create_scaling_condition(
            db,
            config_id=config_id,
            metric=cond.get("metric", "goals"),
            operator=cond.get("operator", ">"),
            value=cond.get("value", 0),
            order=i
        )
        result.append(condition)
    
    return result


# ===== Scaling Logs =====

def get_scaling_logs(
    db: Session,
    config_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple[List[ScalingLog], int]:
    """Get scaling logs with pagination"""
    query = db.query(ScalingLog)
    
    if config_id:
        query = query.filter(ScalingLog.config_id == config_id)
    
    total = query.count()
    items = query.order_by(ScalingLog.created_at.desc()).offset(offset).limit(limit).all()
    
    return items, total


def create_scaling_log(
    db: Session,
    config_id: Optional[int],
    config_name: Optional[str],
    account_name: Optional[str],
    original_group_id: int,
    original_group_name: Optional[str],
    new_group_id: Optional[int] = None,
    new_group_name: Optional[str] = None,
    stats_snapshot: Optional[dict] = None,
    success: bool = False,
    error_message: Optional[str] = None,
    total_banners: int = 0,
    duplicated_banners: int = 0
) -> ScalingLog:
    """Create new scaling log entry"""
    log = ScalingLog(
        config_id=config_id,
        config_name=config_name,
        account_name=account_name,
        original_group_id=original_group_id,
        original_group_name=original_group_name,
        new_group_id=new_group_id,
        new_group_name=new_group_name,
        stats_snapshot=stats_snapshot,
        success=success,
        error_message=error_message,
        total_banners=total_banners,
        duplicated_banners=duplicated_banners
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def check_group_conditions(stats: dict, conditions: List[ScalingCondition]) -> bool:
    """
    Check if ad group stats match all conditions
    
    Args:
        stats: Dict with keys: spent, shows, clicks, goals, cost_per_goal
        conditions: List of ScalingCondition objects
    
    Returns:
        True if ALL conditions are satisfied
    """
    if not conditions:
        return False  # No conditions = don't match anything
    
    for condition in conditions:
        metric = condition.metric
        operator = condition.operator
        threshold = condition.value
        
        # Get metric value from stats
        actual_value = stats.get(metric)
        
        # Handle None values
        if actual_value is None:
            if metric == "cost_per_goal":
                # If no goals, cost_per_goal is infinite
                actual_value = float('inf')
            else:
                actual_value = 0
        
        # Check condition
        if operator == ">":
            if not (actual_value > threshold):
                return False
        elif operator == ">=":
            if not (actual_value >= threshold):
                return False
        elif operator == "<":
            if not (actual_value < threshold):
                return False
        elif operator == "<=":
            if not (actual_value <= threshold):
                return False
        elif operator == "==":
            if not (actual_value == threshold):
                return False
        elif operator == "!=":
            if not (actual_value != threshold):
                return False
        else:
            # Unknown operator, skip
            continue
    
    return True


# ===== Disable Rules (правила автоотключения объявлений) =====

def get_disable_rules(db: Session, enabled_only: bool = False) -> List[DisableRule]:
    """Get all disable rules, optionally filtered by enabled status"""
    query = db.query(DisableRule)
    if enabled_only:
        query = query.filter(DisableRule.enabled == True)
    return query.order_by(desc(DisableRule.priority), DisableRule.id).all()


def get_disable_rule_by_id(db: Session, rule_id: int) -> Optional[DisableRule]:
    """Get a specific disable rule by ID"""
    return db.query(DisableRule).filter(DisableRule.id == rule_id).first()


def create_disable_rule(
    db: Session,
    name: str,
    description: Optional[str] = None,
    enabled: bool = True,
    priority: int = 0
) -> DisableRule:
    """Create a new disable rule"""
    rule = DisableRule(
        name=name,
        description=description,
        enabled=enabled,
        priority=priority
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
    priority: Optional[int] = None
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


# ===== Disable Rule Accounts (привязка правил к кабинетам) =====

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


def replace_rule_accounts(db: Session, rule_id: int, account_ids: List[int]) -> List[int]:
    """Replace all account links for a rule"""
    # Delete existing links
    db.query(DisableRuleAccount).filter(
        DisableRuleAccount.rule_id == rule_id
    ).delete()
    
    # Add new links
    for account_id in account_ids:
        link = DisableRuleAccount(rule_id=rule_id, account_id=account_id)
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
    
    query = db.query(DisableRule).filter(DisableRule.id.in_(rule_ids))
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
    rules: List[DisableRule]
) -> Optional[DisableRule]:
    """
    Check if banner stats match any disable rule.
    Returns the first matching rule (highest priority first), or None.
    
    Args:
        stats: Dict with keys: goals, spent, clicks, shows, ctr, cpc, cost_per_goal
        rules: List of DisableRule objects (should be pre-filtered for account)
    
    Returns:
        The first matching DisableRule, or None if no rules match
    """
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


def format_rule_match_reason(rule: DisableRule, stats: dict) -> str:
    """
    Format a human-readable reason for why a banner matched a rule.
    
    Args:
        rule: The matched DisableRule
        stats: Banner statistics
    
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
        "cost_per_goal": "цена результата"
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
            else:
                actual = 0
        
        if isinstance(actual, float) and actual != float('inf'):
            actual = f"{actual:.2f}"
        
        parts.append(f"  {metric_name} {op_name} {condition.value} (факт: {actual})")
    
    return "\n".join(parts)
