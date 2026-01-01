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
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass

from database import SessionLocal, crud
from database.models import ScalingConfig, Account
from utils.logging_setup import get_logger
from utils.vk_api.banner_stats import (
    classify_banners_streaming,
    get_groups_with_positive_banners,
    get_group_banner_classification
)
from utils.vk_api.scaling import duplicate_ad_group_full, get_banners_by_ad_group
from utils.vk_api.ad_groups import get_ad_group_full
from utils.vk_api.campaigns import toggle_campaign_status
from services.banner_classifier import create_conditions_checker, get_classification_summary
from leadstech.roi_enricher import get_banners_by_ad_group as get_banners_mapping, enrich_groups_with_roi
from leadstech.roi_loader import BannerROIData, load_roi_data_for_accounts

logger = get_logger(service="scaling_engine")

VK_API_BASE_URL = "https://ads.vk.com/api/v2"


@dataclass
class ScalingEngineConfig:
    """Configuration for the scaling engine"""
    activate_positive_banners: bool = True
    duplicate_negative_banners: bool = True
    activate_negative_banners: bool = False
    new_name: Optional[str] = None
    new_budget: Optional[float] = None
    duplicates_count: int = 1
    lookback_days: int = 7
    use_leadstech_roi: bool = False


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
            new_budget=getattr(self.config, 'new_budget', None),
            duplicates_count=getattr(self.config, 'duplicates_count', 1) or 1,
            lookback_days=getattr(self.config, 'lookback_days', 7) or 7,
            use_leadstech_roi=getattr(self.config, 'use_leadstech_roi', False)
        )

        logger.info(f"Loaded config: {self.config.name}")
        logger.info(f"  Conditions: {len(self.conditions_list)}")
        logger.info(f"  Toggle settings: activate_positive={self.engine_config.activate_positive_banners}, "
                    f"duplicate_negative={self.engine_config.duplicate_negative_banners}, "
                    f"activate_negative={self.engine_config.activate_negative_banners}")

    def run(self, accounts: List[Account]) -> ScalingResult:
        """
        Execute the scaling process.

        Args:
            accounts: List of Account objects to process

        Returns:
            ScalingResult with statistics
        """
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

                for dup_num in range(1, self.engine_config.duplicates_count + 1):
                    if self._is_task_cancelled():
                        break

                    try:
                        self._update_task_current(group_id, f"Group {group_id} (copy {dup_num}/{self.engine_config.duplicates_count})")

                        result = self._duplicate_group_with_classification(
                            account=account,
                            group_id=group_id,
                            positive_banner_ids=set(group_positive),
                            negative_banner_ids=set(group_negative)
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

                    except Exception as e:
                        failed += 1
                        errors.append(f"[{account.name}] Group {group_id}: {str(e)}")
                        logger.error(f"  Copy {dup_num} [Account: {account.name}]: exception - {e}")

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
            if self._own_db:
                self.db.close()

    def _duplicate_group_with_classification(
        self,
        account: Account,
        group_id: int,
        positive_banner_ids: Set[int],
        negative_banner_ids: Set[int]
    ) -> dict:
        """
        Duplicate a group with banner status control based on classification.

        Banner statuses are controlled by toggle settings:
        - Positive banners: active if activate_positive_banners else blocked
        - Negative banners: skipped if not duplicate_negative_banners,
                          otherwise active if activate_negative_banners else blocked
        """
        # First, duplicate the group with all banners using existing function
        # This creates the group in blocked status
        result = duplicate_ad_group_full(
            token=account.api_token,
            base_url=VK_API_BASE_URL,
            ad_group_id=group_id,
            new_name=self.engine_config.new_name,
            new_budget=self.engine_config.new_budget,
            auto_activate=False,  # We'll handle activation manually based on toggles
            rate_limit_delay=0.03,
            account_name=account.name
        )

        if not result.get("success"):
            return result

        new_group_id = result.get("new_group_id")
        duplicated_banners = result.get("duplicated_banners", [])

        # Now we need to set banner statuses based on classification
        # Build mapping: original_id -> (new_id, original_name)
        original_to_new: Dict[int, Tuple[int, str]] = {}
        for banner_info in duplicated_banners:
            orig_id = banner_info.get("original_id")
            new_id = banner_info.get("new_id")
            orig_name = banner_info.get("name") or ""
            if orig_id and new_id:
                original_to_new[orig_id] = (new_id, orig_name)

        # Determine which banners to activate/block/delete and rename
        banners_to_activate: List[int] = []
        banners_to_keep_blocked: List[int] = []
        banners_to_delete: List[int] = []
        # Rename mapping: new_id -> new_name with prefix
        banners_to_rename: Dict[int, str] = {}

        logger.info(f"    Processing {len(original_to_new)} banners for classification")
        logger.info(f"    Positive banner IDs in this group: {len([oid for oid in original_to_new.keys() if oid in positive_banner_ids])}")
        logger.info(f"    Negative banner IDs in this group: {len([oid for oid in original_to_new.keys() if oid in negative_banner_ids])}")

        for orig_id, (new_id, orig_name) in original_to_new.items():
            # Use banner ID as fallback if name is empty
            display_name = orig_name if orig_name else f"Banner_{orig_id}"

            if orig_id in positive_banner_ids:
                # Positive banner - add "Позитив" prefix
                new_name = f"Позитив {display_name}"
                banners_to_rename[new_id] = new_name
                logger.debug(f"      Banner {orig_id} -> {new_id}: POSITIVE, rename to '{new_name}'")
                if self.engine_config.activate_positive_banners:
                    banners_to_activate.append(new_id)
                else:
                    banners_to_keep_blocked.append(new_id)
            elif orig_id in negative_banner_ids:
                # Negative banner
                if not self.engine_config.duplicate_negative_banners:
                    # Should not duplicate negative banners - delete them
                    banners_to_delete.append(new_id)
                    logger.debug(f"      Banner {orig_id} -> {new_id}: NEGATIVE, will be deleted")
                else:
                    # Add "Негатив" prefix
                    new_name = f"Негатив {display_name}"
                    banners_to_rename[new_id] = new_name
                    logger.debug(f"      Banner {orig_id} -> {new_id}: NEGATIVE, rename to '{new_name}'")
                    if self.engine_config.activate_negative_banners:
                        banners_to_activate.append(new_id)
                    else:
                        banners_to_keep_blocked.append(new_id)
            else:
                # Banner not in classification - might be new or missed
                logger.warning(f"      Banner {orig_id} -> {new_id}: NOT CLASSIFIED (not in positive or negative set)")

        # Delete negative banners if needed
        if banners_to_delete:
            logger.info(f"    Deleting {len(banners_to_delete)} negative banners")
            for banner_id in banners_to_delete:
                try:
                    self._delete_banner(account.api_token, banner_id)
                except Exception as e:
                    logger.warning(f"    Failed to delete banner {banner_id}: {e}")

        # Rename banners with prefix (Позитив/Негатив)
        if banners_to_rename:
            logger.info(f"    Renaming {len(banners_to_rename)} banners with classification prefix")
            renamed_count = 0
            for banner_id, new_name in banners_to_rename.items():
                try:
                    self._rename_banner(account.api_token, banner_id, new_name)
                    renamed_count += 1
                    logger.info(f"      ✓ Banner {banner_id} renamed to: '{new_name}'")
                except Exception as e:
                    logger.warning(f"      ✗ Failed to rename banner {banner_id} to '{new_name}': {e}")
            logger.info(f"    Renamed {renamed_count}/{len(banners_to_rename)} banners")
        else:
            logger.warning(f"    No banners to rename! Check classification logic.")

        # Activate banners if needed
        if banners_to_activate:
            logger.info(f"    Activating {len(banners_to_activate)} banners")
            for banner_id in banners_to_activate:
                try:
                    self._activate_banner(account.api_token, banner_id)
                except Exception as e:
                    logger.warning(f"    Failed to activate banner {banner_id}: {e}")

        # Activate group if any banners should be active
        should_activate_group = len(banners_to_activate) > 0

        if should_activate_group:
            logger.info(f"    Activating group {new_group_id}")
            try:
                from utils.vk_api.ad_groups import update_ad_group
                update_ad_group(account.api_token, VK_API_BASE_URL, new_group_id, {"status": "active"})
            except Exception as e:
                logger.warning(f"    Failed to activate group {new_group_id}: {e}")

        # Update result with classification info
        result["positive_count"] = len([orig_id for orig_id in original_to_new.keys() if orig_id in positive_banner_ids])
        result["negative_count"] = len([orig_id for orig_id in original_to_new.keys() if orig_id in negative_banner_ids])
        result["deleted_negative"] = len(banners_to_delete)
        result["activated_banners"] = len(banners_to_activate)
        result["renamed_banners"] = len(banners_to_rename)

        return result

    def _activate_banner(self, token: str, banner_id: int):
        """Activate a banner"""
        import requests
        from utils.vk_api.core import _headers
        url = f"{VK_API_BASE_URL}/banners/{banner_id}.json"
        response = requests.post(url, headers=_headers(token), json={"status": "active"}, timeout=20)
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Failed to activate banner: {response.text[:200]}")

    def _rename_banner(self, token: str, banner_id: int, new_name: str):
        """Rename a banner"""
        import requests
        from utils.vk_api.core import _headers
        url = f"{VK_API_BASE_URL}/banners/{banner_id}.json"
        response = requests.post(url, headers=_headers(token), json={"name": new_name}, timeout=20)
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Failed to rename banner: {response.text[:200]}")

    def _delete_banner(self, token: str, banner_id: int):
        """Delete a banner"""
        import requests
        from utils.vk_api.core import _headers
        url = f"{VK_API_BASE_URL}/banners/{banner_id}.json"
        response = requests.delete(url, headers=_headers(token), timeout=20)
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Failed to delete banner: {response.text[:200]}")

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
                ]
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
        banner_sub_fields = lt_config.banner_sub_fields or ["sub4"]
        if isinstance(banner_sub_fields, str):
            import json
            try:
                banner_sub_fields = json.loads(banner_sub_fields)
            except (json.JSONDecodeError, TypeError):
                banner_sub_fields = [banner_sub_fields]

        logger.info(f"LeadsTech config loaded: base_url={lt_config.base_url}, sub_fields={banner_sub_fields}")

        # Create LeadsTech client
        lt_client = LeadstechClient(LeadstechClientConfig(
            base_url=lt_config.base_url or "https://api.leads.tech",
            login=lt_config.login,
            password=lt_config.password,
            banner_sub_fields=banner_sub_fields
        ))

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
                progress_callback=progress_callback
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
