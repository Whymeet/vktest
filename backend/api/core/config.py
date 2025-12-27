"""
Configuration constants for the API
"""
import os
from pathlib import Path

# Environment detection
IN_DOCKER = os.environ.get('IN_DOCKER', 'false').lower() == 'true'

# Project paths
if IN_DOCKER:
    PROJECT_ROOT = Path("/app")
    CFG_PATH = PROJECT_ROOT / "config"
    LOGS_DIR = PROJECT_ROOT / "logs"
    DATA_DIR = PROJECT_ROOT / "data"
    SCHEDULER_SCRIPT = PROJECT_ROOT / "scheduler" / "scheduler_main.py"
    SCALING_SCHEDULER_SCRIPT = PROJECT_ROOT / "scheduler" / "scaling_scheduler.py"
    MAIN_SCRIPT = PROJECT_ROOT / "core" / "main.py"
    BOT_SCRIPT = PROJECT_ROOT / "bot" / "telegram_bot.py"
else:
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    CFG_PATH = PROJECT_ROOT / "config"
    LOGS_DIR = PROJECT_ROOT / "logs"
    DATA_DIR = PROJECT_ROOT / "data"
    SCHEDULER_SCRIPT = PROJECT_ROOT / "backend" / "scheduler" / "scheduler_main.py"
    SCALING_SCHEDULER_SCRIPT = PROJECT_ROOT / "backend" / "scheduler" / "scaling_scheduler.py"
    MAIN_SCRIPT = PROJECT_ROOT / "backend" / "core" / "main.py"
    BOT_SCRIPT = PROJECT_ROOT / "backend" / "bot" / "telegram_bot.py"

# Rate limiting
RATE_LIMIT_PER_MINUTE = os.getenv("RATE_LIMIT_PER_MINUTE", "60")

# CORS settings
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
