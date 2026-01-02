"""
CRUD operations for LeadsTech integration
Includes: LeadsTechConfig, LeadsTechCabinet, LeadsTechAnalysisResult
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from utils.time_utils import get_moscow_time
from utils.logging_setup import get_logger
from database.models import LeadsTechConfig, LeadsTechCabinet, LeadsTechAnalysisResult, LeadsTechCabinetTotal

logger = get_logger(service="crud", function="leadstech")


# ===== LeadsTech Config =====

def get_leadstech_config(db: Session, user_id: int = None) -> Optional[LeadsTechConfig]:
    """Get LeadsTech configuration for user"""
    if user_id is None:
        return db.query(LeadsTechConfig).first()
    return db.query(LeadsTechConfig).filter(LeadsTechConfig.user_id == user_id).first()


def create_or_update_leadstech_config(
    db: Session,
    login: str,
    password: str,
    base_url: str = "https://api.leads.tech",
    date_from: str = None,
    date_to: str = None,
    banner_sub_fields: list = None,
    user_id: int = None
) -> LeadsTechConfig:
    """Create or update LeadsTech configuration for user"""
    if banner_sub_fields is None:
        banner_sub_fields = ["sub4", "sub5"]

    config = db.query(LeadsTechConfig).filter(LeadsTechConfig.user_id == user_id).first() if user_id else get_leadstech_config(db)

    if config:
        config.login = login
        config.password = password
        config.base_url = base_url
        config.date_from = date_from
        config.date_to = date_to
        config.banner_sub_fields = banner_sub_fields
        config.updated_at = get_moscow_time()
    else:
        config = LeadsTechConfig(
            user_id=user_id,
            login=login,
            password=password,
            base_url=base_url,
            date_from=date_from,
            date_to=date_to,
            banner_sub_fields=banner_sub_fields
        )
        db.add(config)

    db.commit()
    db.refresh(config)
    return config


def delete_leadstech_config(db: Session, user_id: int = None) -> bool:
    """Delete LeadsTech configuration for user"""
    config = get_leadstech_config(db, user_id=user_id)
    if not config:
        return False
    db.delete(config)
    db.commit()
    return True


# ===== LeadsTech Cabinets =====

def get_leadstech_cabinets(db: Session, user_id: int, enabled_only: bool = False) -> List[LeadsTechCabinet]:
    """Get all LeadsTech cabinets with their linked accounts for a specific user"""
    query = db.query(LeadsTechCabinet).filter(LeadsTechCabinet.user_id == user_id)
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
    enabled: bool = True,
    user_id: int = None
) -> LeadsTechCabinet:
    """Create LeadsTech cabinet mapping"""
    existing = get_leadstech_cabinet_by_account(db, account_id)
    if existing:
        existing.leadstech_label = leadstech_label
        existing.enabled = enabled
        existing.updated_at = get_moscow_time()
        db.commit()
        db.refresh(existing)
        return existing

    cabinet = LeadsTechCabinet(
        user_id=user_id,
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
    results: List[dict],
    user_id: int = None
) -> int:
    """Clear all existing results for user and save new ones"""
    if user_id:
        db.query(LeadsTechAnalysisResult).filter(LeadsTechAnalysisResult.user_id == user_id).delete()
    else:
        db.query(LeadsTechAnalysisResult).delete()

    count = 0
    for r in results:
        result = LeadsTechAnalysisResult(
            user_id=user_id,
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
    sort_order: str = 'desc',
    user_id: int = None,
    roi_min: Optional[float] = None,
    roi_max: Optional[float] = None,
    spent_min: Optional[float] = None,
    spent_max: Optional[float] = None,
    revenue_min: Optional[float] = None,
    revenue_max: Optional[float] = None,
    profit_min: Optional[float] = None,
    profit_max: Optional[float] = None
) -> tuple[List[LeadsTechAnalysisResult], int]:
    """Get LeadsTech analysis results with pagination, sorting and filters."""
    query = db.query(LeadsTechAnalysisResult)

    if user_id:
        query = query.filter(LeadsTechAnalysisResult.user_id == user_id)
    if cabinet_name:
        query = query.filter(LeadsTechAnalysisResult.cabinet_name == cabinet_name)

    if roi_min is not None:
        query = query.filter(LeadsTechAnalysisResult.roi_percent >= roi_min)
    if roi_max is not None:
        query = query.filter(LeadsTechAnalysisResult.roi_percent <= roi_max)
    if spent_min is not None:
        query = query.filter(LeadsTechAnalysisResult.vk_spent >= spent_min)
    if spent_max is not None:
        query = query.filter(LeadsTechAnalysisResult.vk_spent <= spent_max)
    if revenue_min is not None:
        query = query.filter(LeadsTechAnalysisResult.lt_revenue >= revenue_min)
    if revenue_max is not None:
        query = query.filter(LeadsTechAnalysisResult.lt_revenue <= revenue_max)
    if profit_min is not None:
        query = query.filter(LeadsTechAnalysisResult.profit >= profit_min)
    if profit_max is not None:
        query = query.filter(LeadsTechAnalysisResult.profit <= profit_max)

    total = query.count()

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


def get_leadstech_analysis_cabinet_names(db: Session, user_id: int) -> List[str]:
    """Get all unique cabinet names from analysis results for a specific user"""
    results = db.query(LeadsTechAnalysisResult.cabinet_name).filter(
        LeadsTechAnalysisResult.user_id == user_id
    ).distinct().all()
    return sorted([r[0] for r in results if r[0]])


def get_leadstech_data_for_banners(
    db: Session,
    user_id: int,
    cabinet_name: str
) -> dict:
    """
    Get LeadsTech data for ROI enrichment in scaling.

    Returns a mapping of banner_id to its LeadsTech metrics:
    {
        banner_id: {
            "lt_revenue": float,
            "vk_spent": float,
            "profit": float,
            "roi_percent": float or None
        }
    }

    Args:
        db: Database session
        user_id: User ID
        cabinet_name: VK cabinet name to filter by

    Returns:
        Dict mapping banner_id to metrics
    """
    logger.info(f"🔍 Загрузка LeadsTech данных для кабинета '{cabinet_name}' (user_id={user_id})...")

    results = db.query(LeadsTechAnalysisResult).filter(
        LeadsTechAnalysisResult.user_id == user_id,
        LeadsTechAnalysisResult.cabinet_name == cabinet_name
    ).all()

    data = {}
    total_revenue = 0.0
    total_spent = 0.0

    for r in results:
        data[r.banner_id] = {
            "lt_revenue": float(r.lt_revenue or 0),
            "vk_spent": float(r.vk_spent or 0),
            "profit": float(r.profit or 0),
            "roi_percent": float(r.roi_percent) if r.roi_percent is not None else None
        }
        total_revenue += float(r.lt_revenue or 0)
        total_spent += float(r.vk_spent or 0)

    if data:
        logger.info(f"✅ Найдено {len(data)} баннеров с LeadsTech данными")
        logger.info(f"   Общий доход: {total_revenue:.2f}₽, расход: {total_spent:.2f}₽")
        # Логируем первые 3 баннера для отладки
        for i, (bid, bdata) in enumerate(list(data.items())[:3]):
            roi = bdata['roi_percent']
            roi_str = f"{roi:.1f}%" if roi is not None else "N/A"
            logger.debug(f"   Баннер {bid}: revenue={bdata['lt_revenue']:.0f}, spent={bdata['vk_spent']:.0f}, ROI={roi_str}")
    else:
        logger.warning(f"⚠️ Нет LeadsTech данных для кабинета '{cabinet_name}'")

    return data


def get_leadstech_analysis_stats(
    db: Session,
    user_id: int,
    cabinet_name: Optional[str] = None,
    roi_min: Optional[float] = None,
    roi_max: Optional[float] = None,
    spent_min: Optional[float] = None,
    spent_max: Optional[float] = None,
    revenue_min: Optional[float] = None,
    revenue_max: Optional[float] = None,
    profit_min: Optional[float] = None,
    profit_max: Optional[float] = None
) -> dict:
    """Get aggregated statistics for LeadsTech analysis results"""
    query = db.query(
        func.count(LeadsTechAnalysisResult.id).label('total_count'),
        func.coalesce(func.sum(LeadsTechAnalysisResult.vk_spent), 0).label('total_spent'),
        func.coalesce(func.sum(LeadsTechAnalysisResult.lt_revenue), 0).label('total_revenue'),
        func.coalesce(func.sum(LeadsTechAnalysisResult.profit), 0).label('total_profit')
    ).filter(LeadsTechAnalysisResult.user_id == user_id)

    if cabinet_name:
        query = query.filter(LeadsTechAnalysisResult.cabinet_name == cabinet_name)
    if roi_min is not None:
        query = query.filter(LeadsTechAnalysisResult.roi_percent >= roi_min)
    if roi_max is not None:
        query = query.filter(LeadsTechAnalysisResult.roi_percent <= roi_max)
    if spent_min is not None:
        query = query.filter(LeadsTechAnalysisResult.vk_spent >= spent_min)
    if spent_max is not None:
        query = query.filter(LeadsTechAnalysisResult.vk_spent <= spent_max)
    if revenue_min is not None:
        query = query.filter(LeadsTechAnalysisResult.lt_revenue >= revenue_min)
    if revenue_max is not None:
        query = query.filter(LeadsTechAnalysisResult.lt_revenue <= revenue_max)
    if profit_min is not None:
        query = query.filter(LeadsTechAnalysisResult.profit >= profit_min)
    if profit_max is not None:
        query = query.filter(LeadsTechAnalysisResult.profit <= profit_max)

    result = query.first()

    total_spent = float(result.total_spent or 0)
    total_revenue = float(result.total_revenue or 0)
    total_profit = float(result.total_profit or 0)

    weighted_roi = (total_profit / total_spent * 100) if total_spent > 0 else 0

    # Get total VK spent (filtered by cabinet if specified)
    total_vk_spent = get_cabinet_total_spent(db, user_id, cabinet_name)
    real_profit = total_revenue - total_vk_spent

    return {
        'total_count': result.total_count or 0,
        'total_spent': total_spent,
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'avg_roi': weighted_roi,
        'total_vk_spent': total_vk_spent,
        'real_profit': real_profit
    }


# ===== LeadsTech Cabinet Totals =====

def save_leadstech_cabinet_totals(
    db: Session,
    user_id: int,
    cabinet_totals: dict,
    date_from: str,
    date_to: str
) -> int:
    """
    Save total VK spent for each cabinet.

    Args:
        db: Database session
        user_id: User ID
        cabinet_totals: Dict mapping cabinet_name to total_vk_spent
        date_from: Analysis date range start
        date_to: Analysis date range end

    Returns:
        Number of records saved
    """
    # Delete old totals for this user
    db.query(LeadsTechCabinetTotal).filter(LeadsTechCabinetTotal.user_id == user_id).delete()

    # Insert new totals
    count = 0
    for cabinet_name, total_spent in cabinet_totals.items():
        db.add(LeadsTechCabinetTotal(
            user_id=user_id,
            cabinet_name=cabinet_name,
            total_vk_spent=total_spent,
            date_from=date_from,
            date_to=date_to,
        ))
        count += 1

    db.commit()
    logger.info(f"Saved cabinet totals for {count} cabinets")
    return count


def get_cabinet_total_spent(
    db: Session,
    user_id: int,
    cabinet_name: Optional[str] = None
) -> float:
    """
    Get total VK spent - for specific cabinet or sum of all.

    Args:
        db: Database session
        user_id: User ID
        cabinet_name: Optional cabinet name to filter by

    Returns:
        Total VK spent (sum of all cabinets if cabinet_name is None)
    """
    query = db.query(func.sum(LeadsTechCabinetTotal.total_vk_spent)).filter(
        LeadsTechCabinetTotal.user_id == user_id
    )
    if cabinet_name:
        query = query.filter(LeadsTechCabinetTotal.cabinet_name == cabinet_name)

    result = query.scalar()
    return float(result or 0)
