"""
CRUD operations for Banner management
Includes: BannerAction (history), ActiveBanner
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from utils.time_utils import get_moscow_time
from database.models import BannerAction, ActiveBanner, Account, WhitelistBanner


# ===== Banner Actions (History) =====

def create_banner_action(
    db: Session,
    banner_id: int,
    action: str,  # 'disabled' or 'enabled'
    user_id: Optional[int] = None,
    account_name: Optional[str] = None,
    vk_account_id: Optional[int] = None,
    banner_name: Optional[str] = None,
    ad_group_id: Optional[int] = None,
    ad_group_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
    campaign_name: Optional[str] = None,
    banner_status: Optional[str] = None,
    delivery_status: Optional[str] = None,
    moderation_status: Optional[str] = None,
    spend: Optional[float] = None,
    clicks: int = 0,
    shows: int = 0,
    ctr: Optional[float] = None,
    cpc: Optional[float] = None,
    conversions: int = 0,
    cost_per_conversion: Optional[float] = None,
    spent_limit: Optional[float] = None,
    lookback_days: Optional[int] = None,
    analysis_date_from: Optional[str] = None,
    analysis_date_to: Optional[str] = None,
    reason: Optional[str] = None,
    stats: Optional[dict] = None,
    is_dry_run: bool = False,
    roi: Optional[float] = None,
    lt_revenue: Optional[float] = None,
    lt_spent: Optional[float] = None
) -> BannerAction:
    """Log a banner action (enable/disable) with full details"""
    account_db_id = None
    if vk_account_id and user_id:
        account = db.query(Account).filter(
            Account.user_id == user_id,
            Account.account_id == vk_account_id
        ).first()
        if account:
            account_db_id = account.id

    db_action = BannerAction(
        user_id=user_id,
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
        is_dry_run=is_dry_run,
        roi=roi,
        lt_revenue=lt_revenue,
        lt_spent=lt_spent
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
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
    roi_data: Optional[dict] = None
) -> BannerAction:
    """Helper function for logging a disabled banner

    Args:
        roi_data: Optional dict mapping banner_id -> BannerROIData with roi_percent, lt_revenue, vk_spent
    """
    spend = banner_data.get("spent", 0.0)
    clicks = banner_data.get("clicks", 0)
    shows = banner_data.get("shows", 0)
    vk_goals = banner_data.get("vk_goals", 0)

    ctr = (clicks / shows * 100) if shows > 0 else None
    cpc = (spend / clicks) if clicks > 0 else None
    cost_per_conversion = (spend / vk_goals) if vk_goals > 0 else None

    if reason is None:
        matched_rule = banner_data.get("matched_rule", "Не указано")
        reason = matched_rule

    if not disable_success:
        reason = f"[ОШИБКА ОТКЛЮЧЕНИЯ] {reason}"

    # Extract ROI data if available
    roi = None
    lt_revenue = None
    lt_spent = None
    banner_id = banner_data.get("id")
    if roi_data and banner_id:
        roi_info = roi_data.get(banner_id)
        if roi_info:
            # Handle both object and dict
            if hasattr(roi_info, 'roi_percent'):
                roi = roi_info.roi_percent
                lt_revenue = roi_info.lt_revenue
                lt_spent = roi_info.vk_spent
            else:
                roi = roi_info.get('roi_percent')
                lt_revenue = roi_info.get('lt_revenue')
                lt_spent = roi_info.get('vk_spent')
            # Debug logging
            from utils.logging_setup import get_logger
            logger = get_logger(service="crud", function="banners")
            logger.info(f"[ROI DEBUG] banner_id={banner_id}, roi={roi}, lt_revenue={lt_revenue}, lt_spent={lt_spent}")

    return create_banner_action(
        db=db,
        banner_id=banner_id,
        action="disabled",
        user_id=user_id,
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
        is_dry_run=is_dry_run,
        roi=roi,
        lt_revenue=lt_revenue,
        lt_spent=lt_spent
    )


def get_banner_history(
    db: Session,
    user_id: Optional[int] = None,
    banner_id: Optional[int] = None,
    vk_account_id: Optional[int] = None,
    account_name: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
    sort_by: str = 'created_at',
    sort_order: str = 'desc'
) -> tuple[List[BannerAction], int]:
    """Get banner action history with filters, pagination and sorting"""
    query = db.query(BannerAction)

    if user_id is not None:
        query = query.filter(BannerAction.user_id == user_id)
    if banner_id is not None:
        query = query.filter(BannerAction.banner_id == banner_id)
    if vk_account_id is not None:
        query = query.filter(BannerAction.vk_account_id == vk_account_id)
    if account_name is not None:
        query = query.filter(BannerAction.account_name == account_name)
    if action is not None:
        query = query.filter(BannerAction.action == action)

    total = query.count()

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
    user_id: int = None,
    account_name: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
    sort_by: str = 'created_at',
    sort_order: str = 'desc'
) -> tuple[List[BannerAction], int]:
    """Get recently disabled banners with sorting for a user"""
    return get_banner_history(
        db,
        user_id=user_id,
        account_name=account_name,
        action='disabled',
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order
    )


def get_disabled_banners_account_names(db: Session, user_id: int) -> List[str]:
    """Get unique account names from disabled banners for a user"""
    results = db.query(BannerAction.account_name).filter(
        BannerAction.user_id == user_id,
        BannerAction.action == 'disabled',
        BannerAction.account_name.isnot(None)
    ).distinct().all()
    return [r[0] for r in results if r[0]]


# ===== Active Banners =====

def get_active_banners(db: Session, user_id: Optional[int] = None) -> List[ActiveBanner]:
    """Get all active banners for a user"""
    query = db.query(ActiveBanner)
    if user_id is not None:
        query = query.filter(ActiveBanner.user_id == user_id)
    return query.all()


def add_active_banner(
    db: Session,
    banner_id: int,
    vk_account_id: int,
    user_id: Optional[int] = None,
    banner_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
    campaign_name: Optional[str] = None,
    current_spend: float = 0.0,
    current_conversions: int = 0
) -> ActiveBanner:
    """Add or update active banner"""
    existing = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if existing:
        existing.banner_name = banner_name or existing.banner_name
        existing.campaign_id = campaign_id or existing.campaign_id
        existing.campaign_name = campaign_name or existing.campaign_name
        existing.current_spend = current_spend
        existing.current_conversions = current_conversions
        existing.updated_at = get_moscow_time()
        db.commit()
        db.refresh(existing)
        return existing

    is_wl = db.query(WhitelistBanner).filter(
        WhitelistBanner.user_id == user_id,
        WhitelistBanner.banner_id == banner_id
    ).first() is not None if user_id else False

    db_banner = ActiveBanner(
        user_id=user_id,
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
