"""
Process control endpoints - start/stop scheduler, analysis, bot, etc.
"""
import os
import sys
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user
from api.core.config import (
    PROJECT_ROOT,
    LOGS_DIR,
    SCHEDULER_SCRIPT,
    SCALING_SCHEDULER_SCRIPT,
    MAIN_SCRIPT,
    BOT_SCRIPT,
)
from api.services.process_manager import (
    running_processes,
    is_process_running_by_db,
    kill_process_by_pid,
)

router = APIRouter(prefix="/api/control", tags=["Process Control"])


@router.get("/status")
async def get_control_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get process control status for current user - checks actual process state via PID"""
    scheduler_running, scheduler_pid = is_process_running_by_db("scheduler", db, current_user.id)
    analysis_running, analysis_pid = is_process_running_by_db("analysis", db, current_user.id)
    bot_running, bot_pid = is_process_running_by_db("bot", db, current_user.id)
    scaling_scheduler_running, scaling_scheduler_pid = is_process_running_by_db("scaling_scheduler", db, current_user.id)

    return {
        "scheduler": {"running": scheduler_running, "pid": scheduler_pid},
        "analysis": {"running": analysis_running, "pid": analysis_pid},
        "bot": {"running": bot_running, "pid": bot_pid},
        "scaling_scheduler": {"running": scaling_scheduler_running, "pid": scaling_scheduler_pid}
    }


@router.post("/scheduler/start")
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

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        user_log_prefix = f"user_{current_user.id}"
        scheduler_stdout = open(LOGS_DIR / f"{user_log_prefix}_scheduler_stdout.log", "a", encoding="utf-8")
        scheduler_stderr = open(LOGS_DIR / f"{user_log_prefix}_scheduler_stderr.log", "a", encoding="utf-8")

        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)
        env["VK_ADS_USERNAME"] = current_user.username

        process = subprocess.Popen(
            [sys.executable, str(SCHEDULER_SCRIPT)],
            stdout=scheduler_stdout,
            stderr=scheduler_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
            env=env
        )

        process_name = f"scheduler_{current_user.id}"
        # Set auto_start=True so scheduler will be restarted after server restart
        crud.set_process_running(db, process_name, process.pid, str(SCHEDULER_SCRIPT), user_id=current_user.id, auto_start=True)
        running_processes[process_name] = process

        print(f"Scheduler started with PID: {process.pid} for user {current_user.username}")
        return {"message": "Scheduler started", "pid": process.pid}
    except Exception as e:
        print(f"Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}")


@router.post("/scheduler/stop")
async def stop_scheduler(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop scheduler for current user"""
    is_running, pid = is_process_running_by_db("scheduler", db, current_user.id)

    if not is_running:
        raise HTTPException(status_code=400, detail="Scheduler not running")

    success = kill_process_by_pid(pid)

    if success:
        process_name = f"scheduler_{current_user.id}"
        crud.set_process_stopped(db, process_name)

        if process_name in running_processes:
            del running_processes[process_name]

        print(f"Scheduler stopped (PID: {pid}) for user {current_user.username}")
        return {"message": "Scheduler stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler (PID: {pid})")


@router.post("/analysis/start")
async def start_analysis(db: Session = Depends(get_db)):
    """Start analysis with persistent PID tracking"""
    is_running, existing_pid = is_process_running_by_db("analysis", db)

    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Analysis already running (PID: {existing_pid})"
        )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        analysis_stdout = open(LOGS_DIR / "analysis_stdout.log", "a", encoding="utf-8")
        analysis_stderr = open(LOGS_DIR / "analysis_stderr.log", "a", encoding="utf-8")

        process = subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            stdout=analysis_stdout,
            stderr=analysis_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True
        )

        crud.set_process_running(db, "analysis", process.pid, str(MAIN_SCRIPT))
        running_processes["analysis"] = process

        print(f"Analysis started with PID: {process.pid}")
        return {"message": "Analysis started", "pid": process.pid}
    except Exception as e:
        print(f"Failed to start analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


@router.post("/analysis/stop")
async def stop_analysis(db: Session = Depends(get_db)):
    """Stop analysis"""
    is_running, pid = is_process_running_by_db("analysis", db)

    if not is_running:
        raise HTTPException(status_code=400, detail="Analysis not running")

    success = kill_process_by_pid(pid)

    if success:
        crud.set_process_stopped(db, "analysis")

        if "analysis" in running_processes:
            del running_processes["analysis"]

        print(f"Analysis stopped (PID: {pid})")
        return {"message": "Analysis stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop analysis (PID: {pid})")


@router.post("/bot/start")
async def start_bot(db: Session = Depends(get_db)):
    """Start Telegram bot with persistent PID tracking"""
    is_running, existing_pid = is_process_running_by_db("bot", db)

    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Bot already running (PID: {existing_pid})"
        )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        bot_stdout = open(LOGS_DIR / "bot_stdout.log", "a", encoding="utf-8")
        bot_stderr = open(LOGS_DIR / "bot_stderr.log", "a", encoding="utf-8")

        process = subprocess.Popen(
            [sys.executable, str(BOT_SCRIPT)],
            stdout=bot_stdout,
            stderr=bot_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True
        )

        crud.set_process_running(db, "bot", process.pid, str(BOT_SCRIPT))
        running_processes["bot"] = process

        print(f"Bot started with PID: {process.pid}")
        return {"message": "Bot started", "pid": process.pid}
    except Exception as e:
        print(f"Failed to start bot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")


@router.post("/bot/stop")
async def stop_bot(db: Session = Depends(get_db)):
    """Stop Telegram bot"""
    is_running, pid = is_process_running_by_db("bot", db)

    if not is_running:
        raise HTTPException(status_code=400, detail="Bot not running")

    success = kill_process_by_pid(pid)

    if success:
        crud.set_process_stopped(db, "bot")

        if "bot" in running_processes:
            del running_processes["bot"]

        print(f"Bot stopped (PID: {pid})")
        return {"message": "Bot stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop bot (PID: {pid})")


@router.post("/scaling_scheduler/start")
async def start_scaling_scheduler(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start scaling scheduler with persistent PID tracking for current user"""
    is_running, existing_pid = is_process_running_by_db("scaling_scheduler", db, current_user.id)

    if is_running:
        raise HTTPException(
            status_code=400,
            detail=f"Scaling scheduler already running (PID: {existing_pid})"
        )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        user_log_prefix = f"user_{current_user.id}"
        scaling_scheduler_stdout = open(LOGS_DIR / f"{user_log_prefix}_scaling_scheduler_stdout.log", "a", encoding="utf-8")
        scaling_scheduler_stderr = open(LOGS_DIR / f"{user_log_prefix}_scaling_scheduler_stderr.log", "a", encoding="utf-8")

        env = os.environ.copy()
        env["VK_ADS_USER_ID"] = str(current_user.id)
        env["VK_ADS_USERNAME"] = current_user.username

        process = subprocess.Popen(
            [sys.executable, str(SCALING_SCHEDULER_SCRIPT)],
            stdout=scaling_scheduler_stdout,
            stderr=scaling_scheduler_stderr,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
            env=env
        )

        process_name = f"scaling_scheduler_{current_user.id}"
        crud.set_process_running(db, process_name, process.pid, str(SCALING_SCHEDULER_SCRIPT), user_id=current_user.id)
        running_processes[process_name] = process

        print(f"Scaling scheduler started with PID: {process.pid} for user {current_user.username}")
        return {"message": "Scaling scheduler started", "pid": process.pid}
    except Exception as e:
        print(f"Failed to start scaling scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scaling scheduler: {str(e)}")


@router.post("/scaling_scheduler/stop")
async def stop_scaling_scheduler(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop scaling scheduler for current user"""
    is_running, pid = is_process_running_by_db("scaling_scheduler", db, current_user.id)

    if not is_running:
        raise HTTPException(status_code=400, detail="Scaling scheduler not running")

    success = kill_process_by_pid(pid)

    if success:
        process_name = f"scaling_scheduler_{current_user.id}"
        crud.set_process_stopped(db, process_name)

        if process_name in running_processes:
            del running_processes[process_name]

        print(f"Scaling scheduler stopped (PID: {pid}) for user {current_user.username}")
        return {"message": "Scaling scheduler stopped", "pid": pid}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to stop scaling scheduler (PID: {pid})")


@router.post("/kill-all")
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

    print(f"Killed {len(killed)} processes: {[k['name'] for k in killed]}")

    return {
        "message": f"Killed {len(killed)} processes",
        "killed": killed,
        "errors": errors if errors else None
    }
