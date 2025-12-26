"""
Account Statistics endpoints
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user

router = APIRouter(prefix="/api/stats", tags=["Statistics"])


def _format_account_stats(s) -> dict:
    """Format DailyAccountStats model to dict"""
    return {
        "id": s.id,
        "account_name": s.account_name,
        "vk_account_id": s.vk_account_id,
        "stats_date": s.stats_date,
        "active_banners": s.active_banners,
        "disabled_banners": s.disabled_banners,
        "over_limit_banners": s.over_limit_banners,
        "under_limit_banners": s.under_limit_banners,
        "no_activity_banners": s.no_activity_banners,
        "total_spend": s.total_spend,
        "total_clicks": s.total_clicks,
        "total_shows": s.total_shows,
        "total_conversions": s.total_conversions,
        "spent_limit": s.spent_limit,
        "lookback_days": s.lookback_days,
        "created_at": s.created_at.isoformat() if s.created_at else None
    }


@router.get("/accounts")
async def get_account_stats(
    account_name: Optional[str] = None,
    stats_date: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get account statistics with optional filters"""
    stats = crud.get_account_stats(db, account_name=account_name, stats_date=stats_date, limit=limit)
    return {
        "count": len(stats),
        "stats": [_format_account_stats(s) for s in stats]
    }


@router.get("/accounts/today")
async def get_today_account_stats(
    account_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get today's account statistics"""
    stats = crud.get_today_stats(db, account_name=account_name)
    return {
        "count": len(stats),
        "date": datetime.utcnow().strftime('%Y-%m-%d'),
        "stats": [_format_account_stats(s) for s in stats]
    }


@router.get("/accounts/range")
async def get_account_stats_range(
    date_from: str,
    date_to: str,
    account_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get account statistics for date range"""
    stats = crud.get_stats_by_date_range(db, date_from, date_to, account_name)
    return {
        "count": len(stats),
        "date_from": date_from,
        "date_to": date_to,
        "stats": [_format_account_stats(s) for s in stats]
    }


@router.get("/accounts/summary")
async def get_account_stats_summary(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get aggregated summary for last N days"""
    summary = crud.get_account_stats_summary(db, days=days)
    return summary
