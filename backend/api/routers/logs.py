"""
Logs viewing endpoints
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database.models import User
from auth.dependencies import get_current_user, require_feature
from api.core.config import LOGS_DIR

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("")
async def list_log_files(
    current_user: User = Depends(require_feature("logs"))
):
    """
    List available log files.
    Returns list of log files with metadata for the frontend.
    """
    log_files = []

    # Scan logs directory
    if LOGS_DIR.exists():
        for log_file in LOGS_DIR.glob("*.log"):
            try:
                stat = log_file.stat()
                # Determine log type
                if "scheduler" in log_file.name.lower():
                    log_type = "scheduler"
                else:
                    log_type = "main"

                log_files.append({
                    "name": log_file.name,
                    "path": str(log_file),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": log_type
                })
            except Exception:
                continue

    # Sort by modification time (newest first)
    log_files.sort(key=lambda x: x["modified"], reverse=True)

    return log_files


@router.get("/{log_type}/{filename}")
async def get_log_content(
    log_type: str,
    filename: str,
    tail: int = 500,
    current_user: User = Depends(get_current_user)
):
    """Get log file contents"""
    # Validate log type
    if log_type not in ["main", "scheduler"]:
        raise HTTPException(status_code=404, detail="Log type not found")

    # Build file path safely
    log_file = LOGS_DIR / filename

    # Security check - ensure file is within LOGS_DIR
    try:
        log_file.resolve().relative_to(LOGS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not log_file.exists():
        return {"filename": filename, "content": "", "total_lines": 0}

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            content = ''.join(all_lines[-tail:])
            return {
                "filename": filename,
                "content": content,
                "total_lines": len(all_lines)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")
