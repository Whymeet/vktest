"""
API Routers - FastAPI APIRouter modules
"""
from api.routers.dashboard import router as dashboard_router
from api.routers.accounts import router as accounts_router
from api.routers.settings import router as settings_router
from api.routers.whitelist import router as whitelist_router
from api.routers.banners import router as banners_router
from api.routers.stats import router as stats_router
from api.routers.control import router as control_router
from api.routers.logs import router as logs_router
from api.routers.leadstech import router as leadstech_router
from api.routers.scaling import router as scaling_router
from api.routers.disable_rules import router as disable_rules_router
from api.routers.auto_disable import router as auto_disable_router

__all__ = [
    "dashboard_router",
    "accounts_router",
    "settings_router",
    "whitelist_router",
    "banners_router",
    "stats_router",
    "control_router",
    "logs_router",
    "leadstech_router",
    "scaling_router",
    "disable_rules_router",
    "auto_disable_router",
]
