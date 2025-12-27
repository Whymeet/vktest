"""
Scheduler analysis - Running main analysis subprocess
"""
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from utils.time_utils import get_moscow_time
from scheduler.config import MAIN_SCRIPT, PROJECT_ROOT, LOGS_DIR
from scheduler.event_logger import log_scheduler_event, EventType


def determine_error_type(return_code: int, stderr: bytes) -> str:
    """
    Determine error type from return code and stderr.

    Args:
        return_code: Process return code
        stderr: Process stderr output

    Returns:
        Human-readable error type string
    """
    if return_code == -9 or return_code == 137:
        return "SIGKILL (probably OOM - out of memory)"
    elif return_code == -15 or return_code == 143:
        return "SIGTERM (forced termination)"
    elif return_code == -2 or return_code == 130:
        return "SIGINT (user interrupt)"
    elif stderr:
        stderr_text = stderr.decode('utf-8', errors='ignore').lower()
        if 'memory' in stderr_text or 'oom' in stderr_text:
            return "Out of Memory (OOM)"
        elif 'timeout' in stderr_text:
            return "Timeout (execution time exceeded)"
        elif 'connection' in stderr_text:
            return "Connection Error"
        elif 'api' in stderr_text:
            return "API Error"
        elif 'database' in stderr_text or 'postgres' in stderr_text:
            return "Database Error"

    return f"Unknown Error (code {return_code})"


def save_process_logs(
    run_type: str,
    stdout: bytes,
    stderr: bytes,
    return_code: int,
    elapsed: float,
    extra_days: int,
    username: str,
    logger=None
) -> bool:
    """
    Save full process logs to separate files.

    Args:
        run_type: Type of analysis run
        stdout: Process stdout
        stderr: Process stderr
        return_code: Process return code
        elapsed: Execution time in seconds
        extra_days: Extra lookback days used
        username: Username for directory naming
        logger: Optional logger

    Returns:
        True if saved successfully
    """
    try:
        # Create directory for process logs
        process_logs_dir = LOGS_DIR / "scheduler" / "process_logs" / username
        process_logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = get_moscow_time().strftime("%Y%m%d_%H%M%S")
        extra_suffix = f"_plus{extra_days}d" if extra_days > 0 else ""
        base_name = f"{timestamp}_{run_type}{extra_suffix}_rc{return_code}"

        # Save stdout
        if stdout:
            stdout_file = process_logs_dir / f"{base_name}_stdout.log"
            with open(stdout_file, 'wb') as f:
                f.write(stdout)
            if logger:
                logger.debug(f"Stdout saved: {stdout_file}")

        # Save stderr (if exists)
        if stderr:
            stderr_file = process_logs_dir / f"{base_name}_stderr.log"
            with open(stderr_file, 'wb') as f:
                f.write(stderr)
            if logger:
                logger.debug(f"Stderr saved: {stderr_file}")

        # Save metadata
        meta_file = process_logs_dir / f"{base_name}_meta.txt"
        with open(meta_file, 'w', encoding='utf-8') as f:
            f.write(f"Username: {username}\n")
            f.write(f"Analysis type: {run_type}\n")
            f.write(f"Extra days: {extra_days}\n")
            f.write(f"Return code: {return_code}\n")
            f.write(f"Execution time: {elapsed:.1f} sec\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Error type: {determine_error_type(return_code, stderr)}\n")

        return True

    except Exception as e:
        if logger:
            logger.error(f"Error saving process logs: {e}")
        return False


def run_analysis(
    extra_lookback_days: int = 0,
    run_type: str = "main",
    username: str = "unknown",
    user_id: Optional[str] = None,
    run_count: int = 0,
    logger=None
) -> Tuple[bool, Optional[subprocess.Popen]]:
    """
    Run analysis subprocess.

    Args:
        extra_lookback_days: Extra days to add to lookback_days
        run_type: Type of run for logging
        username: Username for logging
        user_id: User ID for logging
        run_count: Current run count
        logger: Optional logger

    Returns:
        Tuple of (success: bool, process: Popen or None)
    """
    if not MAIN_SCRIPT.exists():
        if logger:
            logger.error(f"Script not found: {MAIN_SCRIPT}")
        log_scheduler_event(
            EventType.ANALYSIS_ERROR,
            "Script not found",
            username=username,
            user_id=user_id,
            run_count=run_count,
            extra_data={"run_type": run_type, "script_path": str(MAIN_SCRIPT)}
        )
        return False, None

    extra_info = f" (+{extra_lookback_days} days)" if extra_lookback_days > 0 else "..."

    if logger:
        logger.info(f"Starting {run_type} analysis{extra_info}")
        logger.debug(f"   Command: {sys.executable} {MAIN_SCRIPT}")
        logger.debug(f"   Working directory: {PROJECT_ROOT}")
        if extra_lookback_days > 0:
            logger.debug(f"   VK_EXTRA_LOOKBACK_DAYS={extra_lookback_days}")

    # Log analysis start
    log_scheduler_event(
        EventType.ANALYSIS_STARTED,
        f"Starting {run_type} analysis",
        username=username,
        user_id=user_id,
        run_count=run_count,
        extra_data={"run_type": run_type, "extra_lookback_days": extra_lookback_days}
    )

    try:
        start_time = time.time()

        # Prepare environment with extra days
        env = os.environ.copy()
        if extra_lookback_days > 0:
            env["VK_EXTRA_LOOKBACK_DAYS"] = str(extra_lookback_days)

        process = subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=env
        )

        process_pid = process.pid
        if logger:
            logger.debug(f"   Process PID: {process_pid}")

        # Wait for completion
        stdout, stderr = process.communicate()
        return_code = process.returncode
        elapsed = time.time() - start_time

        # Save full logs
        save_process_logs(run_type, stdout, stderr, return_code, elapsed, extra_lookback_days, username, logger)

        if return_code == 0:
            if logger:
                logger.info(f"{run_type.capitalize()} analysis completed successfully in {elapsed:.1f} sec")

                # Log important messages from stdout
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    for line in stdout_text.split('\n'):
                        if any(kw in line for kw in ['УБЫТОЧНОЕ', 'отключено', 'disabled', 'ERROR', 'ОШИБКА']):
                            logger.info(f"   {line.strip()}")

            log_scheduler_event(
                EventType.ANALYSIS_SUCCESS,
                f"{run_type.capitalize()} analysis successful",
                username=username,
                user_id=user_id,
                run_count=run_count,
                extra_data={
                    "run_type": run_type,
                    "elapsed_seconds": round(elapsed, 1),
                    "return_code": return_code,
                    "pid": process_pid
                }
            )
            return True, None

        else:
            # Determine error type
            error_type = determine_error_type(return_code, stderr)

            if logger:
                logger.error(f"{run_type.capitalize()} analysis failed (code {return_code}) in {elapsed:.1f} sec")
                logger.error(f"   Error type: {error_type}")

                if stderr:
                    stderr_text = stderr.decode('utf-8', errors='ignore')
                    logger.error(f"Stderr (first 2000 chars):\n{stderr_text[:2000]}")
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    lines = stdout_text.strip().split('\n')
                    last_lines = lines[-50:] if len(lines) > 50 else lines
                    logger.error(f"Stdout (last {len(last_lines)} lines):\n" + '\n'.join(last_lines))

            log_scheduler_event(
                EventType.ANALYSIS_FAILED,
                f"{run_type.capitalize()} analysis failed",
                username=username,
                user_id=user_id,
                run_count=run_count,
                extra_data={
                    "run_type": run_type,
                    "elapsed_seconds": round(elapsed, 1),
                    "return_code": return_code,
                    "error_type": error_type,
                    "pid": process_pid,
                    "stderr_preview": stderr.decode('utf-8', errors='ignore')[:500] if stderr else None
                }
            )

            return False, None

    except Exception as e:
        if logger:
            logger.error(f"Error starting {run_type} analysis: {e}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(error_trace)

        log_scheduler_event(
            EventType.ANALYSIS_EXCEPTION,
            f"Exception starting {run_type} analysis",
            username=username,
            user_id=user_id,
            run_count=run_count,
            extra_data={
                "run_type": run_type,
                "exception": str(e),
                "traceback": str(e)[:1000]
            }
        )

        return False, None
