"""
VK Ads Manager - FastAPI Backend with PostgreSQL
Версия с базой данных вместо JSON файлов
Версия 3.1.0 - с персистентным управлением процессами
"""

import asyncio
import json
import os
import sys
import subprocess
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uvicorn
import psutil
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db, init_db, SessionLocal
from database import crud
from utils.time_utils import get_moscow_time
from auth.dependencies import get_current_user, get_current_superuser, get_optional_current_user
from database.models import User
from api.auth_routes import router as auth_router

# Определяем окружение (Docker или локальное)
IN_DOCKER = os.environ.get('IN_DOCKER', 'false').lower() == 'true'

# Пути к проекту
if IN_DOCKER:
    PROJECT_ROOT = Path("/app")
    CFG_PATH = PROJECT_ROOT / "config"
    LOGS_DIR = PROJECT_ROOT / "logs"
    DATA_DIR = PROJECT_ROOT / "data"
    SCHEDULER_SCRIPT = PROJECT_ROOT / "scheduler" / "scheduler_main.py"
    MAIN_SCRIPT = PROJECT_ROOT / "core" / "main.py"
    BOT_SCRIPT = PROJECT_ROOT / "bot" / "telegram_bot.py"
else:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    CFG_PATH = PROJECT_ROOT / "config"
    LOGS_DIR = PROJECT_ROOT / "logs"
    DATA_DIR = PROJECT_ROOT / "data"
    SCHEDULER_SCRIPT = PROJECT_ROOT / "backend" / "scheduler" / "scheduler_main.py"
    MAIN_SCRIPT = PROJECT_ROOT / "backend" / "core" / "main.py"
    BOT_SCRIPT = PROJECT_ROOT / "backend" / "bot" / "telegram_bot.py"

# Глобальное хранилище процессов (кэш для текущей сессии API)
# PID также сохраняется в БД для персистентности
running_processes: Dict[str, subprocess.Popen] = {}


# === Process Management Helpers ===

def check_pid_alive(pid: int) -> bool:
    """Check if process with given PID is alive using psutil"""
    if pid is None:
        return False
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def check_process_is_python_script(pid: int, script_name: str) -> bool:
    """Check if PID is our Python script (not just any process with same PID)"""
    if pid is None:
        return False
    try:
        process = psutil.Process(pid)
        cmdline = process.cmdline()
        # Check if it's a python process running our script
        return any(script_name in arg for arg in cmdline)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def kill_process_by_pid(pid: int, timeout: int = 10) -> bool:
    """Kill process by PID with graceful termination"""
    if not check_pid_alive(pid):
        return True

    try:
        process = psutil.Process(pid)
        # First try graceful termination
        process.terminate()

        try:
            process.wait(timeout=timeout)
        except psutil.TimeoutExpired:
            # Force kill if not responding
            process.kill()
            process.wait(timeout=5)

        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"Error killing process {pid}: {e}")
        return False


def recover_processes_on_startup():
    """Recover process tracking on API startup by checking saved PIDs"""
    db = SessionLocal()
    try:
        # Get all process states (global check)
        process_states = crud.get_all_process_states(db)

        for state in process_states:
            if state.status == 'running' and state.pid:
                script_name = Path(state.script_path).name if state.script_path else state.name

                if check_process_is_python_script(state.pid, script_name):
                    # Process is still running - keep tracking it
                    print(f"✅ Recovered running process: {state.name} (PID: {state.pid})")
                else:
                    # Process died while API was down - update in DB
                    state.status = 'stopped'
                    state.last_error = "Process died while API was down"
                    db.commit()
                    print(f"⚠️ Process {state.name} (PID: {state.pid}) is no longer running, marked as stopped")
    except Exception as e:
        print(f"⚠️ Error during process recovery: {e}")
    finally:
        db.close()


# === Pydantic Models ===

class AccountModel(BaseModel):
    name: str
    api: str
    trigger: Optional[int] = None
    spent_limit_rub: float = 100.0


class AccountCreate(BaseModel):
    name: str
    api: str
    trigger: Optional[int] = None
    spent_limit_rub: Optional[float] = 100.0


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    api: Optional[str] = None
    trigger: Optional[int] = None
    spent_limit_rub: Optional[float] = None


class AnalysisSettings(BaseModel):
    lookback_days: int = 10
    spent_limit_rub: float = 100.0
    dry_run: bool = False
    sleep_between_calls: float = 3.0


class TelegramSettings(BaseModel):
    bot_token: str
    chat_id: List[str]
    enabled: bool = True


class QuietHours(BaseModel):
    enabled: bool = False
    start: str = "23:00"
    end: str = "08:00"


class SecondPassSettings(BaseModel):
    enabled: bool = True
    extra_days_min: int = 7
    extra_days_max: int = 50
    delay_seconds: int = 30


class ReEnableSettings(BaseModel):
    """Settings for auto re-enabling previously disabled banners (runs after main analysis)"""
    enabled: bool = False
    interval_minutes: int = 120  # Интервал между запусками автовключения (по умолчанию 2 часа)
    lookback_hours: int = 24  # Смотрим отключённые баннеры за последние N часов
    delay_after_analysis_seconds: int = 30  # Пауза после основного анализа перед автовключением
    dry_run: bool = True  # Режим тестирования (не включать реально)


class SchedulerSettings(BaseModel):
    enabled: bool = True
    interval_minutes: int = 60
    max_runs: int = 0
    start_delay_seconds: int = 10
    retry_on_error: bool = True
    retry_delay_minutes: int = 5
    max_retries: int = 3
    quiet_hours: QuietHours = QuietHours()
    second_pass: SecondPassSettings = SecondPassSettings()
    reenable: ReEnableSettings = ReEnableSettings()  # Настройки автовключения


class StatisticsTriggerSettings(BaseModel):
    enabled: bool = False
    wait_seconds: int = 10


class FullConfig(BaseModel):
    analysis_settings: AnalysisSettings
    telegram: TelegramSettings
    scheduler: SchedulerSettings
    statistics_trigger: StatisticsTriggerSettings


# === LeadsTech Pydantic Models ===

class LeadsTechConfigCreate(BaseModel):
    login: str
    password: Optional[str] = None  # Optional to allow updates without password
    base_url: str = "https://api.leads.tech"
    lookback_days: int = 10
    banner_sub_field: str = "sub4"


class LeadsTechCabinetCreate(BaseModel):
    account_id: int
    leadstech_label: str
    enabled: bool = True


class LeadsTechCabinetUpdate(BaseModel):
    leadstech_label: Optional[str] = None
    enabled: Optional[bool] = None


# === Disable Rules Pydantic Models ===

class DisableRuleConditionModel(BaseModel):
    """Одно условие правила отключения"""
    metric: str  # goals, spent, clicks, shows, ctr, cpc, cost_per_goal
    operator: str  # equals, not_equals, greater_than, less_than, greater_or_equal, less_or_equal
    value: float
    order: int = 0


class DisableRuleCreate(BaseModel):
    """Создание нового правила отключения"""
    name: str
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    conditions: List[DisableRuleConditionModel] = []
    account_ids: List[int] = []  # ID кабинетов из таблицы accounts


class DisableRuleUpdate(BaseModel):
    """Обновление правила отключения"""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    conditions: Optional[List[DisableRuleConditionModel]] = None
    account_ids: Optional[List[int]] = None


class DisableRuleResponse(BaseModel):
    """Ответ с данными правила"""
    id: int
    name: str
    description: Optional[str]
    enabled: bool
    priority: int
    created_at: str
    updated_at: str
    conditions: List[dict]
    account_ids: List[int]
    account_names: List[str]

    class Config:
        from_attributes = True


# === Rate Limiting ===
RATE_LIMIT_PER_MINUTE = os.getenv("RATE_LIMIT_PER_MINUTE", "60")
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_PER_MINUTE}/minute"])


# === FastAPI App ===

app = FastAPI(
    title="VK Ads Manager API",
    description="Backend API для управления рекламными кампаниями VK",
    version="4.0.0-multitenancy"
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - настройка из переменных окружения для production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
origins = [origin.strip() for origin in ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Register auth router
app.include_router(auth_router)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    print("🔧 Initializing database...")
    init_db()
    print("✅ Database initialized")

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Logs directory: {LOGS_DIR}")

    # Recover running processes from DB
    print("🔍 Checking for running processes...")
    recover_processes_on_startup()
    print("✅ Process recovery complete")


# === Health Check ===

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "4.0.0-multitenancy", "database": "postgresql", "auth": "enabled"}


# === Dashboard ===

@app.get("/api/dashboard")
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


# === Accounts ===

@app.get("/api/accounts")
async def get_accounts_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all accounts for current user - returns dict with account names as keys"""
    accounts = crud.get_accounts(db, current_user.id)

    # Convert to dict format expected by frontend
    accounts_dict = {}
    for acc in accounts:
        accounts_dict[acc.name] = {
            "id": acc.id,  # DB id for LeadsTech cabinet linking
            "name": acc.name,
            "api": acc.api_token,
            "trigger": acc.client_id,
            "spent_limit_rub": 100.0
        }

    return {"accounts": accounts_dict}


@app.post("/api/accounts")
async def create_account(
    account: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new account for current user"""
    # Generate account_id from trigger or name hash
    account_id = account.trigger if account.trigger else abs(hash(account.name)) % 1000000000

    # Check if exists by name for this user
    existing_accounts = crud.get_accounts(db, current_user.id)
    for acc in existing_accounts:
        if acc.name == account.name:
            raise HTTPException(status_code=400, detail="Account with this name already exists")

    # Create
    new_account = crud.create_account(
        db,
        user_id=current_user.id,
        account_id=account_id,
        name=account.name,
        api_token=account.api,
        client_id=account.trigger if account.trigger else account_id
    )

    return {"message": "Account created successfully"}


@app.put("/api/accounts/{account_name}")
async def update_account_endpoint(
    account_name: str,
    account: AccountUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update account by name for current user"""
    # Find account by old name for this user
    accounts = crud.get_accounts(db, current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == account_name:
            target_account = acc
            break

    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update
    crud.update_account(
        db,
        user_id=current_user.id,
        account_id=target_account.account_id,
        name=account.name if account.name else target_account.name,
        api_token=account.api if account.api else target_account.api_token,
        client_id=account.trigger if account.trigger else target_account.client_id
    )

    return {"message": "Account updated successfully"}


@app.delete("/api/accounts/{account_name}")
async def delete_account_endpoint(
    account_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete account by name for current user"""
    # Find account by name for this user
    accounts = crud.get_accounts(db, current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == account_name:
            target_account = acc
            break

    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    crud.delete_account(db, current_user.id, target_account.account_id)
    return {"message": "Account deleted successfully"}


# === Settings ===

@app.get("/api/settings")
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
        })
    }


@app.put("/api/settings")
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

    return {"message": "Settings updated"}


@app.put("/api/settings/analysis")
async def update_analysis_settings(
    settings: AnalysisSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update analysis settings for current user"""
    crud.set_user_setting(db, current_user.id, 'analysis_settings', settings.model_dump())
    return {"message": "Analysis settings updated"}


@app.put("/api/settings/telegram")
async def update_telegram_settings(
    settings: TelegramSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update Telegram settings for current user"""
    crud.set_user_setting(db, current_user.id, 'telegram', settings.model_dump())
    return {"message": "Telegram settings updated"}


@app.put("/api/settings/scheduler")
async def update_scheduler_settings(
    settings: SchedulerSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scheduler settings for current user"""
    crud.set_user_setting(db, current_user.id, 'scheduler', settings.model_dump())
    return {"message": "Scheduler settings updated"}


@app.put("/api/settings/statistics_trigger")
async def update_statistics_trigger(
    settings: StatisticsTriggerSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update statistics trigger settings for current user"""
    crud.set_user_setting(db, current_user.id, 'statistics_trigger', settings.model_dump())
    return {"message": "Statistics trigger settings updated"}


# === Whitelist ===

@app.get("/api/whitelist")
async def get_whitelist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get whitelist for current user"""
    banner_ids = crud.get_whitelist(db, current_user.id)
    return {"banner_ids": banner_ids}


@app.put("/api/whitelist")
async def update_whitelist(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Replace entire whitelist for current user"""
    banner_ids = data.get("banner_ids", [])
    crud.replace_whitelist(db, current_user.id, banner_ids)
    return {"message": "Whitelist updated", "count": len(banner_ids)}


@app.post("/api/whitelist/bulk-add")
async def bulk_add_to_whitelist(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add multiple banners to whitelist without removing existing ones"""
    banner_ids = data.get("banner_ids", [])
    if not banner_ids:
        raise HTTPException(status_code=400, detail="banner_ids is required")
    
    result = crud.bulk_add_to_whitelist(db, current_user.id, banner_ids)
    return {
        "message": f"Добавлено {result['added']} баннеров, пропущено {result['skipped']} (уже в списке)",
        "added": result["added"],
        "skipped": result["skipped"],
        "total": result["total"]
    }


@app.post("/api/whitelist/bulk-remove")
async def bulk_remove_from_whitelist(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove multiple banners from whitelist"""
    banner_ids = data.get("banner_ids", [])
    if not banner_ids:
        raise HTTPException(status_code=400, detail="banner_ids is required")
    
    result = crud.bulk_remove_from_whitelist(db, current_user.id, banner_ids)
    return {
        "message": f"Удалено {result['removed']} баннеров из {result['total']}",
        "removed": result["removed"],
        "total": result["total"]
    }


@app.post("/api/whitelist/add/{banner_id}")
async def add_to_whitelist(
    banner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add banner to whitelist for current user"""
    crud.add_to_whitelist(db, current_user.id, banner_id)
    return {"message": "Banner added to whitelist"}


@app.delete("/api/whitelist/{banner_id}")
async def remove_from_whitelist(
    banner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove banner from whitelist for current user"""
    removed = crud.remove_from_whitelist(db, current_user.id, banner_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Banner not in whitelist")
    return {"message": "Banner removed from whitelist"}


# === Active Banners ===

@app.get("/api/banners/active")
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


# === Banner History ===

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


@app.get("/api/banners/history")
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
    page_size = min(page_size, 500)  # Max 500 per page
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


@app.get("/api/banners/disabled")
async def get_disabled_banners(
    page: int = 1,
    page_size: int = 500,
    account_name: Optional[str] = None,
    sort_by: str = 'created_at',
    sort_order: str = 'desc',
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recently disabled banners with full details, pagination and sorting for current user.
    Это главный endpoint для просмотра логов отключённых групп.
    """
    page_size = min(page_size, 500)  # Max 500 per page
    offset = (page - 1) * page_size
    
    # Validate sort parameters
    valid_sort_fields = ['created_at', 'spend', 'clicks', 'shows', 'ctr', 'conversions', 'cost_per_conversion', 'banner_id']
    if sort_by not in valid_sort_fields:
        sort_by = 'created_at'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    history, total = crud.get_disabled_banners(
        db,
        current_user.id,
        page_size, 
        offset,
        sort_by=sort_by,
        sort_order=sort_order
    )

    # Filter by account name if provided
    if account_name:
        history = [h for h in history if h.account_name == account_name]

    # Calculate summary statistics
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


@app.get("/api/banners/disabled/accounts")
async def get_disabled_banners_accounts(db: Session = Depends(get_db)):
    """Get all unique account names from disabled banners for filter dropdown"""
    account_names = crud.get_disabled_banners_account_names(db)
    return {"accounts": account_names}


# === Account Statistics ===

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


@app.get("/api/stats/accounts")
async def get_account_stats(
    account_name: Optional[str] = None,
    stats_date: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get account statistics with optional filters"""
    stats = crud.get_account_stats(db, account_name=account_name, stats_date=stats_date, limit=limit)
    return {
        "count": len(stats),
        "stats": [_format_account_stats(s) for s in stats]
    }


@app.get("/api/stats/accounts/today")
async def get_today_account_stats(
    account_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get today's account statistics"""
    stats = crud.get_today_stats(db, account_name=account_name)
    return {
        "count": len(stats),
        "date": datetime.utcnow().strftime('%Y-%m-%d'),
        "stats": [_format_account_stats(s) for s in stats]
    }


@app.get("/api/stats/accounts/range")
async def get_account_stats_range(
    date_from: str,
    date_to: str,
    account_name: Optional[str] = None,
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


@app.get("/api/stats/accounts/summary")
async def get_account_stats_summary(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get aggregated summary for last N days"""
    summary = crud.get_account_stats_summary(db, days=days)
    return summary


@app.get("/api/logs")
async def list_log_files():
    """
    List available log files.
    Returns list of log files with metadata for the frontend.
    """
    log_files = []

    # Scan logs directory
    if LOGS_DIR.exists():
        for log_file in LOGS_DIR.glob("*.log"):
            try:
                stat = log_file.stat()
                # Determine log type
                if "scheduler" in log_file.name.lower():
                    log_type = "scheduler"
                else:
                    log_type = "main"

                log_files.append({
                    "name": log_file.name,
                    "path": str(log_file),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": log_type
                })
            except Exception:
                continue

    # Sort by modification time (newest first)
    log_files.sort(key=lambda x: x["modified"], reverse=True)

    return log_files


# === Process Control ===

def is_process_running_by_db(process_name: str, db: Session, user_id: int = None) -> tuple[bool, Optional[int]]:
    """
    Check if process is running by checking DB state and verifying PID is alive.
    Returns (is_running, pid)
    Note: user_id is accepted for compatibility but processes are currently global
    """
    # Build unique process name with user_id if provided
    full_name = f"{process_name}_{user_id}" if user_id else process_name
    state = crud.get_process_state(db, full_name)

    if not state or state.status != 'running' or not state.pid:
        return False, None

    # Verify the PID is actually alive and it's our script
    script_name = Path(state.script_path).name if state.script_path else process_name

    if check_process_is_python_script(state.pid, script_name):
        return True, state.pid

    # PID is dead or not our process - update DB
    crud.set_process_stopped(db, full_name, error="Process no longer running")
    return False, None


@app.get("/api/control/status")
async def get_control_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get process control status for current user - checks actual process state via PID"""
    scheduler_running, scheduler_pid = is_process_running_by_db("scheduler", db, current_user.id)
    analysis_running, analysis_pid = is_process_running_by_db("analysis", db, current_user.id)
    bot_running, bot_pid = is_process_running_by_db("bot", db, current_user.id)

    return {
        "scheduler": {"running": scheduler_running, "pid": scheduler_pid},
        "analysis": {"running": analysis_running, "pid": analysis_pid},
        "bot": {"running": bot_running, "pid": bot_pid}
    }


@app.post("/api/control/scheduler/start")
async def start_scheduler(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start scheduler with persistent PID tracking for current user"""
    is_running, existing_pid = is_process_running_by_db("scheduler", db, current_user.id)

    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Scheduler already running (PID: {existing_pid})"
        )

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Open log files for stdout/stderr with user-specific filenames
        user_log_prefix = f"user_{current_user.id}"
        scheduler_stdout = open(LOGS_DIR / f"{user_log_prefix}_scheduler_stdout.log", "a", encoding="utf-8")
        scheduler_stderr = open(LOGS_DIR / f"{user_log_prefix}_scheduler_stderr.log", "a", encoding="utf-8")

        # Pass user_id as environment variable to the scheduler
        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)

        process = subprocess.Popen(
            [sys.executable, str(SCHEDULER_SCRIPT)],
            stdout=scheduler_stdout,
            stderr=scheduler_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
            env=env
        )

        # Save to DB for persistence with user-specific name
        process_name = f"scheduler_{current_user.id}"
        crud.set_process_running(db, process_name, process.pid, str(SCHEDULER_SCRIPT), user_id=current_user.id)

        # Also keep in memory cache for current session
        running_processes[process_name] = process

        print(f"✅ Scheduler started with PID: {process.pid} for user {current_user.username}")
        return {"message": "Scheduler started", "pid": process.pid}
    except Exception as e:
        print(f"❌ Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}")


@app.post("/api/control/scheduler/stop")
async def stop_scheduler(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop scheduler for current user - works even after API restart"""
    is_running, pid = is_process_running_by_db("scheduler", db, current_user.id)

    if not is_running:
        raise HTTPException(status_code=400, detail="Scheduler not running")

    # Kill by PID (works even if not in memory cache)
    success = kill_process_by_pid(pid)

    if success:
        process_name = f"scheduler_{current_user.id}"
        crud.set_process_stopped(db, process_name)

        # Remove from memory cache if present
        if process_name in running_processes:
            del running_processes[process_name]

        print(f"✅ Scheduler stopped (PID: {pid}) for user {current_user.username}")
        return {"message": "Scheduler stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler (PID: {pid})")


@app.post("/api/control/analysis/start")
async def start_analysis(db: Session = Depends(get_db)):
    """Start analysis with persistent PID tracking"""
    is_running, existing_pid = is_process_running_by_db("analysis", db)

    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Analysis already running (PID: {existing_pid})"
        )

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Open log files for stdout/stderr
        analysis_stdout = open(LOGS_DIR / "analysis_stdout.log", "a", encoding="utf-8")
        analysis_stderr = open(LOGS_DIR / "analysis_stderr.log", "a", encoding="utf-8")

        process = subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            stdout=analysis_stdout,
            stderr=analysis_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True
        )

        # Save to DB for persistence
        crud.set_process_running(db, "analysis", process.pid, str(MAIN_SCRIPT))

        # Also keep in memory cache
        running_processes["analysis"] = process

        print(f"✅ Analysis started with PID: {process.pid}")
        return {"message": "Analysis started", "pid": process.pid}
    except Exception as e:
        print(f"❌ Failed to start analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


@app.post("/api/control/analysis/stop")
async def stop_analysis(db: Session = Depends(get_db)):
    """Stop analysis - works even after API restart"""
    is_running, pid = is_process_running_by_db("analysis", db)

    if not is_running:
        raise HTTPException(status_code=400, detail="Analysis not running")

    success = kill_process_by_pid(pid)

    if success:
        crud.set_process_stopped(db, "analysis")

        if "analysis" in running_processes:
            del running_processes["analysis"]

        print(f"✅ Analysis stopped (PID: {pid})")
        return {"message": "Analysis stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop analysis (PID: {pid})")


@app.post("/api/control/bot/start")
async def start_bot(db: Session = Depends(get_db)):
    """Start Telegram bot with persistent PID tracking"""
    is_running, existing_pid = is_process_running_by_db("bot", db)

    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Bot already running (PID: {existing_pid})"
        )

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Open log files for stdout/stderr
        bot_stdout = open(LOGS_DIR / "bot_stdout.log", "a", encoding="utf-8")
        bot_stderr = open(LOGS_DIR / "bot_stderr.log", "a", encoding="utf-8")

        process = subprocess.Popen(
            [sys.executable, str(BOT_SCRIPT)],
            stdout=bot_stdout,
            stderr=bot_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True
        )

        # Save to DB for persistence
        crud.set_process_running(db, "bot", process.pid, str(BOT_SCRIPT))

        # Also keep in memory cache
        running_processes["bot"] = process

        print(f"✅ Bot started with PID: {process.pid}")
        return {"message": "Bot started", "pid": process.pid}
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")


@app.post("/api/control/bot/stop")
async def stop_bot(db: Session = Depends(get_db)):
    """Stop Telegram bot - works even after API restart"""
    is_running, pid = is_process_running_by_db("bot", db)

    if not is_running:
        raise HTTPException(status_code=400, detail="Bot not running")

    success = kill_process_by_pid(pid)

    if success:
        crud.set_process_stopped(db, "bot")

        if "bot" in running_processes:
            del running_processes["bot"]

        print(f"✅ Bot stopped (PID: {pid})")
        return {"message": "Bot stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop bot (PID: {pid})")


@app.post("/api/control/kill-all")
async def kill_all_processes(db: Session = Depends(get_db)):
    """Kill all running processes - uses DB for persistence"""
    killed = []
    errors = []

    process_states = crud.get_all_process_states(db)

    for state in process_states:
        if state.status == 'running' and state.pid:
            if kill_process_by_pid(state.pid):
                crud.set_process_stopped(db, state.name)
                killed.append({"name": state.name, "pid": state.pid})

                if state.name in running_processes:
                    del running_processes[state.name]
            else:
                errors.append({"name": state.name, "pid": state.pid})

    print(f"✅ Killed {len(killed)} processes: {[k['name'] for k in killed]}")

    return {
        "message": f"Killed {len(killed)} processes",
        "killed": killed,
        "errors": errors if errors else None
    }


# === Logs ===

@app.get("/api/logs/{log_type}/{filename}")
async def get_log_content(log_type: str, filename: str, tail: int = 500):
    """Get log file contents"""
    # Validate log type
    if log_type not in ["main", "scheduler"]:
        raise HTTPException(status_code=404, detail="Log type not found")

    # Build file path safely
    log_file = LOGS_DIR / filename

    # Security check - ensure file is within LOGS_DIR
    try:
        log_file.resolve().relative_to(LOGS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not log_file.exists():
        return {"filename": filename, "content": "", "total_lines": 0}

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            content = ''.join(all_lines[-tail:])
            return {
                "filename": filename,
                "content": content,
                "total_lines": len(all_lines)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")


# === LeadsTech Config ===

@app.get("/api/leadstech/config")
async def get_leadstech_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get LeadsTech configuration"""
    config = crud.get_leadstech_config(db, user_id=current_user.id)
    if not config:
        return {"configured": False}

    return {
        "configured": True,
        "login": config.login,
        "base_url": config.base_url,
        "lookback_days": config.lookback_days,
        "banner_sub_field": config.banner_sub_field,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None
    }


@app.put("/api/leadstech/config")
async def update_leadstech_config(
    config: LeadsTechConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update LeadsTech configuration"""
    existing_config = crud.get_leadstech_config(db)
    
    # If config exists and no password provided, use existing password
    password = config.password
    if not password:
        if existing_config:
            password = existing_config.password
        else:
            raise HTTPException(status_code=400, detail="Password is required for new configuration")
    
    result = crud.create_or_update_leadstech_config(
        db,
        login=config.login,
        password=password,
        user_id=current_user.id,
        base_url=config.base_url,
        lookback_days=config.lookback_days,
        banner_sub_field=config.banner_sub_field
    )
    return {"message": "LeadsTech configuration updated", "id": result.id}


@app.delete("/api/leadstech/config")
async def delete_leadstech_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete LeadsTech configuration"""
    if crud.delete_leadstech_config(db, user_id=current_user.id):
        return {"message": "LeadsTech configuration deleted"}
    raise HTTPException(status_code=404, detail="LeadsTech configuration not found")


# === LeadsTech Cabinets ===

@app.get("/api/leadstech/cabinets")
async def get_leadstech_cabinets(
    enabled_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all LeadsTech cabinets with their linked accounts"""
    cabinets = crud.get_leadstech_cabinets(db, user_id=current_user.id, enabled_only=enabled_only)

    result = []
    for cab in cabinets:
        account = cab.account
        result.append({
            "id": cab.id,
            "account_id": cab.account_id,
            "account_name": account.name if account else None,
            "account_api_token": account.api_token if account else None,
            "leadstech_label": cab.leadstech_label,
            "enabled": cab.enabled,
            "created_at": cab.created_at.isoformat() if cab.created_at else None,
            "updated_at": cab.updated_at.isoformat() if cab.updated_at else None
        })

    return {"cabinets": result, "count": len(result)}


@app.post("/api/leadstech/cabinets")
async def create_leadstech_cabinet(
    cabinet: LeadsTechCabinetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update LeadsTech cabinet mapping"""
    result = crud.create_leadstech_cabinet(
        db,
        account_id=cabinet.account_id,
        leadstech_label=cabinet.leadstech_label,
        enabled=cabinet.enabled,
        user_id=current_user.id
    )
    return {"message": "LeadsTech cabinet created/updated", "id": result.id}


@app.put("/api/leadstech/cabinets/{cabinet_id}")
async def update_leadstech_cabinet(
    cabinet_id: int,
    cabinet: LeadsTechCabinetUpdate,
    db: Session = Depends(get_db)
):
    """Update LeadsTech cabinet"""
    result = crud.update_leadstech_cabinet(
        db,
        cabinet_id=cabinet_id,
        leadstech_label=cabinet.leadstech_label,
        enabled=cabinet.enabled
    )
    if not result:
        raise HTTPException(status_code=404, detail="LeadsTech cabinet not found")
    return {"message": "LeadsTech cabinet updated"}


@app.delete("/api/leadstech/cabinets/{cabinet_id}")
async def delete_leadstech_cabinet(cabinet_id: int, db: Session = Depends(get_db)):
    """Delete LeadsTech cabinet"""
    if crud.delete_leadstech_cabinet(db, cabinet_id):
        return {"message": "LeadsTech cabinet deleted"}
    raise HTTPException(status_code=404, detail="LeadsTech cabinet not found")


# === LeadsTech Analysis ===

@app.get("/api/leadstech/analysis/results")
async def get_leadstech_analysis_results(
    cabinet_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    sort_by: str = 'created_at',
    sort_order: str = 'desc',
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get LeadsTech analysis results with pagination and sorting"""
    page_size = min(page_size, 500)  # Max 500 per page
    offset = (page - 1) * page_size
    
    # Validate sort parameters
    valid_sort_fields = ['created_at', 'roi_percent', 'profit', 'vk_spent', 'lt_revenue', 'banner_id']
    if sort_by not in valid_sort_fields:
        sort_by = 'created_at'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    results, total = crud.get_leadstech_analysis_results(
        db,
        cabinet_name=cabinet_name,
        limit=page_size,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        user_id=current_user.id
    )
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    formatted = []
    for r in results:
        formatted.append({
            "id": r.id,
            "cabinet_name": r.cabinet_name,
            "leadstech_label": r.leadstech_label,
            "banner_id": r.banner_id,
            "vk_spent": r.vk_spent,
            "lt_revenue": r.lt_revenue,
            "profit": r.profit,
            "roi_percent": r.roi_percent,
            "lt_clicks": r.lt_clicks,
            "lt_conversions": r.lt_conversions,
            "lt_approved": r.lt_approved,
            "lt_inprogress": r.lt_inprogress,
            "lt_rejected": r.lt_rejected,
            "date_from": r.date_from,
            "date_to": r.date_to,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })

    return {
        "results": formatted, 
        "count": len(formatted),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@app.get("/api/leadstech/analysis/cabinets")
async def get_leadstech_analysis_cabinets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all unique cabinet names from analysis results for filter dropdown"""
    cabinet_names = crud.get_leadstech_analysis_cabinet_names(db, user_id=current_user.id)
    return {"cabinets": cabinet_names}


@app.post("/api/leadstech/analysis/start")
async def start_leadstech_analysis(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start LeadsTech analysis for enabled cabinets"""
    # Check if config exists
    config = crud.get_leadstech_config(db)
    if not config:
        raise HTTPException(status_code=400, detail="LeadsTech not configured. Please configure login/password first.")

    # Check if there are enabled cabinets for this user
    cabinets = crud.get_leadstech_cabinets(db, user_id=current_user.id, enabled_only=True)
    if not cabinets:
        raise HTTPException(status_code=400, detail="No enabled LeadsTech cabinets. Please configure at least one cabinet.")

    # Check if analysis is already running
    is_running, existing_pid = is_process_running_by_db("leadstech_analysis", db, current_user.id)
    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"LeadsTech analysis already running (PID: {existing_pid})"
        )

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Path to the leadstech analyzer script
    leadstech_script = PROJECT_ROOT / "backend" / "leadstech" / "analyzer.py"
    if IN_DOCKER:
        leadstech_script = PROJECT_ROOT / "leadstech" / "analyzer.py"

    try:
        # Open log files
        lt_stdout = open(LOGS_DIR / "leadstech_stdout.log", "a", encoding="utf-8")
        lt_stderr = open(LOGS_DIR / "leadstech_stderr.log", "a", encoding="utf-8")

        # Pass user_id as environment variable
        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)

        process = subprocess.Popen(
            [sys.executable, str(leadstech_script)],
            stdout=lt_stdout,
            stderr=lt_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
            env=env
        )

        # Save to DB for persistence
        process_name = f"leadstech_analysis_{current_user.id}"
        crud.set_process_running(db, process_name, process.pid, str(leadstech_script), user_id=current_user.id)

        print(f"✅ LeadsTech analysis started with PID: {process.pid}")
        return {
            "message": "LeadsTech analysis started",
            "pid": process.pid,
            "cabinets_count": len(cabinets)
        }
    except Exception as e:
        print(f"❌ Failed to start LeadsTech analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


@app.post("/api/leadstech/analysis/stop")
async def stop_leadstech_analysis(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop running LeadsTech analysis"""
    is_running, pid = is_process_running_by_db("leadstech_analysis", db, current_user.id)

    if not is_running:
        raise HTTPException(status_code=400, detail="LeadsTech analysis not running")

    success = kill_process_by_pid(pid)

    if success:
        process_name = f"leadstech_analysis_{current_user.id}"
        crud.set_process_stopped(db, process_name)
        print(f"✅ LeadsTech analysis stopped (PID: {pid})")
        return {"message": "LeadsTech analysis stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop analysis (PID: {pid})")


@app.get("/api/leadstech/analysis/status")
async def get_leadstech_analysis_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get LeadsTech analysis process status"""
    is_running, pid = is_process_running_by_db("leadstech_analysis", db, current_user.id)
    return {"running": is_running, "pid": pid}


@app.get("/api/leadstech/analysis/logs")
async def get_leadstech_analysis_logs(lines: int = 100):
    """Get last N lines from LeadsTech analysis logs"""
    try:
        # Get latest analyzer log file
        log_files = sorted(LOGS_DIR.glob("leadstech_analyzer_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not log_files:
            # Fallback to stderr log
            stderr_log = LOGS_DIR / "leadstech_stderr.log"
            if stderr_log.exists():
                with open(stderr_log, 'r', encoding='utf-8') as f:
                    content = f.readlines()
                    return {"logs": ''.join(content[-lines:]), "source": "stderr"}
            return {"logs": "No logs found", "source": "none"}
        
        # Read latest analyzer log
        latest_log = log_files[0]
        with open(latest_log, 'r', encoding='utf-8') as f:
            content = f.readlines()
            return {"logs": ''.join(content[-lines:]), "source": str(latest_log.name)}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")


@app.post("/api/leadstech/whitelist-profitable")
async def whitelist_profitable_banners(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start background process to add profitable banners to whitelist and enable them.
    """
    roi_threshold = data.get("roi_threshold")
    enable_banners = data.get("enable_banners", True)

    if roi_threshold is None:
        raise HTTPException(status_code=400, detail="roi_threshold is required")

    try:
        roi_threshold = float(roi_threshold)
    except ValueError:
        raise HTTPException(status_code=400, detail="roi_threshold must be a number")

    # Check if already running
    is_running, existing_pid = is_process_running_by_db("whitelist_worker", db, current_user.id)
    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Whitelist process already running (PID: {existing_pid})"
        )

    # Path to worker script
    worker_script = PROJECT_ROOT / "backend" / "leadstech" / "whitelist_worker.py"
    if IN_DOCKER:
        worker_script = PROJECT_ROOT / "leadstech" / "whitelist_worker.py"

    try:
        # Ensure logs dir exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        stdout = open(LOGS_DIR / "whitelist_stdout.log", "a", encoding="utf-8")
        stderr = open(LOGS_DIR / "whitelist_stderr.log", "a", encoding="utf-8")

        cmd = [
            sys.executable, 
            str(worker_script),
            "--roi", str(roi_threshold),
            "--enable", str(enable_banners).lower()
        ]

        # Pass user_id as environment variable
        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)

        process = subprocess.Popen(
            cmd,
            stdout=stdout,
            stderr=stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
            env=env
        )

        process_name = f"whitelist_worker_{current_user.id}"
        crud.set_process_running(db, process_name, process.pid, str(worker_script), user_id=current_user.id)

        return {
            "message": "Whitelist process started",
            "pid": process.pid
        }
    except Exception as e:
        print(f"❌ Failed to start whitelist worker: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start worker: {str(e)}")


@app.get("/api/leadstech/whitelist-profitable/status")
async def get_whitelist_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get whitelist worker status"""
    is_running, pid = is_process_running_by_db("whitelist_worker", db, current_user.id)
    return {"running": is_running, "pid": pid}


@app.post("/api/leadstech/whitelist-profitable/stop")
async def stop_whitelist_worker(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop whitelist worker"""
    is_running, pid = is_process_running_by_db("whitelist_worker", db, current_user.id)

    if not is_running:
        raise HTTPException(status_code=400, detail="Whitelist worker not running")

    success = kill_process_by_pid(pid)

    if success:
        process_name = f"whitelist_worker_{current_user.id}"
        crud.set_process_stopped(db, process_name)
        return {"message": "Worker stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop worker (PID: {pid})")


# ===== Scaling API =====

class ScalingConditionModel(BaseModel):
    metric: str  # spent, shows, clicks, goals, cost_per_goal
    operator: str  # >, <, >=, <=, ==, !=
    value: float


class ScalingConfigCreate(BaseModel):
    name: str
    schedule_time: str = "08:00"
    account_id: Optional[int] = None
    account_ids: Optional[List[int]] = None  # Multiple accounts selection
    new_budget: Optional[float] = None
    auto_activate: bool = False
    lookback_days: int = 7
    duplicates_count: int = 1  # Number of duplicates per group
    enabled: bool = False
    conditions: List[ScalingConditionModel] = []


class ScalingConfigUpdate(BaseModel):
    name: Optional[str] = None
    schedule_time: Optional[str] = None
    account_id: Optional[int] = None
    account_ids: Optional[List[int]] = None  # Multiple accounts selection
    new_budget: Optional[float] = None
    auto_activate: Optional[bool] = None
    lookback_days: Optional[int] = None
    duplicates_count: Optional[int] = None  # Number of duplicates per group
    enabled: Optional[bool] = None
    conditions: Optional[List[ScalingConditionModel]] = None


class ManualDuplicateRequest(BaseModel):
    account_name: str
    ad_group_ids: List[int]  # Multiple group IDs
    new_budget: Optional[float] = None
    auto_activate: bool = False
    duplicates_count: int = 1  # Number of duplicates per group


@app.get("/api/scaling/configs")
async def get_scaling_configs_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all scaling configurations"""
    configs = crud.get_scaling_configs(db, user_id=current_user.id)
    result = []
    
    for config in configs:
        conditions = crud.get_scaling_conditions(db, config.id)
        account_ids = crud.get_scaling_config_account_ids(db, config.id)
        result.append({
            "id": config.id,
            "name": config.name,
            "enabled": config.enabled,
            "schedule_time": config.schedule_time,
            "account_id": config.account_id,
            "account_ids": account_ids,
            "new_budget": config.new_budget,
            "auto_activate": config.auto_activate,
            "lookback_days": config.lookback_days,
            "duplicates_count": config.duplicates_count or 1,
            "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
            "created_at": config.created_at.isoformat(),
            "conditions": [
                {
                    "id": c.id,
                    "metric": c.metric,
                    "operator": c.operator,
                    "value": c.value
                }
                for c in conditions
            ]
        })
    
    return result


@app.post("/api/scaling/configs")
async def create_scaling_config_endpoint(
    data: ScalingConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new scaling configuration"""
    config = crud.create_scaling_config(
        db,
        user_id=current_user.id,
        name=data.name,
        schedule_time=data.schedule_time,
        account_id=data.account_id,
        account_ids=data.account_ids,
        new_budget=data.new_budget,
        auto_activate=data.auto_activate,
        lookback_days=data.lookback_days,
        duplicates_count=data.duplicates_count,
        enabled=data.enabled
    )
    
    # Add conditions
    if data.conditions:
        crud.set_scaling_conditions(
            db,
            config.id,
            [c.model_dump() for c in data.conditions]
        )
    
    return {"id": config.id, "message": "Configuration created"}


@app.put("/api/scaling/configs/{config_id}")
async def update_scaling_config_endpoint(
    config_id: int,
    data: ScalingConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scaling configuration"""
    config = crud.update_scaling_config(
        db,
        config_id,
        name=data.name,
        schedule_time=data.schedule_time,
        account_id=data.account_id,
        account_ids=data.account_ids,
        new_budget=data.new_budget,
        auto_activate=data.auto_activate,
        lookback_days=data.lookback_days,
        duplicates_count=data.duplicates_count,
        enabled=data.enabled
    )
    
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    # Update conditions if provided
    if data.conditions is not None:
        crud.set_scaling_conditions(
            db,
            config_id,
            [c.model_dump() for c in data.conditions]
        )
    
    return {"message": "Configuration updated"}


@app.delete("/api/scaling/configs/{config_id}")
async def delete_scaling_config_endpoint(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete scaling configuration"""
    if not crud.delete_scaling_config(db, config_id):
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    return {"message": "Configuration deleted"}


@app.get("/api/scaling/logs")
async def get_scaling_logs_endpoint(
    config_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get scaling logs"""
    logs, total = crud.get_scaling_logs(db, user_id=current_user.id, config_id=config_id, limit=limit, offset=offset)
    
    return {
        "items": [
            {
                "id": log.id,
                "config_id": log.config_id,
                "config_name": log.config_name,
                "account_name": log.account_name,
                "original_group_id": log.original_group_id,
                "original_group_name": log.original_group_name,
                "new_group_id": log.new_group_id,
                "new_group_name": log.new_group_name,
                "stats_snapshot": log.stats_snapshot,
                "success": log.success,
                "error_message": log.error_message,
                "total_banners": log.total_banners,
                "duplicated_banners": log.duplicated_banners,
                "duplicated_banner_ids": log.duplicated_banner_ids,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "total": total
    }


@app.get("/api/scaling/ad-groups/{account_name}")
async def get_account_ad_groups_with_stats(
    account_name: str,
    lookback_days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get ad groups with statistics for an account"""
    from datetime import datetime, timedelta
    from utils.vk_api import get_ad_groups_with_stats

    # Find account
    accounts = crud.get_accounts(db, user_id=current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == account_name:
            target_account = acc
            break
    
    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Calculate date range
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    base_url = "https://ads.vk.com/api/v2"
    
    try:
        groups = get_ad_groups_with_stats(
            token=target_account.api_token,
            base_url=base_url,
            date_from=date_from,
            date_to=date_to
        )
        
        return {
            "account_name": account_name,
            "date_from": date_from,
            "date_to": date_to,
            "groups": groups
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ad groups: {str(e)}")


@app.post("/api/scaling/duplicate")
async def manual_duplicate_ad_group(
    data: ManualDuplicateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually duplicate ad groups (supports multiple groups and multiple copies)"""
    from utils.vk_api import duplicate_ad_group_full

    # Find account
    accounts = crud.get_accounts(db, user_id=current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == data.account_name:
            target_account = acc
            break
    
    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    base_url = "https://ads.vk.com/api/v2"
    duplicates_count = max(1, min(data.duplicates_count, 10))  # Limit 1-10 copies
    
    results = {
        "total_groups": len(data.ad_group_ids),
        "duplicates_per_group": duplicates_count,
        "total_operations": len(data.ad_group_ids) * duplicates_count,
        "completed": 0,
        "success": [],
        "errors": []
    }
    
    for group_id in data.ad_group_ids:
        for copy_num in range(duplicates_count):
            try:
                result = duplicate_ad_group_full(
                    token=target_account.api_token,
                    base_url=base_url,
                    ad_group_id=group_id,
                    new_name=None,  # Auto-generate
                    new_budget=data.new_budget,
                    auto_activate=data.auto_activate,
                    rate_limit_delay=0.03
                )
                
                # Log the operation
                # Extract banner IDs for logging
                banner_ids_data = None
                if result.get("duplicated_banners"):
                    banner_ids_data = [
                        {
                            "original_id": b.get("original_id"),
                            "new_id": b.get("new_id"),
                            "name": b.get("name")
                        }
                        for b in result.get("duplicated_banners", [])
                    ]

                crud.create_scaling_log(
                    db,
                    user_id=current_user.id,
                    config_id=None,
                    config_name="Manual",
                    account_name=data.account_name,
                    original_group_id=group_id,
                    original_group_name=result.get("original_group_name"),
                    new_group_id=result.get("new_group_id"),
                    new_group_name=result.get("new_group_name"),
                    stats_snapshot=None,
                    success=result.get("success", False),
                    error_message=result.get("error"),
                    total_banners=result.get("total_banners", 0),
                    duplicated_banners=len(result.get("duplicated_banners", [])),
                    duplicated_banner_ids=banner_ids_data
                )
                
                if result.get("success"):
                    results["success"].append({
                        "original_group_id": group_id,
                        "original_group_name": result.get("original_group_name"),
                        "new_group_id": result.get("new_group_id"),
                        "new_group_name": result.get("new_group_name"),
                        "copy_number": copy_num + 1,
                        "banners_copied": len(result.get("duplicated_banners", []))
                    })
                else:
                    results["errors"].append({
                        "original_group_id": group_id,
                        "copy_number": copy_num + 1,
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                crud.create_scaling_log(
                    db,
                    user_id=current_user.id,
                    config_id=None,
                    config_name="Manual",
                    account_name=data.account_name,
                    original_group_id=group_id,
                    original_group_name=None,
                    success=False,
                    error_message=str(e)
                )
                results["errors"].append({
                    "original_group_id": group_id,
                    "copy_number": copy_num + 1,
                    "error": str(e)
                })
            
            results["completed"] += 1
    
    return results

@app.post("/api/scaling/run/{config_id}")
async def run_scaling_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually run a scaling configuration"""
    from datetime import datetime, timedelta
    from utils.vk_api import get_ad_groups_with_stats, duplicate_ad_group_full

    config = crud.get_scaling_config_by_id(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    conditions = crud.get_scaling_conditions(db, config_id)
    if not conditions:
        raise HTTPException(status_code=400, detail="No conditions defined for this configuration")
    
    # Get target accounts (priority: account_ids > account_id > all accounts)
    account_ids = crud.get_scaling_config_account_ids(db, config_id)

    if account_ids:
        # Use multiple selected accounts
        all_accounts = crud.get_accounts(db, user_id=current_user.id)
        accounts = [a for a in all_accounts if a.id in account_ids]
    elif config.account_id:
        # Fallback to single account (deprecated)
        all_accounts = crud.get_accounts(db, user_id=current_user.id)
        accounts = [a for a in all_accounts if a.id == config.account_id]
    else:
        # All accounts
        accounts = crud.get_accounts(db, user_id=current_user.id)
    
    if not accounts:
        raise HTTPException(status_code=404, detail="No accounts found")
    
    # Calculate date range
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=config.lookback_days)).strftime("%Y-%m-%d")
    
    base_url = "https://ads.vk.com/api/v2"
    
    results = {
        "duplicated": [],
        "skipped": [],
        "errors": []
    }
    
    print(f"")
    print(f"{'='*80}")
    print(f"🚀 ЗАПУСК АВТОМАТИЧЕСКОГО МАСШТАБИРОВАНИЯ")
    print(f"   Конфиг: {config.name}")
    print(f"   Условия: {[(c.metric, c.operator, c.value) for c in conditions]}")
    print(f"   Дублей на группу: {config.duplicates_count or 1}")
    print(f"   Период: {date_from} - {date_to}")
    print(f"   Аккаунтов: {len(accounts)}")
    print(f"{'='*80}")
    
    for account in accounts:
        try:
            print(f"\n📊 Обрабатываем аккаунт: {account.name}")
            
            # Get groups with stats
            groups = get_ad_groups_with_stats(
                token=account.api_token,
                base_url=base_url,
                date_from=date_from,
                date_to=date_to
            )
            
            print(f"   Найдено групп: {len(groups)}")
            
            for group in groups:
                group_id = group.get("id")
                group_name = group.get("name", "Unknown")
                stats = group.get("stats", {})
                
                print(f"\n   📋 Группа {group_id}: {group_name}")
                print(f"      Статистика: spent={stats.get('spent')}, goals={stats.get('goals')}, cost_per_goal={stats.get('cost_per_goal')}")
                
                # Check conditions
                conditions_met = crud.check_group_conditions(stats, conditions)
                print(f"      Условия выполнены: {conditions_met}")
                
                if conditions_met:
                    # Duplicate the group N times (based on duplicates_count)
                    duplicates_count = config.duplicates_count or 1
                    print(f"      ✅ Запускаем дублирование x{duplicates_count}")
                    
                    for dup_num in range(1, duplicates_count + 1):
                        try:
                            print(f"🔄 Дублирование группы {group_id} ({dup_num}/{duplicates_count})")
                            
                            result = duplicate_ad_group_full(
                                token=account.api_token,
                                base_url=base_url,
                                ad_group_id=group_id,
                                new_name=None,  # Auto-generate name
                                new_budget=config.new_budget,
                                auto_activate=config.auto_activate,
                                rate_limit_delay=0.03
                            )
                            
                            # Log the operation
                            # Extract banner IDs for logging
                            banner_ids_data = None
                            if result.get("duplicated_banners"):
                                banner_ids_data = [
                                    {
                                        "original_id": b.get("original_id"),
                                        "new_id": b.get("new_id"),
                                        "name": b.get("name")
                                    }
                                    for b in result.get("duplicated_banners", [])
                                ]

                            crud.create_scaling_log(
                                db,
                                user_id=current_user.id,
                                config_id=config.id,
                                config_name=config.name,
                                account_name=account.name,
                                original_group_id=group_id,
                                original_group_name=group_name,
                                new_group_id=result.get("new_group_id"),
                                new_group_name=result.get("new_group_name"),
                                stats_snapshot=stats,
                                success=result.get("success", False),
                                error_message=result.get("error"),
                                total_banners=result.get("total_banners", 0),
                                duplicated_banners=len(result.get("duplicated_banners", [])),
                                duplicated_banner_ids=banner_ids_data
                            )
                            
                            if result.get("success"):
                                results["duplicated"].append({
                                    "account": account.name,
                                    "original_group_id": group_id,
                                    "original_group_name": group_name,
                                    "new_group_id": result.get("new_group_id"),
                                    "new_group_name": result.get("new_group_name"),
                                    "banners_copied": len(result.get("duplicated_banners", [])),
                                    "duplicate_number": dup_num
                                })
                            else:
                                results["errors"].append({
                                    "account": account.name,
                                    "group_id": group_id,
                                    "group_name": group_name,
                                    "error": result.get("error"),
                                    "duplicate_number": dup_num
                                })
                                
                        except Exception as e:
                            results["errors"].append({
                                "account": account.name,
                                "group_id": group_id,
                                "group_name": group_name,
                                "error": str(e),
                                "duplicate_number": dup_num
                            })
                else:
                    results["skipped"].append({
                        "account": account.name,
                        "group_id": group_id,
                        "group_name": group_name,
                        "stats": stats,
                        "reason": "Conditions not met"
                    })
                    
        except Exception as e:
            results["errors"].append({
                "account": account.name,
                "error": str(e)
            })
    
    # Update last run time
    crud.update_scaling_config_last_run(db, config_id)
    
    # Логируем результат запуска (даже если ничего не продублировано)
    total_checked = len(results["duplicated"]) + len(results["skipped"]) + len(results["errors"])
    if len(results["duplicated"]) == 0:
        # Создаём запись о запуске без дублирования
        crud.create_scaling_log(
            db,
            user_id=current_user.id,
            config_id=config.id,
            config_name=config.name,
            account_name=", ".join([a.name for a in accounts]),
            original_group_id=0,
            original_group_name=f"Проверено групп: {total_checked}",
            new_group_id=None,
            new_group_name=None,
            stats_snapshot={"checked": total_checked, "skipped": len(results["skipped"])},
            success=True,
            error_message="Нет групп, соответствующих условиям",
            total_banners=0,
            duplicated_banners=0
        )
    
    print(f"\n{'='*80}")
    print(f"✅ МАСШТАБИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"   Проверено групп: {total_checked}")
    print(f"   Продублировано: {len(results['duplicated'])}")
    print(f"   Пропущено: {len(results['skipped'])}")
    print(f"   Ошибок: {len(results['errors'])}")
    print(f"{'='*80}\n")
    
    return {
        "config_name": config.name,
        "date_from": date_from,
        "date_to": date_to,
        "results": results
    }


# ===== Auto-Disable API =====

class AutoDisableConditionModel(BaseModel):
    metric: str  # spent, shows, clicks, goals, cost_per_goal, ctr
    operator: str  # >, <, >=, <=, ==
    value: float


class AutoDisableConfigCreate(BaseModel):
    name: str
    lookback_days: int = 10
    account_ids: Optional[List[int]] = None  # Multiple accounts selection
    enabled: bool = False
    conditions: List[AutoDisableConditionModel] = []


class AutoDisableConfigUpdate(BaseModel):
    name: Optional[str] = None
    lookback_days: Optional[int] = None
    account_ids: Optional[List[int]] = None  # Multiple accounts selection
    enabled: Optional[bool] = None
    conditions: Optional[List[AutoDisableConditionModel]] = None


@app.get("/api/auto-disable/configs")
async def get_auto_disable_configs_endpoint(db: Session = Depends(get_db)):
    """Get all auto-disable configurations"""
    configs = crud.get_auto_disable_configs(db)
    result = []
    
    for config in configs:
        conditions = crud.get_auto_disable_conditions(db, config.id)
        account_ids = crud.get_auto_disable_config_account_ids(db, config.id)
        result.append({
            "id": config.id,
            "name": config.name,
            "enabled": config.enabled,
            "lookback_days": config.lookback_days,
            "account_ids": account_ids,
            "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
            "created_at": config.created_at.isoformat(),
            "conditions": [
                {
                    "id": c.id,
                    "metric": c.metric,
                    "operator": c.operator,
                    "value": c.value
                }
                for c in conditions
            ]
        })
    
    return result


@app.post("/api/auto-disable/configs")
async def create_auto_disable_config_endpoint(data: AutoDisableConfigCreate, db: Session = Depends(get_db)):
    """Create new auto-disable configuration"""
    config = crud.create_auto_disable_config(
        db,
        name=data.name,
        enabled=data.enabled,
        lookback_days=data.lookback_days,
        account_ids=data.account_ids
    )
    
    # Add conditions
    if data.conditions:
        crud.set_auto_disable_conditions(
            db,
            config.id,
            [c.model_dump() for c in data.conditions]
        )
    
    return {"id": config.id, "message": "Configuration created"}


@app.put("/api/auto-disable/configs/{config_id}")
async def update_auto_disable_config_endpoint(config_id: int, data: AutoDisableConfigUpdate, db: Session = Depends(get_db)):
    """Update auto-disable configuration"""
    config = crud.update_auto_disable_config(
        db,
        config_id,
        name=data.name,
        enabled=data.enabled,
        lookback_days=data.lookback_days,
        account_ids=data.account_ids
    )
    
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    # Update conditions if provided
    if data.conditions is not None:
        crud.set_auto_disable_conditions(
            db,
            config_id,
            [c.model_dump() for c in data.conditions]
        )
    
    return {"message": "Configuration updated"}


@app.delete("/api/auto-disable/configs/{config_id}")
async def delete_auto_disable_config_endpoint(config_id: int, db: Session = Depends(get_db)):
    """Delete auto-disable configuration"""
    if not crud.delete_auto_disable_config(db, config_id):
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    return {"message": "Configuration deleted"}


@app.get("/api/auto-disable/logs")
async def get_auto_disable_logs_endpoint(
    config_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get auto-disable logs"""
    logs, total = crud.get_auto_disable_logs(db, config_id, limit, offset)
    
    return {
        "items": [
            {
                "id": log.id,
                "config_id": log.config_id,
                "config_name": log.config_name,
                "account_name": log.account_name,
                "banner_id": log.banner_id,
                "banner_name": log.banner_name,
                "ad_group_id": log.ad_group_id,
                "ad_group_name": log.ad_group_name,
                "stats_snapshot": log.stats_snapshot,
                "success": log.success,
                "error_message": log.error_message,
                "is_dry_run": log.is_dry_run,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "total": total
    }


@app.get("/api/auto-disable/summary")
async def get_auto_disable_summary_endpoint(db: Session = Depends(get_db)):
    """Get summary of auto-disable rules and recent activity"""
    configs = crud.get_auto_disable_configs(db)
    enabled_count = sum(1 for c in configs if c.enabled)
    
    # Get recent logs
    logs, total_logs = crud.get_auto_disable_logs(db, limit=10)
    
    # Count disabled banners in last 24 hours
    recent_logs, _ = crud.get_auto_disable_logs(db, limit=1000)
    now = get_moscow_time()
    disabled_24h = sum(1 for log in recent_logs 
                       if log.success and 
                       not log.is_dry_run and 
                       (now - log.created_at).total_seconds() < 86400)
    
    return {
        "total_rules": len(configs),
        "enabled_rules": enabled_count,
        "disabled_24h": disabled_24h,
        "total_logs": total_logs,
        "recent_logs": [
            {
                "id": log.id,
                "config_name": log.config_name,
                "banner_id": log.banner_id,
                "banner_name": log.banner_name,
                "account_name": log.account_name,
                "success": log.success,
                "is_dry_run": log.is_dry_run,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
    }


# === Disable Rules API (Правила отключения объявлений) ===

@app.get("/api/disable-rules")
async def get_disable_rules_endpoint(
    enabled_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all disable rules with their conditions and linked accounts for current user"""
    rules = crud.get_disable_rules(db, user_id=current_user.id, enabled_only=enabled_only)
    
    result = []
    for rule in rules:
        # Get conditions
        conditions = [
            {
                "id": c.id,
                "metric": c.metric,
                "operator": c.operator,
                "value": c.value,
                "order": c.order
            }
            for c in rule.conditions
        ]
        
        # Get linked accounts
        account_ids = crud.get_rule_account_ids(db, rule.id)
        accounts = crud.get_rule_accounts(db, rule.id)
        account_names = [acc.name for acc in accounts]
        
        result.append({
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "created_at": rule.created_at.isoformat(),
            "updated_at": rule.updated_at.isoformat(),
            "conditions": conditions,
            "account_ids": account_ids,
            "account_names": account_names
        })
    
    return {"items": result, "total": len(result)}


@app.get("/api/disable-rules/metrics")
async def get_disable_rule_metrics_endpoint():
    """Get available metrics and operators for disable rules"""
    return {
        "metrics": [
            {"value": "goals", "label": "Результаты (goals)", "description": "Количество конверсий/целей VK"},
            {"value": "spent", "label": "Потрачено (₽)", "description": "Сумма потраченных денег в рублях"},
            {"value": "clicks", "label": "Клики", "description": "Количество кликов по объявлению"},
            {"value": "shows", "label": "Показы", "description": "Количество показов объявления"},
            {"value": "ctr", "label": "CTR (%)", "description": "Click-through rate (клики/показы * 100)"},
            {"value": "cpc", "label": "CPC (₽)", "description": "Cost per click (цена за клик)"},
            {"value": "cost_per_goal", "label": "Цена результата (₽)", "description": "Стоимость одной конверсии"},
            {"value": "roi", "label": "ROI (%)", "description": "Return on Investment ((доход - затраты) / затраты * 100). Если дохода нет или объявление не в Leadstech - ROI = 0"}
        ],
        "operators": [
            {"value": "equals", "label": "=", "description": "Равно"},
            {"value": "not_equals", "label": "≠", "description": "Не равно"},
            {"value": "greater_than", "label": ">", "description": "Больше"},
            {"value": "less_than", "label": "<", "description": "Меньше"},
            {"value": "greater_or_equal", "label": "≥", "description": "Больше или равно"},
            {"value": "less_or_equal", "label": "≤", "description": "Меньше или равно"}
        ]
    }


@app.get("/api/disable-rules/for-account/{account_id}")
async def get_rules_for_account_endpoint(
    account_id: int,
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get all disable rules that apply to a specific account"""
    rules = crud.get_rules_for_account(db, account_id, enabled_only=enabled_only)
    
    result = []
    for rule in rules:
        conditions = [
            {
                "id": c.id,
                "metric": c.metric,
                "operator": c.operator,
                "value": c.value,
                "order": c.order
            }
            for c in rule.conditions
        ]
        
        result.append({
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "conditions": conditions
        })
    
    return {"items": result, "total": len(result)}


@app.get("/api/disable-rules/{rule_id}")
async def get_disable_rule_endpoint(rule_id: int, db: Session = Depends(get_db)):
    """Get a specific disable rule by ID"""
    rule = crud.get_disable_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    conditions = [
        {
            "id": c.id,
            "metric": c.metric,
            "operator": c.operator,
            "value": c.value,
            "order": c.order
        }
        for c in rule.conditions
    ]
    
    account_ids = crud.get_rule_account_ids(db, rule.id)
    accounts = crud.get_rule_accounts(db, rule.id)
    account_names = [acc.name for acc in accounts]
    
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "conditions": conditions,
        "account_ids": account_ids,
        "account_names": account_names
    }


@app.post("/api/disable-rules")
async def create_disable_rule_endpoint(
    data: DisableRuleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new disable rule for current user"""
    # Create the rule
    rule = crud.create_disable_rule(
        db,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        priority=data.priority
    )
    
    # Add conditions
    if data.conditions:
        conditions_data = [c.model_dump() for c in data.conditions]
        crud.replace_rule_conditions(db, rule.id, conditions_data)
    
    # Link accounts
    if data.account_ids:
        crud.replace_rule_accounts(db, rule.id, data.account_ids, user_id=current_user.id)
    
    # Fetch updated data
    account_ids = crud.get_rule_account_ids(db, rule.id)
    accounts = crud.get_rule_accounts(db, rule.id)
    account_names = [acc.name for acc in accounts]
    
    conditions = [
        {
            "id": c.id,
            "metric": c.metric,
            "operator": c.operator,
            "value": c.value,
            "order": c.order
        }
        for c in rule.conditions
    ]
    
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "conditions": conditions,
        "account_ids": account_ids,
        "account_names": account_names
    }


@app.put("/api/disable-rules/{rule_id}")
async def update_disable_rule_endpoint(
    rule_id: int,
    data: DisableRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing disable rule for current user"""
    rule = crud.get_disable_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Update basic fields
    crud.update_disable_rule(
        db,
        rule_id,
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        priority=data.priority
    )
    
    # Update conditions if provided
    if data.conditions is not None:
        conditions_data = [c.model_dump() for c in data.conditions]
        crud.replace_rule_conditions(db, rule_id, conditions_data)
    
    # Update account links if provided
    if data.account_ids is not None:
        crud.replace_rule_accounts(db, rule_id, data.account_ids, user_id=current_user.id)
    
    # Fetch updated rule
    rule = crud.get_disable_rule_by_id(db, rule_id)
    account_ids = crud.get_rule_account_ids(db, rule_id)
    accounts = crud.get_rule_accounts(db, rule_id)
    account_names = [acc.name for acc in accounts]
    
    conditions = [
        {
            "id": c.id,
            "metric": c.metric,
            "operator": c.operator,
            "value": c.value,
            "order": c.order
        }
        for c in rule.conditions
    ]
    
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "conditions": conditions,
        "account_ids": account_ids,
        "account_names": account_names
    }


@app.delete("/api/disable-rules/{rule_id}")
async def delete_disable_rule_endpoint(rule_id: int, db: Session = Depends(get_db)):
    """Delete a disable rule"""
    if not crud.delete_disable_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return {"message": "Rule deleted successfully"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
