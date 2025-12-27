"""
CRUD operations for Whitelist management
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from database.models import WhitelistBanner


def get_whitelist(db: Session, user_id: int) -> List[int]:
    """Get all whitelisted banner IDs for a user"""
    banners = db.query(WhitelistBanner).filter(WhitelistBanner.user_id == user_id).all()
    return [b.banner_id for b in banners]


def add_to_whitelist(db: Session, user_id: int, banner_id: int, note: Optional[str] = None) -> WhitelistBanner:
    """Add banner to whitelist for a user"""
    existing = db.query(WhitelistBanner).filter(
        WhitelistBanner.user_id == user_id,
        WhitelistBanner.banner_id == banner_id
    ).first()
    if existing:
        return existing

    db_banner = WhitelistBanner(user_id=user_id, banner_id=banner_id, note=note)
    db.add(db_banner)
    db.commit()
    db.refresh(db_banner)
    return db_banner


def remove_from_whitelist(db: Session, user_id: int, banner_id: int) -> bool:
    """Remove banner from whitelist for a user"""
    banner = db.query(WhitelistBanner).filter(
        WhitelistBanner.user_id == user_id,
        WhitelistBanner.banner_id == banner_id
    ).first()
    if not banner:
        return False

    db.delete(banner)
    db.commit()
    return True


def is_whitelisted(db: Session, user_id: int, banner_id: int) -> bool:
    """Check if banner is whitelisted for a user"""
    return db.query(WhitelistBanner).filter(
        WhitelistBanner.user_id == user_id,
        WhitelistBanner.banner_id == banner_id
    ).first() is not None


def replace_whitelist(db: Session, user_id: int, banner_ids: List[int]) -> List[int]:
    """Replace entire whitelist for a user"""
    db.query(WhitelistBanner).filter(WhitelistBanner.user_id == user_id).delete()

    for banner_id in banner_ids:
        db.add(WhitelistBanner(user_id=user_id, banner_id=banner_id))

    db.commit()
    return banner_ids


def bulk_add_to_whitelist(db: Session, user_id: int, banner_ids: List[int]) -> dict:
    """Add multiple banners to whitelist for a user (without removing existing ones)"""
    if not banner_ids:
        return {"added": 0, "skipped": 0, "total": 0}

    existing_records = db.query(WhitelistBanner.banner_id).filter(
        WhitelistBanner.user_id == user_id,
        WhitelistBanner.banner_id.in_(banner_ids)
    ).all()
    existing_ids = {record[0] for record in existing_records}

    new_banner_ids = [bid for bid in banner_ids if bid not in existing_ids]

    if new_banner_ids:
        new_banners = [
            WhitelistBanner(user_id=user_id, banner_id=banner_id)
            for banner_id in new_banner_ids
        ]
        db.bulk_save_objects(new_banners)
        db.commit()

    return {
        "added": len(new_banner_ids),
        "skipped": len(existing_ids),
        "total": len(banner_ids)
    }


def bulk_remove_from_whitelist(db: Session, user_id: int, banner_ids: List[int]) -> dict:
    """Remove multiple banners from whitelist for a user"""
    if not banner_ids:
        return {"removed": 0, "total": 0}

    removed_count = db.query(WhitelistBanner).filter(
        WhitelistBanner.user_id == user_id,
        WhitelistBanner.banner_id.in_(banner_ids)
    ).delete(synchronize_session='fetch')

    db.commit()
    return {
        "removed": removed_count,
        "total": len(banner_ids)
    }
