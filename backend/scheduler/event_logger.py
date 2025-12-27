"""
Scheduler event logger - JSONL logging for scheduler events
"""
import json
from pathlib import Path
from typing import Dict, Optional

from utils.time_utils import get_moscow_time
from scheduler.config import SCHEDULER_LOGS_DIR


def log_scheduler_event(
    event_type: str,
    message: str,
    username: str,
    user_id: Optional[str] = None,
    run_count: int = 0,
    extra_data: Optional[Dict] = None,
    logger=None
) -> bool:
    """
    Log scheduler event to JSONL file for tracking.

    Args:
        event_type: Type of event (STARTED, ANALYSIS_SUCCESS, etc.)
        message: Human-readable message
        username: Username for file naming
        user_id: User ID
        run_count: Current run count
        extra_data: Additional data to include
        logger: Optional logger for error reporting

    Returns:
        True if logged successfully, False otherwise
    """
    try:
        # Ensure logs directory exists
        SCHEDULER_LOGS_DIR.mkdir(parents=True, exist_ok=True)

        events_file = SCHEDULER_LOGS_DIR / f"events_{username}.jsonl"

        event = {
            "timestamp": get_moscow_time().isoformat(),
            "username": username,
            "user_id": user_id,
            "event_type": event_type,
            "message": message,
            "run_count": run_count,
        }

        if extra_data:
            event.update(extra_data)

        with open(events_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')

        return True

    except Exception as e:
        if logger:
            logger.error(f"Error writing scheduler event: {e}")
        return False


def get_events_file_path(username: str) -> Path:
    """Get path to events file for user"""
    return SCHEDULER_LOGS_DIR / f"events_{username}.jsonl"


# Event type constants
class EventType:
    """Standard scheduler event types"""
    STARTED = "STARTED"
    SIGNAL_RECEIVED = "SIGNAL_RECEIVED"
    PROCESS_TERMINATED = "PROCESS_TERMINATED"

    SCHEDULER_LOOP_STARTED = "SCHEDULER_LOOP_STARTED"
    SCHEDULER_STOPPED = "SCHEDULER_STOPPED"
    MAX_RUNS_REACHED = "MAX_RUNS_REACHED"

    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_SUCCESS = "ANALYSIS_SUCCESS"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    ANALYSIS_EXCEPTION = "ANALYSIS_EXCEPTION"
    ANALYSIS_ERROR = "ANALYSIS_ERROR"

    RETRY_STARTED = "RETRY_STARTED"
    RETRY_SUCCESS = "RETRY_SUCCESS"
    RETRY_FAILED = "RETRY_FAILED"

    REENABLE_STARTED = "REENABLE_STARTED"
    REENABLE_COMPLETED = "REENABLE_COMPLETED"
    REENABLE_ERROR = "REENABLE_ERROR"
