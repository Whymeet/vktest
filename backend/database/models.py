"""
Database models for VK Ads Manager
Multi-tenant architecture with user isolation
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Float, DateTime, Text, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from utils.time_utils import get_moscow_time

Base = declarative_base()


# ===== User Models (Multi-tenancy) =====

class User(Base):
    """User model for multi-tenant architecture"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)

    # Status
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)  # Admin privileges

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)
    last_login = Column(DateTime, nullable=True)

    # Relationships - all user data
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", cascade="all, delete-orphan")
    whitelist_banners = relationship("WhitelistBanner", back_populates="user", cascade="all, delete-orphan")
    disable_rules = relationship("DisableRule", back_populates="user", cascade="all, delete-orphan")
    scaling_configs = relationship("ScalingConfig", back_populates="user", cascade="all, delete-orphan")
    process_states = relationship("ProcessState", back_populates="user", cascade="all, delete-orphan")
    leadstech_config = relationship("LeadsTechConfig", back_populates="user", cascade="all, delete-orphan", uselist=False)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class UserSettings(Base):
    """Per-user settings (key-value store) - replaces global Settings"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(JSON, nullable=False)

    # Description
    description = Column(Text, nullable=True)

    # Unique constraint: one key per user
    __table_args__ = (
        UniqueConstraint('user_id', 'key', name='uix_user_settings_key'),
    )

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    # Relationship
    user = relationship("User", back_populates="settings")

    def __repr__(self):
        return f"<UserSettings(user_id={self.user_id}, key='{self.key}')>"


class Account(Base):
    """VK Ads account model"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, nullable=False, index=True)  # VK account ID
    name = Column(String(255), nullable=False)
    api_token = Column(String(255), nullable=False)
    client_id = Column(Integer, nullable=False)

    # Unique constraint: account_id unique per user
    __table_args__ = (
        UniqueConstraint('user_id', 'account_id', name='uix_user_account'),
    )

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    # Relationships
    user = relationship("User", back_populates="accounts")
    banner_actions = relationship("BannerAction", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(account_id={self.account_id}, name='{self.name}')>"


class WhitelistBanner(Base):
    """Whitelist banners model"""
    __tablename__ = "whitelist_banners"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    banner_id = Column(BigInteger, nullable=False, index=True)

    # Unique constraint: banner_id unique per user
    __table_args__ = (
        UniqueConstraint('user_id', 'banner_id', name='uix_user_whitelist_banner'),
    )

    # Optional metadata
    note = Column(Text, nullable=True)
    added_by = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)

    # Relationship
    user = relationship("User", back_populates="whitelist_banners")

    def __repr__(self):
        return f"<WhitelistBanner(banner_id={self.banner_id})>"


class BannerAction(Base):
    """Banner action history (enabled/disabled) - полный лог всех отключённых групп"""
    __tablename__ = "banner_actions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Banner info
    banner_id = Column(BigInteger, nullable=False, index=True)

    # Unique constraint: banner_id unique per user
    __table_args__ = (
        UniqueConstraint('user_id', 'banner_id', name='uix_user_active_banner'),
    )
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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Process identification
    name = Column(String(50), nullable=False, index=True)  # 'scheduler', 'analysis', 'bot'
    pid = Column(Integer, nullable=True)  # OS process ID

    # Unique constraint: one process type per user
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_process'),
    )

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

    # Relationship
    user = relationship("User", back_populates="process_states")

    def __repr__(self):
        return f"<ProcessState(name='{self.name}', pid={self.pid}, status='{self.status}')>"


class LeadsTechConfig(Base):
    """LeadsTech per-user configuration"""
    __tablename__ = "leadstech_config"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

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

    # Relationship
    user = relationship("User", back_populates="leadstech_config")

    def __repr__(self):
        return f"<LeadsTechConfig(login='{self.login}', lookback_days={self.lookback_days})>"


class LeadsTechCabinet(Base):
    """LeadsTech cabinet mapping to VK Ads account"""
    __tablename__ = "leadstech_cabinets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

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


# ===== Auto-Scaling Models =====

class ScalingConfigAccount(Base):
    """Many-to-many link between ScalingConfig and Account"""
    __tablename__ = "scaling_config_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("scaling_configs.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)

    def __repr__(self):
        return f"<ScalingConfigAccount(config_id={self.config_id}, account_id={self.account_id})>"


class ScalingConfig(Base):
    """Auto-scaling configuration"""
    __tablename__ = "scaling_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Basic settings
    name = Column(String(255), nullable=False)  # Name of this scaling config
    enabled = Column(Boolean, default=False)

    # Schedule settings
    schedule_time = Column(String(10), nullable=False, default="08:00")  # HH:MM format (MSK)

    # Target account (deprecated - use scaling_config_accounts for multiple accounts)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    # Scaling options
    new_budget = Column(Float, nullable=True)  # New budget for duplicated groups (NULL = same as original)
    auto_activate = Column(Boolean, default=False)  # Activate duplicated groups immediately
    lookback_days = Column(Integer, default=7)  # Period for statistics analysis
    duplicates_count = Column(Integer, default=1)  # Number of duplicates to create per group

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)
    last_run_at = Column(DateTime, nullable=True)  # Last execution time

    # Relationships
    user = relationship("User", back_populates="scaling_configs")
    conditions = relationship("ScalingCondition", back_populates="config", cascade="all, delete-orphan")
    account = relationship("Account", backref="scaling_configs_legacy", foreign_keys=[account_id])
    config_accounts = relationship("ScalingConfigAccount", backref="config", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ScalingConfig(id={self.id}, name='{self.name}', enabled={self.enabled})>"


class ScalingCondition(Base):
    """Condition for auto-scaling (e.g., goals > 2, cost_per_goal < 200)"""
    __tablename__ = "scaling_conditions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to config
    config_id = Column(Integer, ForeignKey("scaling_configs.id", ondelete="CASCADE"), nullable=False)
    
    # Condition definition
    metric = Column(String(50), nullable=False)  # spent, shows, clicks, goals, cost_per_goal
    operator = Column(String(10), nullable=False)  # >, <, >=, <=, ==
    value = Column(Float, nullable=False)  # Threshold value
    
    # Order for display
    order = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    
    # Relationship
    config = relationship("ScalingConfig", back_populates="conditions")

    def __repr__(self):
        return f"<ScalingCondition(metric='{self.metric}', operator='{self.operator}', value={self.value})>"


class ScalingLog(Base):
    """Log of auto-scaling operations"""
    __tablename__ = "scaling_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Reference to config
    config_id = Column(Integer, ForeignKey("scaling_configs.id", ondelete="SET NULL"), nullable=True)
    config_name = Column(String(255), nullable=True)

    # Account info
    account_name = Column(String(255), nullable=True)
    
    # Original group info
    original_group_id = Column(BigInteger, nullable=False)
    original_group_name = Column(String(500), nullable=True)
    
    # New group info
    new_group_id = Column(BigInteger, nullable=True)
    new_group_name = Column(String(500), nullable=True)
    
    # Statistics at the time of duplication
    stats_snapshot = Column(JSON, nullable=True)  # {spent, shows, clicks, goals, cost_per_goal}
    
    # Result
    success = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    
    # Banners info
    total_banners = Column(Integer, default=0)
    duplicated_banners = Column(Integer, default=0)
    duplicated_banner_ids = Column(JSON, nullable=True)  # List of {original_id, new_id, name}

    # Timestamp
    created_at = Column(DateTime, default=get_moscow_time, nullable=False, index=True)

    def __repr__(self):
        return f"<ScalingLog(original={self.original_group_id}, new={self.new_group_id}, success={self.success})>"


# ===== Disable Rules Models (автоотключение объявлений) =====

class DisableRuleAccount(Base):
    """Many-to-many link between DisableRule and Account"""
    __tablename__ = "disable_rule_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("disable_rules.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)

    def __repr__(self):
        return f"<DisableRuleAccount(rule_id={self.rule_id}, account_id={self.account_id})>"


class DisableRule(Base):
    """
    Rule block for auto-disabling ads.
    Each rule contains multiple conditions that must ALL be met (AND logic).
    A rule can be applied to specific accounts.
    """
    __tablename__ = "disable_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Rule identification
    name = Column(String(255), nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)  # Optional description

    # Rule status
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher priority rules checked first

    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    updated_at = Column(DateTime, default=get_moscow_time, onupdate=get_moscow_time, nullable=False)

    # Relationships
    user = relationship("User", back_populates="disable_rules")
    conditions = relationship("DisableRuleCondition", back_populates="rule", cascade="all, delete-orphan")
    rule_accounts = relationship("DisableRuleAccount", backref="rule", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DisableRule(id={self.id}, name='{self.name}', enabled={self.enabled})>"


class DisableRuleCondition(Base):
    """
    Single condition within a disable rule.
    All conditions in a rule must be satisfied for the rule to trigger (AND logic).
    
    Available metrics:
    - goals: количество результатов/конверсий (vk_goals)
    - spent: потраченный бюджет (в рублях)
    - clicks: количество кликов
    - shows: количество показов
    - ctr: CTR (click-through rate, %)
    - cpc: цена за клик (cost per click)
    - cost_per_goal: цена за результат (spent / goals)
    
    Available operators:
    - equals (==)
    - not_equals (!=)
    - greater_than (>)
    - less_than (<)
    - greater_or_equal (>=)
    - less_or_equal (<=)
    """
    __tablename__ = "disable_rule_conditions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to rule
    rule_id = Column(Integer, ForeignKey("disable_rules.id", ondelete="CASCADE"), nullable=False)
    
    # Condition definition
    metric = Column(String(50), nullable=False)  # goals, spent, clicks, shows, ctr, cpc, cost_per_goal
    operator = Column(String(20), nullable=False)  # equals, not_equals, greater_than, less_than, greater_or_equal, less_or_equal
    value = Column(Float, nullable=False)  # Threshold value
    
    # Order for display
    order = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=get_moscow_time, nullable=False)
    
    # Relationship
    rule = relationship("DisableRule", back_populates="conditions")

    def __repr__(self):
        return f"<DisableRuleCondition(metric='{self.metric}', operator='{self.operator}', value={self.value})>"
