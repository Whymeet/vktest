"""
CRUD operations for database models
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from .models import (
    Account,
    WhitelistBanner,
    BannerAction,
    ActiveBanner,
    Settings,
)


# ===== Accounts =====

def get_accounts(db: Session) -> List[Account]:
    """Get all accounts"""
    return db.query(Account).all()


def get_account_by_id(db: Session, account_id: int) -> Optional[Account]:
    """Get account by VK account ID"""
    return db.query(Account).filter(Account.account_id == account_id).first()


def create_account(
    db: Session,
    account_id: int,
    name: str,
    api_token: str,
    client_id: int
) -> Account:
    """Create new account"""
    db_account = Account(
        account_id=account_id,
        name=name,
        api_token=api_token,
        client_id=client_id
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def update_account(
    db: Session,
    account_id: int,
    name: Optional[str] = None,
    api_token: Optional[str] = None,
    client_id: Optional[int] = None
) -> Optional[Account]:
    """Update account"""
    account = get_account_by_id(db, account_id)
    if not account:
        return None

    if name is not None:
        account.name = name
    if api_token is not None:
        account.api_token = api_token
    if client_id is not None:
        account.client_id = client_id

    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, account_id: int) -> bool:
    """Delete account"""
    account = get_account_by_id(db, account_id)
    if not account:
        return False

    db.delete(account)
    db.commit()
    return True


# ===== Whitelist =====

def get_whitelist(db: Session) -> List[int]:
    """Get all whitelisted banner IDs"""
    banners = db.query(WhitelistBanner).all()
    return [b.banner_id for b in banners]


def add_to_whitelist(db: Session, banner_id: int, note: Optional[str] = None) -> WhitelistBanner:
    """Add banner to whitelist"""
    # Check if already exists
    existing = db.query(WhitelistBanner).filter(WhitelistBanner.banner_id == banner_id).first()
    if existing:
        return existing

    db_banner = WhitelistBanner(banner_id=banner_id, note=note)
    db.add(db_banner)
    db.commit()
    db.refresh(db_banner)
    return db_banner


def remove_from_whitelist(db: Session, banner_id: int) -> bool:
    """Remove banner from whitelist"""
    banner = db.query(WhitelistBanner).filter(WhitelistBanner.banner_id == banner_id).first()
    if not banner:
        return False

    db.delete(banner)
    db.commit()
    return True


def is_whitelisted(db: Session, banner_id: int) -> bool:
    """Check if banner is whitelisted"""
    return db.query(WhitelistBanner).filter(WhitelistBanner.banner_id == banner_id).first() is not None


def replace_whitelist(db: Session, banner_ids: List[int]) -> List[int]:
    """Replace entire whitelist"""
    # Delete all existing
    db.query(WhitelistBanner).delete()

    # Add new ones
    for banner_id in banner_ids:
        db.add(WhitelistBanner(banner_id=banner_id))

    db.commit()
    return banner_ids


# ===== Banner Actions (History) =====

def create_banner_action(
    db: Session,
    banner_id: int,
    vk_account_id: int,
    action: str,  # 'disabled' or 'enabled'
    reason: Optional[str] = None,
    banner_name: Optional[str] = None,
    stats: Optional[dict] = None,
    spend: Optional[float] = None,
    conversions: int = 0,
    is_dry_run: bool = False
) -> BannerAction:
    """Log a banner action (enable/disable)"""
    # Get account DB ID
    account = get_account_by_id(db, vk_account_id)
    if not account:
        raise ValueError(f"Account {vk_account_id} not found")

    db_action = BannerAction(
        banner_id=banner_id,
        banner_name=banner_name,
        account_id=account.id,
        vk_account_id=vk_account_id,
        action=action,
        reason=reason,
        stats=stats,
        spend=spend,
        conversions=conversions,
        is_dry_run=is_dry_run
    )
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    return db_action


def get_banner_history(
    db: Session,
    banner_id: Optional[int] = None,
    vk_account_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 100
) -> List[BannerAction]:
    """Get banner action history with filters"""
    query = db.query(BannerAction)

    if banner_id is not None:
        query = query.filter(BannerAction.banner_id == banner_id)
    if vk_account_id is not None:
        query = query.filter(BannerAction.vk_account_id == vk_account_id)
    if action is not None:
        query = query.filter(BannerAction.action == action)

    return query.order_by(desc(BannerAction.created_at)).limit(limit).all()


def get_disabled_banners(db: Session, limit: int = 100) -> List[BannerAction]:
    """Get recently disabled banners"""
    return get_banner_history(db, action='disabled', limit=limit)


# ===== Active Banners =====

def get_active_banners(db: Session, vk_account_id: Optional[int] = None) -> List[ActiveBanner]:
    """Get all active banners"""
    query = db.query(ActiveBanner)
    if vk_account_id is not None:
        query = query.filter(ActiveBanner.vk_account_id == vk_account_id)
    return query.all()


def add_active_banner(
    db: Session,
    banner_id: int,
    vk_account_id: int,
    banner_name: Optional[str] = None,
    campaign_id: Optional[int] = None,
    campaign_name: Optional[str] = None,
    current_spend: float = 0.0,
    current_conversions: int = 0
) -> ActiveBanner:
    """Add or update active banner"""
    # Check if exists
    existing = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if existing:
        # Update existing
        existing.banner_name = banner_name or existing.banner_name
        existing.campaign_id = campaign_id or existing.campaign_id
        existing.campaign_name = campaign_name or existing.campaign_name
        existing.current_spend = current_spend
        existing.current_conversions = current_conversions
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    # Check if whitelisted
    is_wl = is_whitelisted(db, banner_id)

    db_banner = ActiveBanner(
        banner_id=banner_id,
        banner_name=banner_name,
        vk_account_id=vk_account_id,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        current_spend=current_spend,
        current_conversions=current_conversions,
        is_whitelisted=is_wl
    )
    db.add(db_banner)
    db.commit()
    db.refresh(db_banner)
    return db_banner


def remove_active_banner(db: Session, banner_id: int) -> bool:
    """Remove banner from active list"""
    banner = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if not banner:
        return False

    db.delete(banner)
    db.commit()
    return True


def update_active_banner_stats(
    db: Session,
    banner_id: int,
    spend: float,
    conversions: int
) -> Optional[ActiveBanner]:
    """Update banner statistics"""
    banner = db.query(ActiveBanner).filter(ActiveBanner.banner_id == banner_id).first()
    if not banner:
        return None

    banner.current_spend = spend
    banner.current_conversions = conversions
    banner.last_checked = datetime.utcnow()
    db.commit()
    db.refresh(banner)
    return banner


# ===== Settings =====

def get_setting(db: Session, key: str) -> Optional[dict]:
    """Get setting by key"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        return setting.value
    return None


def set_setting(db: Session, key: str, value: dict, description: Optional[str] = None) -> Settings:
    """Set or update setting"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        setting.value = value
        setting.updated_at = datetime.utcnow()
        if description:
            setting.description = description
    else:
        setting = Settings(key=key, value=value, description=description)
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return setting


def get_all_settings(db: Session) -> dict:
    """Get all settings as dict"""
    settings = db.query(Settings).all()
    return {s.key: s.value for s in settings}


def delete_setting(db: Session, key: str) -> bool:
    """Delete setting"""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if not setting:
        return False

    db.delete(setting)
    db.commit()
    return True
