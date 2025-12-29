"""
VK Ads Manager - FastAPI Application Factory
Модульная архитектура с роутерами
"""
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging before imports
from api.core.config import LOGS_DIR
from api.core.logging_tee import TeeOutput

# Redirect stdout/stderr to log file
_backend_log_file = LOGS_DIR / "backend_all.log"
sys.stdout = TeeOutput(_backend_log_file, sys.__stdout__)
sys.stderr = TeeOutput(_backend_log_file, sys.__stderr__)

# Now import the rest
from database import init_db
from utils.logging_setup import setup_logging, get_logger
from api.core.config import RATE_LIMIT_PER_MINUTE
from api.services.process_manager import recover_processes_on_startup, autostart_scaling_schedulers, autostart_schedulers

# Import routers
from api.auth_routes import router as auth_router
from api.routers import (
    dashboard_router,
    accounts_router,
    settings_router,
    whitelist_router,
    banners_router,
    stats_router,
    control_router,
    logs_router,
    leadstech_router,
    scaling_router,
    disable_rules_router,
    auto_disable_router,
)

# Initialize Loguru
setup_logging()
logger = get_logger(service="vk_api")

# Rate Limiting
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_PER_MINUTE}/minute"])

# Create FastAPI app
app = FastAPI(
    title="VK Ads Manager API",
    description="Backend API для управления рекламными кампаниями VK",
    version="4.0.0-modular"
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
origins = [origin.strip() for origin in ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(accounts_router)
app.include_router(settings_router)
app.include_router(whitelist_router)
app.include_router(banners_router)
app.include_router(stats_router)
app.include_router(control_router)
app.include_router(logs_router)
app.include_router(leadstech_router)
app.include_router(scaling_router)
app.include_router(disable_rules_router)
app.include_router(auto_disable_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database and recover processes on startup"""
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

    # Auto-start scaling scheduler for all users
    print("🚀 Starting scaling schedulers for all users...")
    autostart_scaling_schedulers()
    print("✅ Scaling schedulers started")

    # Auto-start schedulers that were running before restart
    print("🔄 Auto-starting schedulers with auto_start=True...")
    autostart_schedulers()
    print("✅ Scheduler auto-start complete")
