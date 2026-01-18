"""
Banner-Level Scaling Engine
Main orchestrator for the new banner-level auto-scaling system.

============================================================================
СХЕМА РАБОТЫ АВТОМАСШТАБИРОВАНИЯ
============================================================================

ФАЗА 1: КЛАССИФИКАЦИЯ БАННЕРОВ
------------------------------
1. Загружаем список активных баннеров:
   GET https://ads.vk.com/api/v2/banners.json?status=active&limit=200

2. Загружаем статистику для баннеров (батчами по 200 ID):
   GET https://ads.vk.com/api/v2/statistics/banners/day.json?id=123,456,789&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&metrics=base

   Ответ содержит: shows, clicks, spent, vk.goals (конверсии)

3. Классифицируем каждый баннер по условиям:
   - Positive: баннер соответствует условиям (например: goals >= 5 AND cost_per_goal < 150)
   - Negative: баннер НЕ соответствует условиям

4. Группируем по ad_group_id, находим группы с хотя бы 1 positive баннером

ФАЗА 2: ДУБЛИРОВАНИЕ ГРУПП
--------------------------
Для каждой группы с positive баннерами:

1. Получаем полную информацию о группе:
   GET https://ads.vk.com/api/v2/ad_groups/{group_id}.json

2. Создаём копию группы:
   POST https://ads.vk.com/api/v2/ad_groups.json
   Body: { campaign_id, name, budget, ... }

3. Получаем баннеры исходной группы:
   GET https://ads.vk.com/api/v2/banners.json?ad_group_id={group_id}

4. Копируем каждый баннер в новую группу:
   POST https://ads.vk.com/api/v2/banners.json
   Body: { ad_group_id: new_group_id, name, content_type, ... }

5. Управляем статусами баннеров через toggle:
   - Positive баннеры: status=active (если activate_positive_banners=true)
   - Negative баннеры: status=blocked (если duplicate_negative_banners=true, activate_negative=false)

   POST https://ads.vk.com/api/v2/banners/{banner_id}.json
   Body: { status: "active" | "blocked" }

RATE LIMITS:
- statistics/banners/day.json: 2 RPS (requests per second)
- Остальные endpoints: ~35 RPS
- Используем sleep=0.6 сек между запросами статистики

============================================================================
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass

from database import SessionLocal, crud
from database.models import ScalingConfig, Account
from utils.logging_setup import get_logger, set_context, clear_context
from utils.vk_api.banner_stats import (
    classify_banners_streaming,
    get_groups_with_positive_banners,
    get_group_banner_classification
)
from utils.vk_api.scaling import duplicate_ad_group_full, get_banners_by_ad_group, duplicate_ad_group_to_new_campaign
from utils.vk_api.ad_groups import get_ad_group_full
from utils.vk_api.campaigns import toggle_campaign_status
from services.banner_classifier import create_conditions_checker, get_classification_summary
from leadstech.roi_enricher import get_banners_by_ad_group as get_banners_mapping, enrich_groups_with_roi
from leadstech.roi_loader import BannerROIData, load_roi_data_for_accounts

# Module-level logger (fallback, without user context)
logger = get_logger(service="scaling_engine", function="scaling")

VK_API_BASE_URL = "https://ads.vk.com/api/v2"


@dataclass
class ScalingEngineConfig:
    """Configuration for the scaling engine"""
    activate_positive_banners: bool = True
    duplicate_negative_banners: bool = True
    activate_negative_banners: bool = False
    new_name: Optional[str] = None  # Group name template, supports {date}
    new_banner_name_template: Optional[str] = None  # Banner name template, supports {date}
    new_budget: Optional[float] = None
    duplicates_count: int = 1
    lookback_days: int = 7
    use_leadstech_roi: bool = False
    # Campaign duplication options
    duplicate_to_new_campaign: bool = False
    new_campaign_name: Optional[str] = None


@dataclass
class ScalingResult:
    """Result of scaling operation"""
    success: bool
    total_banners_analyzed: int
    positive_banners: int
    negative_banners: int
    groups_found: int
    groups_duplicated: int
    successful_duplications: int
    failed_duplications: int
    errors: List[str]


class BannerScalingEngine:
    """
    Main engine for banner-level scaling.

    Flow:
    1. Load all banners with stats (streaming, batched)
    2. Classify banners (positive/negative) based on conditions
    3. Find groups with at least one positive banner
    4. Duplicate these groups with banner status control via toggles
    """

    def __init__(
        self,
        config_id: int,
        user_id: int,
        task_id: int,
        db_session=None
    ):
        self.config_id = config_id
        self.user_id = user_id
        self.task_id = task_id
        self.db = db_session or SessionLocal()
        self._own_db = db_session is None

        # Create logger with user context
        self.logger = get_logger(service="scaling_engine", function="scaling", user_id=user_id)

        self._load_config()

    def _load_config(self):
        """Load scaling config and conditions from database"""
        self.config = crud.get_scaling_config_by_id(self.db, self.config_id)
        if not self.config:
            raise ValueError(f"Scaling config {self.config_id} not found")

        self.conditions = crud.get_scaling_conditions(self.db, self.config_id)
        self.conditions_list = [
            {"metric": c.metric, "operator": c.operator, "value": c.value}
            for c in self.conditions
        ]

        # Load engine config from model
        self.engine_config = ScalingEngineConfig(
            activate_positive_banners=getattr(self.config, 'activate_positive_banners', True),
            duplicate_negative_banners=getattr(self.config, 'duplicate_negative_banners', True),
            activate_negative_banners=getattr(self.config, 'activate_negative_banners', False),
            new_name=getattr(self.config, 'new_name', None),
            new_banner_name_template=getattr(self.config, 'new_banner_name_template', None),
            new_budget=getattr(self.config, 'new_budget', None),
            duplicates_count=getattr(self.config, 'duplicates_count', 1) or 1,
            lookback_days=getattr(self.config, 'lookback_days', 7) or 7,
            use_leadstech_roi=getattr(self.config, 'use_leadstech_roi', False),
            duplicate_to_new_campaign=getattr(self.config, 'duplicate_to_new_campaign', False),
            new_campaign_name=getattr(self.config, 'new_campaign_name', None)
        )

        # Campaign cache for duplicate_to_new_campaign mode
        self._campaign_cache: Dict[tuple, int] = {}
        # Campaign data cache (to avoid re-fetching original campaign info)
        self._campaign_data_cache: Dict[int, dict] = {}
        # Counter for campaign numbering (e.g., "Копия 1", "Копия 2", ...)
        self._campaign_counter: int = 0

        logger.info(f"Loaded config: {self.config.name}")
        logger.info(f"  Conditions: {len(self.conditions_list)}")
        logger.info(f"  Toggle settings: activate_positive={self.engine_config.activate_positive_banners}, "
                    f"duplicate_negative={self.engine_config.duplicate_negative_banners}, "
                    f"activate_negative={self.engine_config.activate_negative_banners}")
        if self.engine_config.duplicate_to_new_campaign:
            logger.info(f"  Duplicate to new campaign: ENABLED (name: {self.engine_config.new_campaign_name or 'original + date'})")

    def _get_cached_campaign(
        self,
        account_name: str,
        original_campaign_id: int
    ) -> Optional[int]:
        """
        Get cached campaign ID if it was already created.

        Args:
            account_name: Account name
            original_campaign_id: Original campaign ID

        Returns:
            Cached campaign ID or None if not yet created
        """
        cache_key = (account_name, original_campaign_id)
        return self._campaign_cache.get(cache_key)

    def _cache_campaign(
        self,
        account_name: str,
        original_campaign_id: int,
        new_campaign_id: int
    ):
        """Cache newly created campaign ID."""
        cache_key = (account_name, original_campaign_id)
        self._campaign_cache[cache_key] = new_campaign_id
        logger.info(f"    Cached campaign {new_campaign_id} for key {cache_key}")

    def _get_next_campaign_number(self) -> int:
        """Get next campaign number and increment counter."""
        self._campaign_counter += 1
        return self._campaign_counter

    def _prepare_campaign_data(
        self,
        token: str,
        original_campaign_id: int
    ) -> Optional[dict]:
        """
        Prepare campaign data for creation (without ad_groups).

        Args:
            token: VK API token
            original_campaign_id: Original campaign ID

        Returns:
            Campaign data dict or None on error
        """
        from utils.vk_api.campaigns import get_campaign_full, copy_campaign_settings

        # Use cached campaign data if available
        if original_campaign_id in self._campaign_data_cache:
            original_campaign = self._campaign_data_cache[original_campaign_id]
            logger.info(f"    Using cached campaign data for {original_campaign_id}")
        else:
            # Load original campaign
            original_campaign = get_campaign_full(token, VK_API_BASE_URL, original_campaign_id)
            if not original_campaign:
                logger.error(f"    Could not load original campaign {original_campaign_id}")
                return None
            # Cache it
            self._campaign_data_cache[original_campaign_id] = original_campaign

        # Prepare new campaign name with date and number
        date_suffix = datetime.now().strftime("%d-%m-%y")
        campaign_number = self._get_next_campaign_number()

        if self.engine_config.new_campaign_name:
            # Format: "UserName 1 03-01-26", "UserName 2 03-01-26", ...
            new_name = f"{self.engine_config.new_campaign_name} {campaign_number} {date_suffix}"
        else:
            # Format: "OriginalName 1 03-01-26", "OriginalName 2 03-01-26", ...
            original_name = original_campaign.get('name', 'Campaign')
            new_name = f"{original_name} {campaign_number} {date_suffix}"

        # Copy settings from original campaign
        campaign_data = copy_campaign_settings(original_campaign)
        campaign_data['name'] = new_name
        campaign_data['status'] = 'active'  # Create as active

        # Ensure objective is set (required field)
        if 'objective' not in campaign_data:
            logger.error(f"    Original campaign {original_campaign_id} has no objective!")
            return None

        return campaign_data

    def run(self, accounts: List[Account]) -> ScalingResult:
        """
        Execute the scaling process.

        Args:
            accounts: List of Account objects to process

        Returns:
            ScalingResult with statistics
        """
        # Set logging context for this scaling run
        set_context(user_id=self.user_id, service="scaling_engine", function="scaling")

        try:
            logger.info(f"")
            logger.info(f"{'='*80}")
            logger.info(f"BANNER-LEVEL SCALING: {self.config.name}")
            logger.info(f"{'='*80}")

            if not self.conditions_list:
                logger.warning("No conditions defined, skipping")
                return ScalingResult(
                    success=False,
                    total_banners_analyzed=0,
                    positive_banners=0,
                    negative_banners=0,
                    groups_found=0,
                    groups_duplicated=0,
                    successful_duplications=0,
                    failed_duplications=0,
                    errors=["No conditions defined"]
                )

            # Calculate date range
            date_to = datetime.now().strftime("%Y-%m-%d")
            date_from = (datetime.now() - timedelta(days=self.engine_config.lookback_days)).strftime("%Y-%m-%d")

            logger.info(f"Analysis period: {date_from} to {date_to}")
            logger.info(f"Accounts to process: {len(accounts)}")

            # Separate ROI conditions from other conditions
            roi_conditions = [c for c in self.conditions_list if c.get('metric') == 'roi']
            other_conditions = [c for c in self.conditions_list if c.get('metric') != 'roi']

            logger.info(f"Conditions: {len(roi_conditions)} ROI, {len(other_conditions)} other")

            # Pre-filter banners by ROI if ROI conditions exist
            roi_filtered_banner_ids: Optional[Set[int]] = None
            roi_data_by_banner: Dict[int, BannerROIData] = {}

            if roi_conditions:
                logger.info("ROI conditions detected - loading LeadsTech data first...")
                self._update_task_progress("loading_roi", "Loading ROI data from LeadsTech...")
                roi_data_by_banner = self._load_leadstech_roi_data(accounts, date_from, date_to)
                logger.info(f"Loaded ROI data for {len(roi_data_by_banner)} banners")

                # Filter banners by ROI conditions
                roi_filtered_banner_ids = self._filter_banners_by_roi(roi_data_by_banner, roi_conditions)
                logger.info(f"Banners passing ROI conditions: {len(roi_filtered_banner_ids)}")

                if not roi_filtered_banner_ids:
                    logger.info("No banners pass ROI conditions - nothing to scale")
                    return ScalingResult(
                        success=True,
                        total_banners_analyzed=len(roi_data_by_banner),
                        positive_banners=0,
                        negative_banners=len(roi_data_by_banner),
                        groups_found=0,
                        groups_duplicated=0,
                        successful_duplications=0,
                        failed_duplications=0,
                        errors=[]
                    )

            # Create conditions checker for other (non-ROI) conditions
            # If no other conditions, all ROI-filtered banners are positive
            if other_conditions:
                check_conditions = create_conditions_checker(other_conditions)
            else:
                # All banners that passed ROI filter are positive
                check_conditions = lambda stats, banner_id: True

            # Результаты классификации со всех аккаунтов
            all_positive_ids: Set[int] = set()      # ID баннеров, соответствующих условиям
            all_negative_ids: Set[int] = set()      # ID баннеров, НЕ соответствующих условиям
            all_banner_to_group: Dict[int, int] = {}  # banner_id -> ad_group_id
            account_by_group: Dict[int, Account] = {}  # group_id -> account (для получения токена)

            # ========================================================================
            # ФАЗА 1: КЛАССИФИКАЦИЯ
            # Загружаем баннеры и статистику, классифицируем по условиям
            # ========================================================================
            self._update_task_progress("classifying", "Classifying banners...")

            for account in accounts:
                logger.info(f"")
                logger.info(f"Processing account: {account.name}")

                try:
                    # Потоковая классификация баннеров:
                    # 1. GET /banners.json?status=active - загружаем список баннеров
                    # 2. GET /statistics/banners/day.json?id=... - загружаем статистику батчами по 200
                    # 3. Для каждого баннера проверяем условия -> positive или negative
                    # If ROI pre-filter exists, only process those banners (huge optimization for 20k+ banners)
                    positive_ids, negative_ids, banner_to_group = classify_banners_streaming(
                        token=account.api_token,
                        base_url=VK_API_BASE_URL,
                        date_from=date_from,
                        date_to=date_to,
                        check_conditions_fn=check_conditions,
                        include_blocked=True,
                        batch_size=200,  # VK API max limit is 250
                        progress_callback=lambda p, t: self._update_task_progress(
                            "classifying",
                            f"Account {account.name}: {p} banners processed"
                        ),
                        cancel_check_fn=self._is_task_cancelled,
                        only_banner_ids=roi_filtered_banner_ids  # Pre-filtered by ROI (or None for all)
                    )

                    # Track which account owns which groups
                    for banner_id, group_id in banner_to_group.items():
                        account_by_group[group_id] = account

                    # Merge results
                    all_positive_ids.update(positive_ids)
                    all_negative_ids.update(negative_ids)
                    all_banner_to_group.update(banner_to_group)

                    logger.info(f"  Account {account.name}: {len(positive_ids)} positive, {len(negative_ids)} negative")

                    # Check if cancelled during classification
                    if self._is_task_cancelled():
                        logger.warning("Task cancelled by user during classification")
                        break

                except Exception as e:
                    logger.error(f"  Error processing account {account.name}: {e}")
                    self._update_task_error(f"Error in account {account.name}: {str(e)}")

            # Check if task was cancelled
            if self._is_task_cancelled():
                logger.warning("Task cancelled - stopping before duplication phase")
                return ScalingResult(
                    success=False,
                    total_banners_analyzed=len(all_banner_to_group),
                    positive_banners=len(all_positive_ids),
                    negative_banners=len(all_negative_ids),
                    groups_found=0,
                    groups_duplicated=0,
                    successful_duplications=0,
                    failed_duplications=0,
                    errors=["Task cancelled by user"]
                )

            # Summary after classification
            summary = get_classification_summary(all_positive_ids, all_negative_ids, all_banner_to_group)
            logger.info(f"")
            logger.info(f"Classification complete:")
            logger.info(f"  Total banners: {summary['total_banners']}")
            logger.info(f"  Positive: {summary['positive_banners']} ({summary['positive_percent']:.1f}%)")
            logger.info(f"  Negative: {summary['negative_banners']}")
            logger.info(f"  Groups to duplicate: {summary['groups_to_duplicate']}")

            # Phase 2: Duplication
            groups_to_duplicate = get_groups_with_positive_banners(all_positive_ids, all_banner_to_group)

            if not groups_to_duplicate:
                logger.info("No groups with positive banners found")
                return ScalingResult(
                    success=True,
                    total_banners_analyzed=summary['total_banners'],
                    positive_banners=summary['positive_banners'],
                    negative_banners=summary['negative_banners'],
                    groups_found=0,
                    groups_duplicated=0,
                    successful_duplications=0,
                    failed_duplications=0,
                    errors=[]
                )

            self._update_task_progress("duplicating", f"Duplicating {len(groups_to_duplicate)} groups...")

            # Update task total operations
            total_operations = len(groups_to_duplicate) * self.engine_config.duplicates_count
            self._update_task_total(total_operations)

            # If duplicating to new campaign, collect group -> campaign mappings first (parallel)
            group_to_campaign: Dict[int, int] = {}
            if self.engine_config.duplicate_to_new_campaign:
                logger.info(f"")
                logger.info(f"Mode: DUPLICATE TO NEW CAMPAIGN - collecting campaign info (parallel)...")

                def fetch_group_campaign(group_id: int) -> Tuple[int, Optional[int]]:
                    account = account_by_group.get(group_id)
                    if not account:
                        return (group_id, None)
                    group_data = get_ad_group_full(account.api_token, VK_API_BASE_URL, group_id)
                    if group_data:
                        return (group_id, group_data.get('ad_plan_id'))
                    return (group_id, None)

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(fetch_group_campaign, gid) for gid in groups_to_duplicate]
                    for future in as_completed(futures):
                        try:
                            gid, campaign_id = future.result()
                            if campaign_id:
                                group_to_campaign[gid] = campaign_id
                                logger.info(f"  Group {gid} -> Campaign {campaign_id}")
                        except Exception as e:
                            logger.warning(f"  Error fetching group info: {e}")
                logger.info(f"Mapped {len(group_to_campaign)} groups to campaigns")

            successful = 0
            failed = 0
            errors = []
            completed = 0

            for group_id in groups_to_duplicate:
                # Check if task was cancelled
                if self._is_task_cancelled():
                    logger.warning("Task cancelled by user")
                    break

                account = account_by_group.get(group_id)
                if not account:
                    logger.error(f"No account found for group {group_id}")
                    failed += 1
                    errors.append(f"No account for group {group_id}")
                    continue

                # Get classification for this specific group
                group_positive, group_negative = get_group_banner_classification(
                    group_id, all_positive_ids, all_negative_ids, all_banner_to_group
                )

                logger.info(f"")
                logger.info(f"Duplicating group {group_id} [Account: {account.name}]: {len(group_positive)} positive, {len(group_negative)} negative")

                # Activate campaign before duplicating (so ads can be shown)
                if self.engine_config.activate_positive_banners:
                    logger.info(f"  Checking campaign status before duplication...")
                    self._activate_campaign_for_group(account.api_token, group_id)

                # Handle duplication - either to new campaign or to same campaign
                original_campaign_id = group_to_campaign.get(group_id) if self.engine_config.duplicate_to_new_campaign else None

                for dup_num in range(1, self.engine_config.duplicates_count + 1):
                    if self._is_task_cancelled():
                        break

                    try:
                        self._update_task_current(group_id, f"Group {group_id} (copy {dup_num}/{self.engine_config.duplicates_count})")

                        # Check if we need to duplicate to new campaign
                        if self.engine_config.duplicate_to_new_campaign and original_campaign_id:
                            # Check if campaign already exists in cache
                            cached_campaign_id = self._get_cached_campaign(account.name, original_campaign_id)

                            if cached_campaign_id:
                                # Campaign already created - duplicate to it
                                logger.info(f"  Using existing new campaign {cached_campaign_id}")
                                result = self._duplicate_group_with_classification(
                                    account=account,
                                    group_id=group_id,
                                    positive_banner_ids=set(group_positive),
                                    negative_banner_ids=set(group_negative),
                                    target_campaign_id=cached_campaign_id
                                )
                            else:
                                # First group for this campaign - create campaign with group
                                logger.info(f"  Creating NEW campaign with group (first group for campaign {original_campaign_id})")

                                # Prepare campaign data
                                campaign_data = self._prepare_campaign_data(account.api_token, original_campaign_id)
                                if not campaign_data:
                                    failed += 1
                                    error_msg = f"Failed to prepare campaign data for group {group_id}"
                                    errors.append(f"[{account.name}] {error_msg}")
                                    logger.error(f"  {error_msg}")
                                    self._add_task_error(error_msg, account.name, group_id, None)
                                    completed += 1
                                    self._update_task_progress_numbers(completed, successful, failed)
                                    continue

                                # Create campaign with group (with classification - banners are created with correct status)
                                result = duplicate_ad_group_to_new_campaign(
                                    token=account.api_token,
                                    base_url=VK_API_BASE_URL,
                                    ad_group_id=group_id,
                                    campaign_data=campaign_data,
                                    new_name=self.engine_config.new_name,
                                    new_budget=self.engine_config.new_budget,
                                    auto_activate=False,
                                    rate_limit_delay=0.03,
                                    account_name=account.name,
                                    # Pass classification for immediate status/name assignment
                                    positive_banner_ids=set(group_positive),
                                    negative_banner_ids=set(group_negative),
                                    activate_positive=self.engine_config.activate_positive_banners,
                                    activate_negative=self.engine_config.activate_negative_banners,
                                    duplicate_negative=self.engine_config.duplicate_negative_banners,
                                    banner_name_template=self.engine_config.new_banner_name_template
                                )

                                if result.get("success"):
                                    # Cache the new campaign ID for subsequent groups
                                    new_campaign_id = result.get("new_campaign_id")
                                    if new_campaign_id:
                                        self._cache_campaign(account.name, original_campaign_id, new_campaign_id)
                        else:
                            # Normal duplication to same campaign
                            result = self._duplicate_group_with_classification(
                                account=account,
                                group_id=group_id,
                                positive_banner_ids=set(group_positive),
                                negative_banner_ids=set(group_negative),
                                target_campaign_id=None
                            )

                        if result.get("success"):
                            successful += 1
                            logger.info(f"  Copy {dup_num}: success -> {result.get('new_group_id')}")

                            # Create log entry
                            self._create_scaling_log(
                                account=account,
                                group_id=group_id,
                                result=result,
                                positive_ids=group_positive,
                                negative_ids=group_negative
                            )
                        else:
                            failed += 1
                            error_msg = result.get("error", "Unknown error")
                            errors.append(f"[{account.name}] Group {group_id}: {error_msg}")
                            logger.error(f"  Copy {dup_num} [Account: {account.name}]: failed - {error_msg}")
                            # Add error to task errors list for frontend notifications
                            self._add_task_error(error_msg, account.name, group_id, result.get("original_group_name"))

                    except Exception as e:
                        failed += 1
                        error_msg = str(e)
                        errors.append(f"[{account.name}] Group {group_id}: {error_msg}")
                        logger.error(f"  Copy {dup_num} [Account: {account.name}]: exception - {e}")
                        # Add error to task errors list for frontend notifications
                        self._add_task_error(error_msg, account.name, group_id, None)

                    completed += 1
                    self._update_task_progress_numbers(completed, successful, failed)

            # Final summary
            logger.info(f"")
            logger.info(f"{'='*80}")
            logger.info(f"SCALING COMPLETED: {self.config.name}")
            logger.info(f"{'='*80}")
            logger.info(f"  Successful: {successful}")
            logger.info(f"  Failed: {failed}")
            logger.info(f"{'='*80}")

            return ScalingResult(
                success=failed == 0,
                total_banners_analyzed=summary['total_banners'],
                positive_banners=summary['positive_banners'],
                negative_banners=summary['negative_banners'],
                groups_found=len(groups_to_duplicate),
                groups_duplicated=successful,
                successful_duplications=successful,
                failed_duplications=failed,
                errors=errors
            )

        finally:
            clear_context()  # Clear logging context
            if self._own_db:
                self.db.close()

    def _duplicate_group_with_classification(
        self,
        account: Account,
        group_id: int,
        positive_banner_ids: Set[int],
        negative_banner_ids: Set[int],
        target_campaign_id: Optional[int] = None
    ) -> dict:
        """
        Duplicate a group with banner status control based on classification.

        Banner statuses and names are set at creation time (no post-updates needed).
        This is much faster than creating blocked and then updating each banner.

        Args:
            target_campaign_id: If set, duplicate to this campaign instead of original
        """
        # Duplicate the group with classification - banners are created with correct status/name
        result = duplicate_ad_group_full(
            token=account.api_token,
            base_url=VK_API_BASE_URL,
            ad_group_id=group_id,
            new_name=self.engine_config.new_name,
            new_budget=self.engine_config.new_budget,
            auto_activate=False,
            rate_limit_delay=0.03,
            account_name=account.name,
            target_campaign_id=target_campaign_id,
            # Pass classification for immediate status/name assignment
            positive_banner_ids=positive_banner_ids,
            negative_banner_ids=negative_banner_ids,
            activate_positive=self.engine_config.activate_positive_banners,
            activate_negative=self.engine_config.activate_negative_banners,
            duplicate_negative=self.engine_config.duplicate_negative_banners,
            banner_name_template=self.engine_config.new_banner_name_template
        )

        if not result.get("success"):
            return result

        # Log summary
        duplicated_banners = result.get("duplicated_banners", [])
        skipped_banners = result.get("skipped_banners", [])
        group_status = result.get("group_status", "blocked")

        active_count = sum(1 for b in duplicated_banners if b.get("status") == "active")
        blocked_count = sum(1 for b in duplicated_banners if b.get("status") == "blocked")

        logger.info(f"    Created {len(duplicated_banners)} banners (active: {active_count}, blocked: {blocked_count}, skipped: {len(skipped_banners)})")
        logger.info(f"    Group status: {group_status}")

        # Update result with classification info
        result["positive_count"] = active_count
        result["negative_count"] = blocked_count
        result["activated_banners"] = active_count

        return result

    def _activate_campaign_for_group(self, token: str, group_id: int) -> bool:
        """
        Get campaign ID from group and activate it if blocked.
        Returns True if campaign is active (or was activated), False on error.
        """
        try:
            # Get group details to find campaign ID
            group_data = get_ad_group_full(token, VK_API_BASE_URL, group_id)
            if not group_data:
                logger.warning(f"    Could not load group {group_id} to find campaign")
                return False

            campaign_id = group_data.get("ad_plan_id")
            if not campaign_id:
                logger.warning(f"    Group {group_id} has no campaign ID (ad_plan_id)")
                return False

            # Check campaign status
            from utils.vk_api.campaigns import get_campaign_full
            campaign_data = get_campaign_full(token, VK_API_BASE_URL, campaign_id)
            if not campaign_data:
                logger.warning(f"    Could not load campaign {campaign_id}")
                return False

            campaign_status = campaign_data.get("status")
            logger.info(f"    Campaign {campaign_id} status: {campaign_status}")

            if campaign_status == "active":
                logger.info(f"    Campaign {campaign_id} is already active")
                return True

            # Activate the campaign
            logger.info(f"    Activating campaign {campaign_id}...")
            result = toggle_campaign_status(token, VK_API_BASE_URL, campaign_id, "active")
            if result.get("success"):
                logger.info(f"    ✓ Campaign {campaign_id} activated successfully")
                return True
            else:
                logger.error(f"    ✗ Failed to activate campaign {campaign_id}: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"    Error activating campaign for group {group_id}: {e}")
            return False

    def _create_scaling_log(
        self,
        account: Account,
        group_id: int,
        result: dict,
        positive_ids: List[int],
        negative_ids: List[int]
    ):
        """Create scaling log entry with classification data"""
        try:
            log = crud.create_scaling_log(
                db=self.db,
                user_id=self.user_id,
                config_id=self.config_id,
                config_name=self.config.name,
                account_name=account.name,
                original_group_id=group_id,
                original_group_name=result.get("original_group_name"),
                new_group_id=result.get("new_group_id"),
                new_group_name=result.get("new_group_name"),
                requested_name=self.engine_config.new_name,
                stats_snapshot=None,  # Not storing full stats to save space
                success=result.get("success", False),
                error_message=result.get("error"),
                total_banners=result.get("total_banners", 0),
                duplicated_banners=len(result.get("duplicated_banners", [])),
                duplicated_banner_ids=[
                    {"original_id": b.get("original_id"), "new_id": b.get("new_id"), "name": b.get("name")}
                    for b in result.get("duplicated_banners", [])
                ],
                task_id=self.task_id
            )

            # Update with classification data (new fields)
            if log:
                log.positive_banner_ids = positive_ids
                log.negative_banner_ids = negative_ids
                log.positive_count = len(positive_ids)
                log.negative_count = len(negative_ids)
                self.db.commit()

        except Exception as e:
            logger.error(f"Failed to create scaling log: {e}")

    def _update_task_progress(self, phase: str, message: str):
        """Update task phase and message"""
        try:
            crud.update_scaling_task_progress(
                self.db, self.task_id,
                current_group_name=f"[{phase}] {message}"
            )
        except Exception as e:
            logger.debug(f"Failed to update task progress: {e}")

    def _update_task_total(self, total: int):
        """Update task total operations"""
        try:
            task = crud.get_scaling_task(self.db, self.task_id)
            if task:
                task.total_operations = total
                self.db.commit()
        except Exception as e:
            logger.debug(f"Failed to update task total: {e}")

    def _update_task_current(self, group_id: int, name: str):
        """Update current operation info"""
        try:
            crud.update_scaling_task_progress(
                self.db, self.task_id,
                current_group_id=group_id,
                current_group_name=name
            )
        except Exception as e:
            logger.debug(f"Failed to update task current: {e}")

    def _update_task_progress_numbers(self, completed: int, successful: int, failed: int):
        """Update task progress numbers"""
        try:
            crud.update_scaling_task_progress(
                self.db, self.task_id,
                completed=completed,
                successful=successful,
                failed=failed
            )
        except Exception as e:
            logger.debug(f"Failed to update task numbers: {e}")

    def _update_task_error(self, error: str):
        """Update task last error"""
        try:
            crud.update_scaling_task_progress(
                self.db, self.task_id,
                last_error=error
            )
        except Exception as e:
            logger.debug(f"Failed to update task error: {e}")

    def _add_task_error(self, error_msg: str, account_name: str, group_id: int, group_name: Optional[str]):
        """Add error to task errors list for frontend notifications"""
        try:
            crud.update_scaling_task_progress(
                self.db, self.task_id,
                last_error=error_msg,
                add_error={
                    "message": error_msg,
                    "account": account_name,
                    "group_id": group_id,
                    "group_name": group_name
                }
            )
        except Exception as e:
            logger.debug(f"Failed to add task error: {e}")

    def _is_task_cancelled(self) -> bool:
        """Check if task was cancelled by user"""
        try:
            task = crud.get_scaling_task(self.db, self.task_id)
            return task and task.status == 'cancelled'
        except:
            return False

    def _load_leadstech_roi_data(
        self,
        accounts: List[Account],
        date_from: str,
        date_to: str
    ) -> Dict[int, BannerROIData]:
        """
        Load ROI data from LeadsTech for all accounts with labels.

        Args:
            accounts: List of accounts to process
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)

        Returns:
            Dict mapping banner_id to BannerROIData
        """
        from leadstech.leadstech_client import LeadstechClient, LeadstechClientConfig
        from leadstech.vk_client import VkAdsClient, VkAdsConfig

        # Load LeadsTech config
        lt_config = crud.get_leadstech_config(self.db, self.user_id)
        if not lt_config:
            logger.warning("No LeadsTech config found, ROI conditions will fail for all banners")
            return {}

        if not lt_config.login or not lt_config.password:
            logger.warning("LeadsTech credentials not configured")
            return {}

        # Get banner sub fields from config or use default
        banner_sub_fields = lt_config.banner_sub_fields or ["sub4", "sub5"]
        if isinstance(banner_sub_fields, str):
            import json
            try:
                banner_sub_fields = json.loads(banner_sub_fields)
            except (json.JSONDecodeError, TypeError):
                banner_sub_fields = [banner_sub_fields]

        logger.info(f"LeadsTech config loaded: base_url={lt_config.base_url}, sub_fields={banner_sub_fields}")

        # Create LeadsTech client (with DB caching for token)
        lt_client = LeadstechClient(
            LeadstechClientConfig(
                base_url=lt_config.base_url or "https://api.leads.tech",
                login=lt_config.login,
                password=lt_config.password,
                banner_sub_fields=banner_sub_fields
            ),
            db=self.db,
            user_id=self.user_id
        )

        # Factory to create VK client for each account
        def vk_client_factory(account: Account) -> VkAdsClient:
            return VkAdsClient(VkAdsConfig(
                base_url=VK_API_BASE_URL,
                api_token=account.api_token
            ))

        # Progress callback
        def progress_callback(message: str):
            self._update_task_progress("loading_roi", message)

        # Load ROI data
        try:
            return load_roi_data_for_accounts(
                lt_client=lt_client,
                vk_client_factory=vk_client_factory,
                accounts=accounts,
                date_from=date_from,
                date_to=date_to,
                banner_sub_fields=banner_sub_fields,
                progress_callback=progress_callback,
                cancel_check_fn=self._is_task_cancelled
            )
        except Exception as e:
            logger.error(f"Failed to load LeadsTech ROI data: {e}")
            return {}

    def _filter_banners_by_roi(
        self,
        roi_data: Dict[int, BannerROIData],
        roi_conditions: List[dict]
    ) -> Set[int]:
        """
        Filter banners by ROI conditions.

        Args:
            roi_data: Dict mapping banner_id to BannerROIData
            roi_conditions: List of ROI conditions [{"metric": "roi", "operator": ">=", "value": 50}]

        Returns:
            Set of banner IDs that pass ALL ROI conditions
        """
        from services.banner_classifier import check_banner_conditions

        passed_ids: Set[int] = set()

        for banner_id, roi_obj in roi_data.items():
            if roi_obj.roi_percent is None:
                # No ROI data (spent = 0), skip this banner
                continue

            # Create stats dict with roi value for condition checking
            stats = {"roi": roi_obj.roi_percent}

            # Check all ROI conditions
            if check_banner_conditions(stats, roi_conditions, verbose=False):
                passed_ids.add(banner_id)

        logger.info(f"ROI filter: {len(passed_ids)}/{len(roi_data)} banners passed ROI conditions")
        return passed_ids


def run_banner_scaling(
    config_id: int,
    user_id: int,
    task_id: int,
    accounts: List[Account],
    db_session=None
) -> ScalingResult:
    """
    Convenience function to run banner-level scaling.

    Args:
        config_id: Scaling configuration ID
        user_id: User ID
        task_id: Scaling task ID for progress tracking
        accounts: List of accounts to process
        db_session: Optional database session

    Returns:
        ScalingResult with statistics
    """
    engine = BannerScalingEngine(
        config_id=config_id,
        user_id=user_id,
        task_id=task_id,
        db_session=db_session
    )
    return engine.run(accounts)
