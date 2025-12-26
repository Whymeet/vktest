"""
CRUD operations for Global Settings
Note: User-specific settings are in users.py (get_user_setting, set_user_setting, etc.)
"""
from typing import Optional
from sqlalchemy.orm import Session

from utils.time_utils import get_moscow_time
from database.models import Settings


def get_setting(db: Session, key: str) -> Optional[dict]:
    """Get global setting by key"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        return setting.value
    return None


def set_setting(db: Session, key: str, value: dict, description: Optional[str] = None) -> Settings:
    """Set or update global setting"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        setting.value = value
        setting.updated_at = get_moscow_time()
        if description:
            setting.description = description
    else:
        setting = Settings(key=key, value=value, description=description)
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return setting


def get_all_settings(db: Session) -> dict:
    """Get all global settings as dict"""
    settings = db.query(Settings).all()
    return {s.key: s.value for s in settings}


def delete_setting(db: Session, key: str) -> bool:
    """Delete global setting"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if not setting:
        return False

    db.delete(setting)
    db.commit()
    return True
