# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VK Ads Management System - Multi-tenant SaaS platform for automating VKontakte advertising campaigns with rule-based banner management, budget optimization, auto-scaling, and ROI analysis.

## Architecture

**3-tier stack:**
- **Backend**: FastAPI 0.109.0 (Python 3.8+) + SQLAlchemy 2.0 + PostgreSQL 15
- **Frontend**: React 19 + TypeScript 5.9 + Vite 7 + TailwindCSS 4
- **Infrastructure**: Docker Compose + Nginx + Certbot

**Multi-tenancy**: All data isolated by `user_id` with feature flags per user (`auto_disable`, `scaling`, `leadstech`, `logs`).

## Common Commands

### Development

```bash
# Start dev environment with Docker
docker compose -f docker-compose.dev.yml up -d

# Backend only (local, from project root)
source .venv/bin/activate  # or: .venv\Scripts\activate (Windows)
cd backend
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend only (local)
cd frontend
npm install
npm run dev  # http://localhost:5173

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# View application logs (inside container)
docker exec -it vktest2-backend-1 tail -f /app/logs/backend_all.log
```

### User Management

```bash
# Create admin user (interactive)
cd backend
python create_admin.py --interactive

# Create admin user (non-interactive)
python create_admin.py --username admin --password yourpass --email admin@example.com

# Create regular user
python create_user.py --username user --password pass --email user@example.com
```

### Database

```bash
# Database migrations (Alembic)
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# View migration history
alembic history

# Current version
alembic current
```

### Testing

```bash
# Backend tests (run all)
cd backend
pytest

# Run specific test file
pytest tests/test_auth.py -v
pytest tests/test_api.py -v
pytest tests/test_health.py -v

# Run specific test
pytest -k "test_name"

# With coverage
pytest --cov=api --cov-report=html
```

### Frontend

```bash
cd frontend

# Development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint check
npm run lint
```

### Production

```bash
# Deploy production
docker compose -f docker-compose.prod.yml up -d --build

# SSL setup (first time)
./init-ssl.sh

# SSL renewal
./update-ssl.sh
```

## Code Architecture

### Backend Structure

```
backend/
├── api/
│   ├── app.py                # FastAPI app factory with CORS, rate limiting
│   ├── main.py               # Entry point (imports from app.py)
│   ├── auth_routes.py        # Authentication endpoints
│   └── routers/              # Modular route handlers
│       ├── accounts.py       # VK account management
│       ├── disable_rules.py  # Auto-disable rule CRUD
│       ├── auto_disable.py   # Auto-disable execution & manual runs
│       ├── budget_rules.py   # Budget automation CRUD & execution
│       ├── scaling.py        # Ad group duplication configs
│       ├── leadstech.py      # ROI integration
│       ├── dashboard.py      # Dashboard stats
│       ├── banners.py        # Banner data & actions
│       ├── stats.py          # Statistics & charts
│       ├── whitelist.py      # Protected banners
│       ├── settings.py       # Config management
│       ├── control.py        # Process control (start/stop schedulers)
│       └── logs.py           # Log viewing
├── database/
│   ├── models.py             # SQLAlchemy ORM models
│   ├── database.py           # DB connection & session management
│   └── crud/                 # Database operations layer
├── scheduler/
│   ├── scheduler_main.py     # Auto-disable scheduler
│   ├── budget_rules_scheduler.py # Budget scheduler
│   ├── scaling_scheduler.py  # Scaling scheduler
│   ├── analysis.py           # Scheduled analysis logic
│   ├── reenable.py           # Re-enable logic
│   ├── roi_reenable.py       # ROI-based re-enable
│   ├── stats.py              # Stats refresh scheduler
│   └── notifications.py      # Telegram notifications
├── core/
│   ├── analyzer.py           # Rule evaluation engine
│   ├── budget_changer.py     # Budget adjustment logic
│   └── config_loader.py      # Config file loading
├── auth/
│   ├── jwt_handler.py        # JWT token creation/validation
│   └── security.py           # Password hashing
├── services/
│   ├── vk_api_service.py     # VK Ads API client
│   └── leadstech_service.py  # LeadsTech API client
├── utils/
│   ├── vk_api_async.py       # Async VK API wrapper
│   └── logging_setup.py      # Loguru configuration
├── bot/
│   ├── telegram_bot.py       # Telegram bot handlers
│   └── telegram_notify.py    # Telegram notifications
└── alembic/                  # Database migrations
    └── versions/
```

### Frontend Structure

```
frontend/src/
├── pages/                   # Route-level components (lazy loaded)
│   ├── Dashboard.tsx
│   ├── Accounts.tsx
│   ├── DisableRules.tsx
│   ├── BudgetRules.tsx
│   └── Scaling.tsx
├── components/              # Reusable UI components
├── api/                     # API client + TypeScript types
│   └── client.ts            # Axios instance with token refresh
└── hooks/                   # Custom React hooks
```

### Key Patterns

**Database:**
- All timestamps in Moscow timezone (UTC+3)
- Foreign keys with CASCADE or SET NULL
- JSON columns for flexible data (stats snapshots, conditions, errors)
- Composite indexes for multi-column queries
- `created_at`, `updated_at` on major tables

**API:**
- Consistent pagination: `{ items: [...], total: 123, page: 1, page_size: 100 }`
- Query params: `page`, `page_size`, `sort_by`, `sort_order`, `account_name`
- JWT auth via `Authorization: Bearer <token>` header
- Token refresh on 401 with retry interceptor

**Authentication:**
- Access token: 24h expiry
- Refresh token: 7 days expiry, stored in DB with session tracking
- Automatic rotation on refresh

**Frontend:**
- React Query for server state management
- Protected routes check JWT validity
- Feature routes verify user has access to functionality
- Toast notifications for user feedback
- Code splitting with React.lazy()

## Core Workflows

### Auto-Disable Rule Engine

1. User creates rule with conditions (e.g., "spent > 100 AND goals == 0")
2. Scheduler runs analysis at configured interval
3. System fetches banner stats from VK API for lookback period
4. Analyzer evaluates each banner against all enabled rules
5. Matching banners disabled via VK API
6. Actions logged to `banner_actions` table with full context
7. Telegram notification sent

**Files:** `backend/core/analyzer.py`, `backend/api/routers/disable_rules.py`

### Budget Auto-Adjustment

1. User creates budget rule with target conditions and adjustment percentage
2. Scheduler executes rule at specified time
3. System analyzes ad group performance metrics (ROI, goals, etc.)
4. Adjusts budgets up/down by configured percentage (1-20%)
5. Task progress tracked in real-time via `budget_task_logs`

**Files:** `backend/core/budget_changer.py`, `backend/api/routers/budget_rules.py`

### Auto-Scaling (Ad Group Duplication)

1. User creates scaling config with success conditions
2. System identifies high-performing groups matching criteria
3. Duplicates successful groups to new/existing campaigns
4. Supports banner-level filtering (positive/negative classification)
5. Creates 1-100 copies per group
6. Progress tracked via `scaling_tasks` and `scaling_logs`

**Files:** `backend/scheduler/scaling_scheduler.py`, `backend/api/routers/scaling.py`

### ROI Analysis (LeadsTech)

1. User configures LeadsTech API credentials
2. System fetches conversion data from LeadsTech CPA network
3. Matches conversions to banners via sub-field tracking
4. Calculates ROI: `(revenue - spent) / spent * 100`
5. Displays profitable vs unprofitable ads
6. Optional auto-whitelist for profitable banners

**Files:** `backend/api/routers/leadstech.py`, `backend/services/leadstech_service.py`

## Configuration

### Environment Variables (.env)

```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
JWT_SECRET_KEY=minimum_32_character_secret_key
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS=7
ALLOWED_ORIGINS=http://localhost:5173,https://yourdomain.com
RATE_LIMIT_PER_MINUTE=60
```

### Application Config (config/config.json)

Contains VK API account tokens, Telegram bot settings, and scheduler configuration. Updated via `/api/settings` endpoints, not manually.

**Structure:**
```json
{
  "vk_ads_api": {
    "accounts": {
      "AccountName": {
        "api": "Bearer vk1.a...",
        "spent_limit_rub": 100.0
      }
    }
  },
  "telegram": {
    "bot_token": "123456:ABC...",
    "chat_id": ["123456789"],
    "enabled": true
  },
  "scheduler": {
    "enabled": true,
    "interval_minutes": 1
  }
}
```

### Whitelist (config/whitelist.json)

Protected banners that won't be auto-disabled. Managed via `/api/whitelist` endpoints.

```json
{
  "banner_ids": [123456, 789012]
}
```

## Development Notes

**Always use:**
- Async/await for VK API calls and database operations
- FastAPI dependencies for auth and DB sessions
- SQLAlchemy ORM (never raw SQL)
- React Query for server state in frontend
- TypeScript types from `frontend/src/api/types.ts`

**Never:**
- Hardcode VK API tokens (use config.json)
- Skip user_id filtering in multi-tenant queries
- Modify timestamps manually (use DB defaults)
- Use `print()` for logging (use loguru)

**Database changes:**
- Always create Alembic migration: `cd backend && alembic revision --autogenerate -m "description"`
- Update models in `backend/database/models.py` first
- Test migration up/down before committing
- Never manually edit migration files unless fixing specific issues

**Frontend changes:**
- Keep components small and focused
- Use lazy loading for new pages (React.lazy() already configured)
- Add proper TypeScript types, avoid `any`
- Handle loading/error states with React Query
- Use `frontend/src/api/types.ts` for type definitions
- API calls go through `frontend/src/api/client.ts` (has token refresh interceptor)

**Multi-tenancy:**
- ALWAYS filter queries by `user_id` in all database operations
- Never expose data from other users
- Feature flags checked per user: `user.auto_disable_enabled`, `user.scaling_enabled`, etc.
- Use `get_current_user` dependency in API routes for auth

**Scheduler Architecture:**
- Each scheduler runs as separate Python process tracked in `process_states` table
- Schedulers communicate via database, not shared memory
- Use `ProcessState` context manager for process tracking
- Schedulers auto-recover on backend restart (see `autostart_schedulers()` in `api/app.py`)

## Process Management

Background processes tracked in `process_states` table:
- `scheduler_running` - Auto-disable scheduler (analyzes & disables banners)
- `budget_scheduler_running` - Budget adjustment scheduler
- `scaling_scheduler_running` - Scaling scheduler (duplicates ad groups)
- `stats_update_running` - Banner stats refresh

**IMPORTANT:**
- Start/stop via API endpoints: `POST /api/control/scheduler/{process_name}/start|stop`
- Never kill processes manually with `kill` command
- Process state persists in DB and recovers on restart
- Use `POST /api/control/analysis/run` for one-time manual runs

## Logging

**Backend logging:**
- All output redirected to `backend/logs/backend_all.log` (stdout + stderr)
- Loguru used for structured logging
- Per-service loggers available: `get_logger(service="vk_api")`
- Log rotation automatic (10 MB, 7 days retention)

**Viewing logs:**
```bash
# Via API (requires logs feature enabled for user)
GET /api/logs

# Direct file access (local dev)
tail -f backend/logs/backend_all.log

# Inside Docker container
docker exec -it vktest2-backend-1 tail -f /app/logs/backend_all.log
```

**Scheduler logs:**
- Each scheduler writes to separate log file in `backend/scheduler/logs/`
- `scheduler_main.log` - Auto-disable scheduler
- `budget_rules_scheduler.log` - Budget scheduler
- `scaling_scheduler.log` - Scaling scheduler

## VK Ads API Integration

**Authentication:**
- All VK API requests use Bearer token from `config.json`
- Tokens stored per-account: `config["vk_ads_api"]["accounts"][account_name]["api"]`
- Format: `Bearer vk1.a.xxxxx...`

**Rate Limiting:**
- VK API has strict rate limits (3 requests/second per token)
- Use `vk_api_async.py` wrapper with built-in retry logic
- Async/await required for all VK API calls

**Common operations:**
- Fetch banners: `GET /api/v2/banners.json`
- Get statistics: `POST /api/v2/statistics/banners/day.json`
- Update banner status: `PATCH /api/v2/banners/{id}.json`

**Error handling:**
- VK API errors logged with full context
- Telegram notifications on critical failures
- Retry logic for transient errors (429, 5xx)

## Important Gotchas

**Timezone handling:**
- ALL timestamps use Moscow timezone (UTC+3)
- Use `get_moscow_time()` from `utils.time_utils` for new timestamps
- Never use `datetime.now()` directly

**Process recovery:**
- Backend automatically recovers running schedulers on restart
- Check `autostart_schedulers()` and `autostart_scaling_schedulers()` in `api/app.py`
- Process PIDs stored in DB but validated on startup

**Database sessions:**
- Always use FastAPI dependency injection: `db: Session = Depends(get_db)`
- Never create sessions manually outside of dependencies
- Sessions auto-commit on success, rollback on exception

**VK API peculiarities:**
- Banner IDs are BigInteger (not Integer)
- Stats endpoints return empty arrays for new banners (not errors)
- Status field: 1=active, 0=paused, -1=deleted
- Campaigns/groups can have daily budgets in kopecks (multiply by 100)

**Multi-user testing:**
- Use `create_user.py` to create test users
- Each user needs separate VK accounts configured
- Feature flags must be enabled in `user_features` table

**Common errors:**
- "No VK account configured" - User has no accounts in `config.json` with matching `user_id`
- "Feature not enabled" - User lacks entry in `user_features` table
- "Process already running" - Check `process_states` table, may need manual cleanup
- Token refresh loop - Check CORS settings and ALLOWED_ORIGINS in .env

## Troubleshooting

**Backend won't start:**
```bash
# Check database connection
docker compose ps
docker compose logs postgres

# Check environment variables
cat .env | grep DATABASE_URL

# Recreate database
docker compose down -v
docker compose up -d postgres
cd backend && alembic upgrade head
```

**Frontend can't connect to backend:**
```bash
# Check CORS settings in backend/.env or docker-compose
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Check frontend API base URL in frontend/src/api/client.ts
# Should match backend URL
```

**Scheduler not running:**
```bash
# Check process state
curl http://localhost:8000/api/control/status

# Start manually via API
curl -X POST http://localhost:8000/api/control/scheduler/scheduler_running/start

# Check logs
tail -f backend/scheduler/logs/scheduler_main.log
```

**Database migrations failed:**
```bash
# Downgrade one version
cd backend && alembic downgrade -1

# Check current version
alembic current

# View migration history
alembic history

# Force to specific version (dangerous!)
alembic stamp head
```
