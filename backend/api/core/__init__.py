"""
API Core - configuration and utilities
"""
from api.core.config import (
    IN_DOCKER,
    PROJECT_ROOT,
    CFG_PATH,
    LOGS_DIR,
    DATA_DIR,
    SCHEDULER_SCRIPT,
    SCALING_SCHEDULER_SCRIPT,
    MAIN_SCRIPT,
    BOT_SCRIPT,
    RATE_LIMIT_PER_MINUTE,
    ALLOWED_ORIGINS,
)

__all__ = [
    "IN_DOCKER",
    "PROJECT_ROOT",
    "CFG_PATH",
    "LOGS_DIR",
    "DATA_DIR",
    "SCHEDULER_SCRIPT",
    "SCALING_SCHEDULER_SCRIPT",
    "MAIN_SCRIPT",
    "BOT_SCRIPT",
    "RATE_LIMIT_PER_MINUTE",
    "ALLOWED_ORIGINS",
]
