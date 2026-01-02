"""
Whitelist management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import require_feature
from api.services.cache import cached, CacheTTL, CacheInvalidation

router = APIRouter(prefix="/api/whitelist", tags=["Whitelist"])


@router.get("")
@cached(ttl=CacheTTL.WHITELIST, endpoint_name="whitelist")
async def get_whitelist(
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Get whitelist for current user"""
    banner_ids = crud.get_whitelist(db, current_user.id)
    return {"banner_ids": banner_ids}


@router.put("")
async def update_whitelist(
    data: dict,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Replace entire whitelist for current user"""
    banner_ids = data.get("banner_ids", [])
    crud.replace_whitelist(db, current_user.id, banner_ids)

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "whitelist")

    return {"message": "Whitelist updated", "count": len(banner_ids)}


@router.post("/bulk-add")
async def bulk_add_to_whitelist(
    data: dict,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Add multiple banners to whitelist without removing existing ones"""
    banner_ids = data.get("banner_ids", [])
    if not banner_ids:
        raise HTTPException(status_code=400, detail="banner_ids is required")

    result = crud.bulk_add_to_whitelist(db, current_user.id, banner_ids)

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "whitelist")

    return {
        "message": f"Added {result['added']} banners, skipped {result['skipped']} (already in list)",
        "added": result["added"],
        "skipped": result["skipped"],
        "total": result["total"]
    }


@router.post("/bulk-remove")
async def bulk_remove_from_whitelist(
    data: dict,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Remove multiple banners from whitelist"""
    banner_ids = data.get("banner_ids", [])
    if not banner_ids:
        raise HTTPException(status_code=400, detail="banner_ids is required")

    result = crud.bulk_remove_from_whitelist(db, current_user.id, banner_ids)

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "whitelist")

    return {
        "message": f"Removed {result['removed']} banners from {result['total']}",
        "removed": result["removed"],
        "total": result["total"]
    }


@router.post("/add/{banner_id}")
async def add_to_whitelist(
    banner_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Add banner to whitelist for current user"""
    crud.add_to_whitelist(db, current_user.id, banner_id)

    # Invalidate cache after update
    await CacheInvalidation.after_update(current_user.id, "whitelist")

    return {"message": "Banner added to whitelist"}


@router.delete("/{banner_id}")
async def remove_from_whitelist(
    banner_id: int,
    current_user: User = Depends(require_feature("auto_disable")),
    db: Session = Depends(get_db)
):
    """Remove banner from whitelist for current user"""
    removed = crud.remove_from_whitelist(db, current_user.id, banner_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Banner not in whitelist")

    # Invalidate cache after delete
    await CacheInvalidation.after_delete(current_user.id, "whitelist")

    return {"message": "Banner removed from whitelist"}
