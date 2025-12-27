"""
API Services - business logic and background tasks
"""
from api.services.process_manager import (
    running_processes,
    check_pid_alive,
    check_process_is_python_script,
    kill_process_by_pid,
    recover_processes_on_startup,
    is_process_running_by_db,
    autostart_scaling_schedulers,
)
from api.services.scaling_worker import (
    run_duplication_task,
    run_auto_scaling_task,
)

__all__ = [
    # Process manager
    "running_processes",
    "check_pid_alive",
    "check_process_is_python_script",
    "kill_process_by_pid",
    "recover_processes_on_startup",
    "is_process_running_by_db",
    "autostart_scaling_schedulers",
    # Scaling worker
    "run_duplication_task",
    "run_auto_scaling_task",
]
