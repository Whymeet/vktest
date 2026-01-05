"""
Banners management endpoints
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user

router = APIRouter(prefix="/api/banners", tags=["Banners"])


def _format_banner_action(h) -> dict:
    """Format BannerAction model to dict with all fields"""
    return {
        "id": h.id,
        "banner_id": h.banner_id,
        "banner_name": h.banner_name,
        "ad_group_id": h.ad_group_id,
        "ad_group_name": h.ad_group_name,
        "campaign_id": h.campaign_id,
        "campaign_name": h.campaign_name,
        "account_name": h.account_name,
        "vk_account_id": h.vk_account_id,
        "action": h.action,
        "reason": h.reason,
        # Financial data
        "spend": h.spend,
        "clicks": h.clicks,
        "shows": h.shows,
        "ctr": h.ctr,
        "cpc": h.cpc,
        # Conversions
        "conversions": h.conversions,
        "cost_per_conversion": h.cost_per_conversion,
        # ROI data from LeadsTech
        "roi": h.roi,
        "lt_revenue": h.lt_revenue,
        "lt_spent": h.lt_spent,
        # Status info
        "banner_status": h.banner_status,
        "delivery_status": h.delivery_status,
        "moderation_status": h.moderation_status,
        # Analysis info
        "spent_limit": h.spent_limit,
        "lookback_days": h.lookback_days,
        "analysis_date_from": h.analysis_date_from,
        "analysis_date_to": h.analysis_date_to,
        # Other
        "is_dry_run": h.is_dry_run,
        "created_at": h.created_at.isoformat() if h.created_at else None
    }


@router.get("/active")
async def get_active_banners(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active banners for current user"""
    banners = crud.get_active_banners(db, current_user.id)
    return {
        "banners": [
            {
                "banner_id": b.banner_id,
                "banner_name": b.banner_name,
                "vk_account_id": b.vk_account_id,
                "campaign_id": b.campaign_id,
                "campaign_name": b.campaign_name,
                "current_spend": b.current_spend,
                "current_conversions": b.current_conversions,
                "is_whitelisted": b.is_whitelisted,
                "enabled_at": b.enabled_at.isoformat() if b.enabled_at else None,
                "last_checked": b.last_checked.isoformat() if b.last_checked else None
            }
            for b in banners
        ]
    }


@router.get("/history")
async def get_banner_history(
    banner_id: Optional[int] = None,
    account_id: Optional[int] = None,
    action: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get banner action history with full details and pagination for current user"""
    page_size = min(page_size, 500)
    offset = (page - 1) * page_size

    history, total = crud.get_banner_history(db, current_user.id, banner_id, account_id, action, page_size, offset)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return {
        "count": len(history),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "history": [_format_banner_action(h) for h in history]
    }


@router.get("/disabled")
async def get_disabled_banners(
    page: int = 1,
    page_size: int = 500,
    account_name: Optional[str] = None,
    sort_by: str = 'created_at',
    sort_order: str = 'desc',
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recently disabled banners with full details, pagination and sorting for current user"""
    page_size = min(page_size, 500)
    offset = (page - 1) * page_size

    # Validate sort parameters
    valid_sort_fields = ['created_at', 'spend', 'clicks', 'shows', 'ctr', 'conversions', 'cost_per_conversion', 'banner_id']
    if sort_by not in valid_sort_fields:
        sort_by = 'created_at'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    history, total = crud.get_disabled_banners(
        db,
        user_id=current_user.id,
        account_name=account_name,
        limit=page_size,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order
    )

    # Calculate summary statistics from the filtered results
    total_spend = sum(h.spend or 0 for h in history)
    total_clicks = sum(h.clicks or 0 for h in history)
    total_shows = sum(h.shows or 0 for h in history)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return {
        "count": len(history),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "summary": {
            "total_spend": round(total_spend, 2),
            "total_clicks": total_clicks,
            "total_shows": total_shows,
            "total_banners": total
        },
        "disabled": [_format_banner_action(h) for h in history]
    }


@router.get("/disabled/accounts")
async def get_disabled_banners_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all unique account names from disabled banners for filter dropdown"""
    account_names = crud.get_disabled_banners_account_names(db, user_id=current_user.id)
    return {"accounts": account_names}
