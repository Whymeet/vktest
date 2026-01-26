"""
CRUD operations for User management
Includes: User, UserFeature, RefreshToken, UserSettings
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from utils.time_utils import get_moscow_time
from database.models import User, UserFeature, RefreshToken, UserSettings


# ===== User Management =====

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get user by ID"""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get user by username"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


def get_all_users(db: Session) -> List[User]:
    """Get all users"""
    return db.query(User).order_by(User.created_at.desc()).all()


def create_user(
    db: Session,
    username: str,
    password_hash: str,
    email: Optional[str] = None,
    is_superuser: bool = False
) -> User:
    """Create a new user"""
    user = User(
        username=username,
        password_hash=password_hash,
        email=email,
        is_superuser=is_superuser,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    **kwargs
) -> Optional[User]:
    """Update user fields"""
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)

    user.updated_at = get_moscow_time()
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user_id: int, password_hash: str) -> Optional[User]:
    """Update user password"""
    return update_user(db, user_id, password_hash=password_hash)


def update_user_last_login(db: Session, user_id: int) -> Optional[User]:
    """Update user last login time"""
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    user.last_login = get_moscow_time()
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> bool:
    """Delete user and all related data (cascade)"""
    user = get_user_by_id(db, user_id)
    if not user:
        return False

    db.delete(user)
    db.commit()
    return True


# ===== User Features (Access Control) =====

AVAILABLE_FEATURES = ["auto_disable", "scaling", "leadstech", "logs"]


def get_user_features(db: Session, user_id: int) -> List[str]:
    """Get list of features available to user"""
    features = db.query(UserFeature).filter(UserFeature.user_id == user_id).all()
    return [f.feature for f in features]


def user_has_feature(db: Session, user_id: int, feature: str) -> bool:
    """Check if user has access to a specific feature"""
    return db.query(UserFeature).filter(
        UserFeature.user_id == user_id,
        UserFeature.feature == feature
    ).first() is not None


def add_user_feature(db: Session, user_id: int, feature: str) -> Optional[UserFeature]:
    """Add feature access to user"""
    if feature not in AVAILABLE_FEATURES:
        return None

    existing = db.query(UserFeature).filter(
        UserFeature.user_id == user_id,
        UserFeature.feature == feature
    ).first()
    if existing:
        return existing

    user_feature = UserFeature(user_id=user_id, feature=feature)
    db.add(user_feature)
    db.commit()
    db.refresh(user_feature)
    return user_feature


def remove_user_feature(db: Session, user_id: int, feature: str) -> bool:
    """Remove feature access from user"""
    user_feature = db.query(UserFeature).filter(
        UserFeature.user_id == user_id,
        UserFeature.feature == feature
    ).first()
    if not user_feature:
        return False

    db.delete(user_feature)
    db.commit()
    return True


def set_user_features(db: Session, user_id: int, features: List[str]) -> List[str]:
    """Set user features (replaces all existing features)"""
    db.query(UserFeature).filter(UserFeature.user_id == user_id).delete()

    for feature in features:
        if feature in AVAILABLE_FEATURES:
            db.add(UserFeature(user_id=user_id, feature=feature))

    db.commit()
    return get_user_features(db, user_id)


def add_all_features_to_user(db: Session, user_id: int) -> List[str]:
    """Add all available features to user"""
    return set_user_features(db, user_id, AVAILABLE_FEATURES)


# ===== Refresh Tokens (JWT Authentication) =====

def create_refresh_token(
    db: Session,
    user_id: int,
    token_hash: str,
    jti: str,
    expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    device_name: Optional[str] = None
) -> RefreshToken:
    """Create a new refresh token record"""
    token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        jti=jti,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
        device_name=device_name,
        revoked=False
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def get_refresh_token_by_jti(db: Session, jti: str) -> Optional[RefreshToken]:
    """Get refresh token by JTI"""
    return db.query(RefreshToken).filter(RefreshToken.jti == jti).first()


def get_refresh_token_by_hash(db: Session, token_hash: str) -> Optional[RefreshToken]:
    """Get refresh token by hash"""
    return db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()


def get_user_active_tokens(db: Session, user_id: int) -> List[RefreshToken]:
    """Get all active (non-revoked, non-expired) tokens for a user"""
    now = get_moscow_time()
    return db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > now
    ).order_by(desc(RefreshToken.created_at)).all()


def update_token_last_used(db: Session, token_id: int) -> Optional[RefreshToken]:
    """Update token's last_used_at timestamp"""
    token = db.query(RefreshToken).filter(RefreshToken.id == token_id).first()
    if not token:
        return None

    token.last_used_at = get_moscow_time()
    db.commit()
    db.refresh(token)
    return token


def revoke_refresh_token(db: Session, jti: str) -> bool:
    """Revoke a refresh token by JTI"""
    token = get_refresh_token_by_jti(db, jti)
    if not token:
        return False

    token.revoked = True
    token.revoked_at = get_moscow_time()
    db.commit()
    return True


def revoke_all_user_tokens(db: Session, user_id: int) -> int:
    """Revoke all refresh tokens for a user. Returns count of revoked tokens."""
    now = get_moscow_time()
    count = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False
    ).update({
        "revoked": True,
        "revoked_at": now
    }, synchronize_session=False)
    db.commit()
    return count


def delete_expired_tokens(db: Session) -> int:
    """Delete expired tokens. Returns count of deleted tokens."""
    now = get_moscow_time()
    count = db.query(RefreshToken).filter(
        RefreshToken.expires_at < now
    ).delete(synchronize_session=False)
    db.commit()
    return count


def delete_revoked_tokens(db: Session, older_than_days: int = 30) -> int:
    """Delete revoked tokens older than specified days. Returns count of deleted tokens."""
    cutoff_date = get_moscow_time() - timedelta(days=older_than_days)
    count = db.query(RefreshToken).filter(
        RefreshToken.revoked == True,
        RefreshToken.revoked_at < cutoff_date
    ).delete(synchronize_session=False)
    db.commit()
    return count


# ===== User Settings (per-user key-value store) =====

def get_user_setting(db: Session, user_id: int, key: str) -> Optional[dict]:
    """Get user setting by key"""
    setting = db.query(UserSettings).filter(
        UserSettings.user_id == user_id,
        UserSettings.key == key
    ).first()
    if setting:
        return setting.value
    return None


def set_user_setting(
    db: Session,
    user_id: int,
    key: str,
    value: dict,
    description: Optional[str] = None
) -> UserSettings:
    """Set or update user setting"""
    setting = db.query(UserSettings).filter(
        UserSettings.user_id == user_id,
        UserSettings.key == key
    ).first()

    if setting:
        setting.value = value
        setting.updated_at = get_moscow_time()
        if description:
            setting.description = description
    else:
        setting = UserSettings(
            user_id=user_id,
            key=key,
            value=value,
            description=description
        )
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return setting


def get_all_user_settings(db: Session, user_id: int) -> dict:
    """Get all settings for a user as dict"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).all()
    return {s.key: s.value for s in settings}


def delete_user_setting(db: Session, user_id: int, key: str) -> bool:
    """Delete user setting"""
    setting = db.query(UserSettings).filter(
        UserSettings.user_id == user_id,
        UserSettings.key == key
    ).first()
    if not setting:
        return False

    db.delete(setting)
    db.commit()
    return True


# ===== Admin Notifications =====

def get_admin_telegram_config(db: Session) -> dict:
    """
    Get combined telegram config for all admin users.

    Returns a config dict with:
    - telegram.enabled: True if any admin has telegram enabled
    - telegram.bot_token: First available bot_token from admins
    - telegram.chat_id: List of all admin chat_ids

    Returns empty config if no admins have telegram configured.
    """
    # Get all superusers
    admins = db.query(User).filter(
        User.is_superuser == True,
        User.is_active == True
    ).all()

    if not admins:
        return {"telegram": {"enabled": False}}

    all_chat_ids = []
    bot_token = None

    for admin in admins:
        # Get telegram settings for this admin
        telegram_settings = get_user_setting(db, admin.id, "telegram")
        if not telegram_settings:
            continue

        if not telegram_settings.get("enabled", False):
            continue

        # Get bot_token (use first available)
        if not bot_token and telegram_settings.get("bot_token"):
            bot_token = telegram_settings["bot_token"]

        # Collect chat_ids
        chat_ids = telegram_settings.get("chat_id")
        if chat_ids:
            if isinstance(chat_ids, str):
                all_chat_ids.append(chat_ids)
            elif isinstance(chat_ids, list):
                all_chat_ids.extend(chat_ids)

    if not bot_token or not all_chat_ids:
        return {"telegram": {"enabled": False}}

    return {
        "telegram": {
            "enabled": True,
            "bot_token": bot_token,
            "chat_id": list(set(all_chat_ids))  # Remove duplicates
        }
    }
