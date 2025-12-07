"""
Database models for VK Ads Manager
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Account(Base):
    """VK Ads account model"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    api_token = Column(String(255), nullable=False)
    client_id = Column(Integer, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    banner_actions = relationship("BannerAction", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(account_id={self.account_id}, name='{self.name}')>"


class WhitelistBanner(Base):
    """Whitelist banners model"""
    __tablename__ = "whitelist_banners"

    id = Column(Integer, primary_key=True, index=True)
    banner_id = Column(Integer, unique=True, nullable=False, index=True)

    # Optional metadata
    note = Column(Text, nullable=True)
    added_by = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<WhitelistBanner(banner_id={self.banner_id})>"


class BannerAction(Base):
    """Banner action history (enabled/disabled)"""
    __tablename__ = "banner_actions"

    id = Column(Integer, primary_key=True, index=True)

    # Banner info
    banner_id = Column(Integer, nullable=False, index=True)
    banner_name = Column(String(500), nullable=True)

    # Account relationship
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    vk_account_id = Column(Integer, nullable=False, index=True)

    # Action type: 'disabled' or 'enabled'
    action = Column(String(20), nullable=False, index=True)

    # Reason for action
    reason = Column(Text, nullable=True)

    # Stats at the time of action
    stats = Column(JSON, nullable=True)  # Store stats snapshot

    # Additional metadata
    spend = Column(Float, nullable=True)
    conversions = Column(Integer, default=0)
    is_dry_run = Column(Boolean, default=False)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    account = relationship("Account", back_populates="banner_actions")

    def __repr__(self):
        return f"<BannerAction(banner_id={self.banner_id}, action='{self.action}', created_at={self.created_at})>"


class ActiveBanner(Base):
    """Currently active (enabled) banners"""
    __tablename__ = "active_banners"

    id = Column(Integer, primary_key=True, index=True)

    # Banner info
    banner_id = Column(Integer, unique=True, nullable=False, index=True)
    banner_name = Column(String(500), nullable=True)

    # Account
    vk_account_id = Column(Integer, nullable=False, index=True)

    # Campaign info
    campaign_id = Column(Integer, nullable=True, index=True)
    campaign_name = Column(String(500), nullable=True)

    # Current stats
    current_spend = Column(Float, default=0.0)
    current_conversions = Column(Integer, default=0)

    # Status info
    is_whitelisted = Column(Boolean, default=False)
    last_checked = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Timestamps
    enabled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ActiveBanner(banner_id={self.banner_id}, name='{self.banner_name}')>"


class Settings(Base):
    """Application settings (key-value store)"""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False)

    # Description
    description = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Settings(key='{self.key}', value={self.value})>"
