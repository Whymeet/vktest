"""
Dashboard and Health check endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user
from api.services.process_manager import is_process_running_by_db

router = APIRouter(tags=["Dashboard"])


@router.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "4.0.0-modular",
        "database": "postgresql",
        "auth": "enabled"
    }


@router.get("/api/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dashboard overview for current user"""
    accounts = crud.get_accounts(db, current_user.id)
    whitelist_count = len(crud.get_whitelist(db, current_user.id))
    active_banners = crud.get_active_banners(db, current_user.id)

    # Get user settings
    settings = crud.get_all_user_settings(db, current_user.id)
    scheduler_settings = settings.get('scheduler', {})
    analysis_settings = settings.get('analysis_settings', {})
    telegram_settings = settings.get('telegram', {})

    # Check actual process status from DB for this user
    scheduler_running, scheduler_pid = is_process_running_by_db("scheduler", db, current_user.id)

    return {
        "accounts_count": len(accounts),
        "whitelist_count": whitelist_count,
        "active_banners_count": len(active_banners),
        "scheduler_enabled": scheduler_settings.get('enabled', False),
        "process_status": {
            "scheduler": {"running": scheduler_running, "pid": scheduler_pid}
        },
        "dry_run": analysis_settings.get('dry_run', False),
        "telegram_enabled": telegram_settings.get('enabled', False)
    }
