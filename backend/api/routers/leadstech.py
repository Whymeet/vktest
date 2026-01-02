"""
LeadsTech integration endpoints
"""
import os
import sys
import subprocess
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import require_feature
from api.core.config import PROJECT_ROOT, LOGS_DIR, IN_DOCKER
from api.services.process_manager import (
    is_process_running_by_db,
    kill_process_by_pid,
)
from api.schemas.leadstech import (
    LeadsTechConfigCreate,
    LeadsTechCabinetUpdate,
)
from api.services.cache import cached, CacheTTL, CacheInvalidation

router = APIRouter(prefix="/api/leadstech", tags=["LeadsTech"])


class LeadsTechAnalysisSettings(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    banner_sub_fields: Optional[List[str]] = ["sub4", "sub5"]


# === Config ===

@router.get("/config")
@cached(ttl=CacheTTL.LEADSTECH_CONFIG, endpoint_name="leadstech-config")
async def get_leadstech_config(
    current_user: User = Depends(require_feature("leadstech")),
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
        "date_from": config.date_from,
        "date_to": config.date_to,
        "banner_sub_fields": config.banner_sub_fields or ["sub4", "sub5"],
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None
    }


@router.put("/config")
async def update_leadstech_config(
    config: LeadsTechConfigCreate,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Create or update LeadsTech configuration"""
    existing_config = crud.get_leadstech_config(db, user_id=current_user.id)

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
        date_from=config.date_from,
        date_to=config.date_to,
        banner_sub_fields=config.banner_sub_fields
    )

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "leadstech_config")

    return {"message": "LeadsTech configuration updated", "id": result.id}


@router.delete("/config")
async def delete_leadstech_config(
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Delete LeadsTech configuration"""
    if crud.delete_leadstech_config(db, user_id=current_user.id):
        # Invalidate cache after delete
        await CacheInvalidation.after_delete(current_user.id, "leadstech_config")
        return {"message": "LeadsTech configuration deleted"}
    raise HTTPException(status_code=404, detail="LeadsTech configuration not found")


@router.put("/config/analysis")
async def update_leadstech_analysis_settings(
    settings: LeadsTechAnalysisSettings,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Update only LeadsTech analysis settings"""
    existing_config = crud.get_leadstech_config(db, user_id=current_user.id)
    if not existing_config:
        raise HTTPException(status_code=400, detail="LeadsTech credentials not configured. Configure them in Settings first.")

    crud.create_or_update_leadstech_config(
        db,
        login=existing_config.login,
        password=existing_config.password,
        user_id=current_user.id,
        base_url=existing_config.base_url,
        date_from=settings.date_from,
        date_to=settings.date_to,
        banner_sub_fields=settings.banner_sub_fields
    )

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "leadstech_config")

    return {"message": "LeadsTech analysis settings updated"}


# === Cabinets ===

@router.get("/cabinets")
@cached(ttl=CacheTTL.LEADSTECH_CABINETS, endpoint_name="leadstech-cabinets")
async def get_leadstech_cabinets(
    enabled_only: bool = False,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Get all accounts with their labels for LeadsTech analysis.

    Now returns accounts directly from accounts table with their label field.
    """
    accounts = crud.get_accounts(db, user_id=current_user.id)

    result = []
    for acc in accounts:
        # If enabled_only, skip disabled accounts or accounts without label
        if enabled_only and (not acc.label or not acc.leadstech_enabled):
            continue

        result.append({
            "id": acc.id,
            "account_id": acc.id,
            "account_name": acc.name,
            "leadstech_label": acc.label,  # Can be None
            "enabled": acc.leadstech_enabled,  # Separate enabled flag
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "updated_at": acc.updated_at.isoformat() if acc.updated_at else None
        })

    return {"cabinets": result, "count": len(result)}


@router.put("/cabinets/{account_id}")
async def update_leadstech_cabinet(
    account_id: int,
    cabinet: LeadsTechCabinetUpdate,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Update account's LeadsTech settings (label and enabled).

    Now updates fields directly in the accounts table.
    account_id is the database ID of the account.
    """
    result = crud.update_account_leadstech(
        db,
        user_id=current_user.id,
        account_db_id=account_id,
        label=cabinet.leadstech_label,
        enabled=cabinet.enabled
    )
    if not result:
        raise HTTPException(status_code=404, detail="Account not found")

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "leadstech_cabinet")

    return {"message": "Account LeadsTech settings updated"}


@router.delete("/cabinets/{account_id}")
async def delete_leadstech_cabinet(
    account_id: int,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Remove LeadsTech label from account.

    Now clears the label field in the accounts table.
    account_id is the database ID of the account.
    """
    result = crud.update_account_label(
        db,
        user_id=current_user.id,
        account_db_id=account_id,
        label=None
    )
    if not result:
        raise HTTPException(status_code=404, detail="Account not found")

    # Invalidate cache after delete
    await CacheInvalidation.after_delete(current_user.id, "leadstech_cabinet")

    return {"message": "Account label removed"}


# === Analysis ===

@router.get("/analysis/results")
@cached(ttl=CacheTTL.LEADSTECH_RESULTS, endpoint_name="leadstech-results")
async def get_leadstech_analysis_results(
    cabinet_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    sort_by: str = 'created_at',
    sort_order: str = 'desc',
    roi_min: Optional[float] = None,
    roi_max: Optional[float] = None,
    spent_min: Optional[float] = None,
    spent_max: Optional[float] = None,
    revenue_min: Optional[float] = None,
    revenue_max: Optional[float] = None,
    profit_min: Optional[float] = None,
    profit_max: Optional[float] = None,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Get LeadsTech analysis results with pagination, sorting and filters"""
    page_size = min(page_size, 500)
    offset = (page - 1) * page_size

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
        user_id=current_user.id,
        roi_min=roi_min,
        roi_max=roi_max,
        spent_min=spent_min,
        spent_max=spent_max,
        revenue_min=revenue_min,
        revenue_max=revenue_max,
        profit_min=profit_min,
        profit_max=profit_max
    )

    stats = crud.get_leadstech_analysis_stats(
        db,
        user_id=current_user.id,
        cabinet_name=cabinet_name,
        roi_min=roi_min,
        roi_max=roi_max,
        spent_min=spent_min,
        spent_max=spent_max,
        revenue_min=revenue_min,
        revenue_max=revenue_max,
        profit_min=profit_min,
        profit_max=profit_max
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
        "total_pages": total_pages,
        "stats": stats
    }


@router.get("/analysis/cabinets")
@cached(ttl=CacheTTL.LEADSTECH_ANALYSIS_CABINETS, endpoint_name="leadstech-analysis-cabinets")
async def get_leadstech_analysis_cabinets(
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Get all unique cabinet names from analysis results for filter dropdown"""
    cabinet_names = crud.get_leadstech_analysis_cabinet_names(db, user_id=current_user.id)
    return {"cabinets": cabinet_names}


@router.post("/analysis/start")
async def start_leadstech_analysis(
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Start LeadsTech analysis for enabled cabinets"""
    config = crud.get_leadstech_config(db, user_id=current_user.id)
    if not config:
        raise HTTPException(status_code=400, detail="LeadsTech not configured. Please configure login/password first.")

    cabinets = crud.get_leadstech_cabinets(db, user_id=current_user.id, enabled_only=True)
    if not cabinets:
        raise HTTPException(status_code=400, detail="No enabled LeadsTech cabinets. Please configure at least one cabinet.")

    is_running, existing_pid = is_process_running_by_db("leadstech_analysis", db, current_user.id)
    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"LeadsTech analysis already running (PID: {existing_pid})"
        )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    leadstech_script = PROJECT_ROOT / "backend" / "leadstech" / "analyzer.py"
    if IN_DOCKER:
        leadstech_script = PROJECT_ROOT / "leadstech" / "analyzer.py"

    try:
        lt_stdout = open(LOGS_DIR / "leadstech_stdout.log", "a", encoding="utf-8")
        lt_stderr = open(LOGS_DIR / "leadstech_stderr.log", "a", encoding="utf-8")

        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)
        env["VK_ADS_USERNAME"] = current_user.username

        process = subprocess.Popen(
            [sys.executable, str(leadstech_script)],
            stdout=lt_stdout,
            stderr=lt_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
            env=env
        )

        process_name = f"leadstech_analysis_{current_user.id}"
        crud.set_process_running(db, process_name, process.pid, str(leadstech_script), user_id=current_user.id)

        print(f"LeadsTech analysis started with PID: {process.pid}")
        return {
            "message": "LeadsTech analysis started",
            "pid": process.pid,
            "cabinets_count": len(cabinets)
        }
    except Exception as e:
        print(f"Failed to start LeadsTech analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


@router.post("/analysis/stop")
async def stop_leadstech_analysis(
    current_user: User = Depends(require_feature("leadstech")),
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
        print(f"LeadsTech analysis stopped (PID: {pid})")
        return {"message": "LeadsTech analysis stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop analysis (PID: {pid})")


@router.get("/analysis/status")
async def get_leadstech_analysis_status(
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Get LeadsTech analysis process status"""
    is_running, pid = is_process_running_by_db("leadstech_analysis", db, current_user.id)
    return {"running": is_running, "pid": pid}


@router.get("/analysis/logs")
async def get_leadstech_analysis_logs(
    lines: int = 100,
    current_user: User = Depends(require_feature("leadstech"))
):
    """Get last N lines from LeadsTech analysis logs"""
    try:
        log_files = sorted(LOGS_DIR.glob("leadstech_analyzer_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not log_files:
            stderr_log = LOGS_DIR / "leadstech_stderr.log"
            if stderr_log.exists():
                with open(stderr_log, 'r', encoding='utf-8') as f:
                    content = f.readlines()
                    return {"logs": ''.join(content[-lines:]), "source": "stderr"}
            return {"logs": "No logs found", "source": "none"}

        latest_log = log_files[0]
        with open(latest_log, 'r', encoding='utf-8') as f:
            content = f.readlines()
            return {"logs": ''.join(content[-lines:]), "source": str(latest_log.name)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")


# === Whitelist Profitable ===

@router.post("/whitelist-profitable")
async def whitelist_profitable_banners(
    data: dict,
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Start background process to add profitable banners to whitelist and enable them"""
    roi_threshold = data.get("roi_threshold")
    enable_banners = data.get("enable_banners", True)

    if roi_threshold is None:
        raise HTTPException(status_code=400, detail="roi_threshold is required")

    try:
        roi_threshold = float(roi_threshold)
    except ValueError:
        raise HTTPException(status_code=400, detail="roi_threshold must be a number")

    is_running, existing_pid = is_process_running_by_db("whitelist_worker", db, current_user.id)
    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Whitelist process already running (PID: {existing_pid})"
        )

    worker_script = PROJECT_ROOT / "backend" / "leadstech" / "whitelist_worker.py"
    if IN_DOCKER:
        worker_script = PROJECT_ROOT / "leadstech" / "whitelist_worker.py"

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        stdout = open(LOGS_DIR / "whitelist_stdout.log", "a", encoding="utf-8")
        stderr = open(LOGS_DIR / "whitelist_stderr.log", "a", encoding="utf-8")

        cmd = [
            sys.executable,
            str(worker_script),
            "--roi", str(roi_threshold),
            "--enable", str(enable_banners).lower()
        ]

        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)
        env["VK_ADS_USERNAME"] = current_user.username

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
        print(f"Failed to start whitelist worker: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start worker: {str(e)}")


@router.get("/whitelist-profitable/status")
async def get_whitelist_status(
    current_user: User = Depends(require_feature("leadstech")),
    db: Session = Depends(get_db)
):
    """Get whitelist worker status"""
    is_running, pid = is_process_running_by_db("whitelist_worker", db, current_user.id)
    return {"running": is_running, "pid": pid}


@router.post("/whitelist-profitable/stop")
async def stop_whitelist_worker(
    current_user: User = Depends(require_feature("leadstech")),
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
        return {"message": "Whitelist worker stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop worker (PID: {pid})")
