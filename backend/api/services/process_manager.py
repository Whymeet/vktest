"""
Process Management - utilities for managing subprocess lifecycle
"""
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Optional

import psutil

from database import crud, SessionLocal
from api.core.config import (
    PROJECT_ROOT,
    LOGS_DIR,
    SCALING_SCHEDULER_SCRIPT,
)

# Global process cache for current API session
# PID is also persisted in DB for recovery after restart
running_processes: Dict[str, subprocess.Popen] = {}


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
                    print(f"  Recovered running process: {state.name} (PID: {state.pid})")
                else:
                    # Process died while API was down - update in DB
                    state.status = 'stopped'
                    state.last_error = "Process died while API was down"
                    db.commit()
                    print(f"  Process {state.name} (PID: {state.pid}) is no longer running, marked as stopped")
    except Exception as e:
        print(f"  Error during process recovery: {e}")
    finally:
        db.close()


def is_process_running_by_db(process_name: str, db, user_id: int = None) -> tuple:
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


def autostart_scaling_schedulers():
    """Auto-start scaling scheduler for all users on application startup"""
    db = SessionLocal()
    try:
        # Get all users
        from database.models import User
        users = db.query(User).all()

        for user in users:
            # Check if scaling scheduler is already running for this user
            is_running, existing_pid = is_process_running_by_db("scaling_scheduler", db, user.id)

            if is_running:
                print(f"    Scaling scheduler already running for user {user.username} (PID: {existing_pid})")
                continue

            # Start scaling scheduler for this user
            try:
                # Ensure logs directory exists
                LOGS_DIR.mkdir(parents=True, exist_ok=True)

                # Open log files for stdout/stderr with user-specific filenames
                user_log_prefix = f"user_{user.id}"
                scaling_scheduler_stdout = open(LOGS_DIR / f"{user_log_prefix}_scaling_scheduler_stdout.log", "a", encoding="utf-8")
                scaling_scheduler_stderr = open(LOGS_DIR / f"{user_log_prefix}_scaling_scheduler_stderr.log", "a", encoding="utf-8")

                # Pass user_id as environment variable to the scaling scheduler
                env = os.environ.copy()
                env["VK_ADS_USER_ID"] = str(user.id)

                process = subprocess.Popen(
                    [sys.executable, str(SCALING_SCHEDULER_SCRIPT)],
                    stdout=scaling_scheduler_stdout,
                    stderr=scaling_scheduler_stderr,
                    cwd=str(PROJECT_ROOT),
                    start_new_session=True,
                    env=env
                )

                # Save to DB for persistence with user-specific name
                process_name = f"scaling_scheduler_{user.id}"
                crud.set_process_running(db, process_name, process.pid, str(SCALING_SCHEDULER_SCRIPT), user_id=user.id)

                # Also keep in memory cache for current session
                running_processes[process_name] = process

                print(f"    Scaling scheduler started for user {user.username} (PID: {process.pid})")
            except Exception as e:
                print(f"    Failed to start scaling scheduler for user {user.username}: {e}")
    finally:
        db.close()
