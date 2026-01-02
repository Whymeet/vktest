"""
Settings management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user
from api.schemas.settings import (
    AnalysisSettings,
    TelegramSettings,
    SchedulerSettings,
    StatisticsTriggerSettings,
    FullConfig,
    LeadsTechCredentialsUpdate,
)
from api.services.cache import cached, CacheTTL, CacheInvalidation

router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _get_leadstech_for_settings(db: Session, user_id: int) -> dict:
    """Helper to get LeadsTech config for settings response"""
    lt_config = crud.get_leadstech_config(db, user_id=user_id)
    if not lt_config:
        return {
            "configured": False,
            "login": "",
            "base_url": "https://api.leads.tech"
        }
    return {
        "configured": True,
        "login": lt_config.login,
        "base_url": lt_config.base_url or "https://api.leads.tech"
    }


@router.get("")
@cached(ttl=CacheTTL.SETTINGS, endpoint_name="settings")
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all settings for current user"""
    settings = crud.get_all_user_settings(db, current_user.id)

    return {
        "analysis_settings": settings.get('analysis_settings', {
            "lookback_days": 10,
            "spent_limit_rub": 100.0,
            "dry_run": False,
            "sleep_between_calls": 3.0
        }),
        "telegram": settings.get('telegram', {
            "bot_token": "",
            "chat_id": [],
            "enabled": False
        }),
        "scheduler": settings.get('scheduler', {
            "enabled": True,
            "interval_minutes": 60,
            "max_runs": 0,
            "start_delay_seconds": 10,
            "retry_on_error": True,
            "retry_delay_minutes": 5,
            "max_retries": 3,
            "quiet_hours": {"enabled": False, "start": "23:00", "end": "08:00"}
        }),
        "statistics_trigger": settings.get('statistics_trigger', {
            "enabled": False,
            "wait_seconds": 10
        }),
        "leadstech": _get_leadstech_for_settings(db, current_user.id)
    }


@router.put("")
async def update_settings(
    settings: FullConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update all settings for current user"""
    crud.set_user_setting(db, current_user.id, 'analysis_settings', settings.analysis_settings.model_dump())
    crud.set_user_setting(db, current_user.id, 'telegram', settings.telegram.model_dump())
    crud.set_user_setting(db, current_user.id, 'scheduler', settings.scheduler.model_dump())
    crud.set_user_setting(db, current_user.id, 'statistics_trigger', settings.statistics_trigger.model_dump())

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "settings")

    return {"message": "Settings updated"}


@router.put("/analysis")
async def update_analysis_settings(
    settings: AnalysisSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update analysis settings for current user"""
    crud.set_user_setting(db, current_user.id, 'analysis_settings', settings.model_dump())
    await CacheInvalidation.after_update(current_user.id, "settings")
    return {"message": "Analysis settings updated"}


@router.put("/telegram")
async def update_telegram_settings(
    settings: TelegramSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update Telegram settings for current user"""
    crud.set_user_setting(db, current_user.id, 'telegram', settings.model_dump())
    await CacheInvalidation.after_update(current_user.id, "settings")
    return {"message": "Telegram settings updated"}


@router.put("/scheduler")
async def update_scheduler_settings(
    settings: SchedulerSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scheduler settings for current user"""
    crud.set_user_setting(db, current_user.id, 'scheduler', settings.model_dump())
    await CacheInvalidation.after_update(current_user.id, "settings")
    return {"message": "Scheduler settings updated"}


@router.put("/statistics_trigger")
async def update_statistics_trigger(
    settings: StatisticsTriggerSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update statistics trigger settings for current user"""
    crud.set_user_setting(db, current_user.id, 'statistics_trigger', settings.model_dump())
    await CacheInvalidation.after_update(current_user.id, "settings")
    return {"message": "Statistics trigger settings updated"}


@router.put("/leadstech")
async def update_leadstech_credentials(
    credentials: LeadsTechCredentialsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update LeadsTech credentials for current user"""
    existing_config = crud.get_leadstech_config(db, user_id=current_user.id)

    # If config exists and no password provided, use existing password
    password = credentials.password
    if not password:
        if existing_config:
            password = existing_config.password
        else:
            raise HTTPException(status_code=400, detail="Password is required for new configuration")

    crud.create_or_update_leadstech_config(
        db,
        login=credentials.login,
        password=password,
        user_id=current_user.id,
        base_url=credentials.base_url or "https://api.leads.tech"
    )

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "leadstech_config")

    return {"message": "LeadsTech credentials updated"}
