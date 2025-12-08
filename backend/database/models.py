"""
Database models for VK Ads Manager
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from utils.time_utils import get_moscow_time

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
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    # Relationships
    banner_actions = relationship("BannerAction", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(account_id={self.account_id}, name='{self.name}')>"


class WhitelistBanner(Base):
    """Whitelist banners model"""
    __tablename__ = "whitelist_banners"

    id = Column(Integer, primary_key=True, index=True)
    banner_id = Column(BigInteger, unique=True, nullable=False, index=True)

    # Optional metadata
    note = Column(Text, nullable=True)
    added_by = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)

    def __repr__(self):
        return f"<WhitelistBanner(banner_id={self.banner_id})>"


class BannerAction(Base):
    """Banner action history (enabled/disabled) - полный лог всех отключённых групп"""
    __tablename__ = "banner_actions"

    id = Column(Integer, primary_key=True, index=True)

    # Banner info
    banner_id = Column(BigInteger, nullable=False, index=True)
    banner_name = Column(String(500), nullable=True)

    # Ad Group info (группа объявлений)
    ad_group_id = Column(BigInteger, nullable=True, index=True)
    ad_group_name = Column(String(500), nullable=True)

    # Campaign info (кампания)
    campaign_id = Column(BigInteger, nullable=True, index=True)
    campaign_name = Column(String(500), nullable=True)

    # Account relationship
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)
    vk_account_id = Column(Integer, nullable=True, index=True)
    account_name = Column(String(255), nullable=True)  # Название кабинета

    # Action type: 'disabled' or 'enabled'
    action = Column(String(20), nullable=False, index=True)

    # Reason for action
    reason = Column(Text, nullable=True)

    # Stats at the time of action
    stats = Column(JSON, nullable=True)  # Store full stats snapshot

    # Financial data
    spend = Column(Float, nullable=True)  # Потрачено денег
    clicks = Column(Integer, default=0)   # Клики
    shows = Column(Integer, default=0)    # Показы
    ctr = Column(Float, nullable=True)    # CTR
    cpc = Column(Float, nullable=True)    # Цена клика

    # Conversions
    conversions = Column(Integer, default=0)  # vk_goals
    cost_per_conversion = Column(Float, nullable=True)  # Цена конверсии

    # Status info
    banner_status = Column(String(50), nullable=True)  # Статус баннера
    delivery_status = Column(String(50), nullable=True)  # Статус доставки
    moderation_status = Column(String(50), nullable=True)  # Статус модерации

    # Analysis info
    spent_limit = Column(Float, nullable=True)  # Лимит расходов на момент анализа
    lookback_days = Column(Integer, nullable=True)  # Период анализа в днях
    analysis_date_from = Column(String(20), nullable=True)  # Начало периода
    analysis_date_to = Column(String(20), nullable=True)  # Конец периода

    # Dry run flag
    is_dry_run = Column(Boolean, default=False)

    # Timestamp
    created_at = Column(DateTime, default=get_moscow_time, nullable=False, index=True)

    # Relationships
    account = relationship("Account", back_populates="banner_actions")

    def __repr__(self):
        return f"<BannerAction(banner_id={self.banner_id}, action='{self.action}', spend={self.spend}, created_at={self.created_at})>"


class ActiveBanner(Base):
    """Currently active (enabled) banners"""
    __tablename__ = "active_banners"

    id = Column(Integer, primary_key=True, index=True)

    # Banner info
    banner_id = Column(BigInteger, unique=True, nullable=False, index=True)
    banner_name = Column(String(500), nullable=True)

    # Account
    vk_account_id = Column(Integer, nullable=False, index=True)

    # Campaign info
    campaign_id = Column(BigInteger, nullable=True, index=True)
    campaign_name = Column(String(500), nullable=True)

    # Current stats
    current_spend = Column(Float, default=0.0)
    current_conversions = Column(Integer, default=0)

    # Status info
    is_whitelisted = Column(Boolean, default=False)
    last_checked = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time)

    # Timestamps
    enabled_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

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
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    def __repr__(self):
        return f"<Settings(key='{self.key}', value={self.value})>"


class DailyAccountStats(Base):
    """Daily statistics per account - сохраняется при каждом запуске анализа"""
    __tablename__ = "daily_account_stats"

    id = Column(Integer, primary_key=True, index=True)

    # Account info
    account_name = Column(String(255), nullable=False, index=True)
    vk_account_id = Column(Integer, nullable=True, index=True)

    # Date of stats
    stats_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD

    # Banner counts
    active_banners = Column(Integer, default=0)  # Активные объявления
    disabled_banners = Column(Integer, default=0)  # Отключено за этот запуск
    over_limit_banners = Column(Integer, default=0)  # Превысили лимит
    under_limit_banners = Column(Integer, default=0)  # В пределах лимита
    no_activity_banners = Column(Integer, default=0)  # Без активности

    # Financial stats (за период анализа)
    total_spend = Column(Float, default=0.0)  # Всего потрачено
    total_clicks = Column(Integer, default=0)
    total_shows = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)

    # Analysis settings used
    spent_limit = Column(Float, nullable=True)
    lookback_days = Column(Integer, nullable=True)

    # Timestamp когда записана статистика
    created_at = Column(DateTime, default=get_moscow_time, nullable=False, index=True)

    def __repr__(self):
        return f"<DailyAccountStats(account='{self.account_name}', date={self.stats_date}, spend={self.total_spend})>"


class ProcessState(Base):
    """Running process state - persists across API restarts"""
    __tablename__ = "process_states"

    id = Column(Integer, primary_key=True, index=True)

    # Process identification
    name = Column(String(50), unique=True, nullable=False, index=True)  # 'scheduler', 'analysis', 'bot'
    pid = Column(Integer, nullable=True)  # OS process ID

    # Process info
    script_path = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)

    # Status: 'running', 'stopped', 'crashed', 'unknown'
    status = Column(String(20), default='stopped', nullable=False)

    # Last error if crashed
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    def __repr__(self):
        return f"<ProcessState(name='{self.name}', pid={self.pid}, status='{self.status}')>"


class LeadsTechConfig(Base):
    """LeadsTech global configuration"""
    __tablename__ = "leadstech_config"

    id = Column(Integer, primary_key=True, index=True)

    # LeadsTech API credentials
    login = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    base_url = Column(String(500), default="https://api.leads.tech")

    # Analysis settings
    lookback_days = Column(Integer, default=10)
    banner_sub_field = Column(String(50), default="sub4")

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    def __repr__(self):
        return f"<LeadsTechConfig(login='{self.login}', lookback_days={self.lookback_days})>"


class LeadsTechCabinet(Base):
    """LeadsTech cabinet mapping to VK Ads account"""
    __tablename__ = "leadstech_cabinets"

    id = Column(Integer, primary_key=True, index=True)

    # Link to VK Ads account
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    # LeadsTech label (sub1 value for filtering)
    leadstech_label = Column(String(255), nullable=False)

    # Whether to include this cabinet in analysis
    enabled = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    # Relationship
    account = relationship("Account", backref="leadstech_cabinet")

    def __repr__(self):
        return f"<LeadsTechCabinet(account_id={self.account_id}, label='{self.leadstech_label}')>"


class LeadsTechAnalysisResult(Base):
    """LeadsTech analysis results - banner-level ROI data"""
    __tablename__ = "leadstech_analysis_results"

    id = Column(Integer, primary_key=True, index=True)

    # Cabinet info
    cabinet_name = Column(String(255), nullable=False, index=True)
    leadstech_label = Column(String(255), nullable=False)

    # Banner info
    banner_id = Column(BigInteger, nullable=False, index=True)

    # Financial data
    vk_spent = Column(Float, default=0.0)  # VK Ads spending
    lt_revenue = Column(Float, default=0.0)  # LeadsTech revenue
    profit = Column(Float, default=0.0)  # lt_revenue - vk_spent
    roi_percent = Column(Float, nullable=True)  # (profit / vk_spent) * 100

    # LeadsTech metrics
    lt_clicks = Column(Integer, default=0)
    lt_conversions = Column(Integer, default=0)
    lt_approved = Column(Integer, default=0)
    lt_inprogress = Column(Integer, default=0)
    lt_rejected = Column(Integer, default=0)

    # Analysis period
    date_from = Column(String(20), nullable=False)
    date_to = Column(String(20), nullable=False)

    # Timestamp
    created_at = Column(DateTime, default=get_moscow_time, nullable=False, index=True)

    def __repr__(self):
        return f"<LeadsTechAnalysisResult(banner_id={self.banner_id}, roi={self.roi_percent}, profit={self.profit})>"
