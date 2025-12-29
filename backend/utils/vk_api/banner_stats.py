"""
VK Ads API - Banner Statistics with Batching
Optimized for processing 10,000-15,000 banners efficiently
"""
import time
from typing import Dict, List, Generator, Tuple, Set, Optional
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers, _request_with_retries, API_RETRY_DELAY_SCALING

import requests

logger = get_logger(service="vk_api_banner_stats")

# Constants for batching
BANNER_LIST_BATCH_SIZE = 200      # Max banners per list request
BANNER_STATS_BATCH_SIZE = 150     # Max banners per stats request (to avoid URL too long)
REQUEST_DELAY_SECONDS = 0.1       # Delay between requests to avoid rate limit


def get_banners_paginated(
    token: str,
    base_url: str,
    batch_size: int = BANNER_LIST_BATCH_SIZE,
    fields: str = "id,name,status,ad_group_id",
    include_blocked: bool = True,
    sleep_between_calls: float = REQUEST_DELAY_SECONDS
) -> Generator[List[dict], None, None]:
    """
    Generator that yields batches of banners (active + optionally blocked).
    Memory efficient - doesn't load all banners at once.

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        batch_size: Number of banners per batch
        fields: Fields to request
        include_blocked: Include blocked banners (default True)
        sleep_between_calls: Delay between API calls

    Yields:
        List of banner dicts (batch_size items per yield)
    """
    url = f"{base_url}/banners.json"

    statuses = ["active"]
    if include_blocked:
        statuses.append("blocked")

    for status in statuses:
        offset = 0
        page_num = 1

        while True:
            params = {
                "fields": fields,
                "limit": batch_size,
                "offset": offset,
                "_status": status,
            }

            try:
                response = _request_with_retries(
                    "GET", url,
                    headers=_headers(token),
                    params=params,
                    timeout=30,
                    retry_delay=API_RETRY_DELAY_SCALING  # Быстрые ретраи для scaling
                )

                if response.status_code != 200:
                    logger.error(f"[ERROR] HTTP {response.status_code} loading banners (status={status}): {response.text[:200]}")
                    break

                payload = response.json()
                items = payload.get("items", [])

                if items:
                    logger.debug(f"[INFO] Loaded {len(items)} banners (status={status}, page={page_num})")
                    yield items

                if len(items) < batch_size:
                    break

                offset += batch_size
                page_num += 1
                time.sleep(sleep_between_calls)

            except requests.RequestException as e:
                logger.error(f"[ERROR] Network error loading banners: {e}")
                break


def get_all_banners_with_groups(
    token: str,
    base_url: str,
    include_blocked: bool = True
) -> Tuple[List[dict], Dict[int, int]]:
    """
    Load all banners and build banner_id -> group_id mapping.

    Returns:
        Tuple of (banners_list, banner_to_group_dict)
    """
    all_banners = []
    banner_to_group: Dict[int, int] = {}

    for batch in get_banners_paginated(token, base_url, include_blocked=include_blocked):
        for banner in batch:
            banner_id = banner.get("id")
            group_id = banner.get("ad_group_id")
            if banner_id and group_id:
                all_banners.append(banner)
                banner_to_group[banner_id] = group_id

    logger.info(f"[INFO] Loaded {len(all_banners)} banners total, {len(set(banner_to_group.values()))} unique groups")
    return all_banners, banner_to_group


def get_banners_stats_batch(
    token: str,
    base_url: str,
    banner_ids: List[int],
    date_from: str,
    date_to: str,
    metrics: str = "base"
) -> Dict[int, dict]:
    """
    Get statistics for a batch of banners.
    Handles URL length limits automatically.

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        banner_ids: List of banner IDs to get stats for
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        metrics: Metrics type (default "base")

    Returns:
        Dict mapping banner_id to stats dict
    """
    if not banner_ids:
        return {}

    stats_url = f"{base_url}/statistics/banners/day.json"
    stats_by_banner: Dict[int, dict] = {}

    # Split into smaller batches if needed
    for i in range(0, len(banner_ids), BANNER_STATS_BATCH_SIZE):
        batch_ids = banner_ids[i:i + BANNER_STATS_BATCH_SIZE]

        params = {
            "date_from": date_from,
            "date_to": date_to,
            "metrics": metrics,
            "id": ",".join(map(str, batch_ids))
        }

        try:
            response = _request_with_retries(
                "GET", stats_url,
                headers=_headers(token),
                params=params,
                timeout=30,
                retry_delay=API_RETRY_DELAY_SCALING  # Быстрые ретраи для scaling
            )

            if response.status_code == 414:
                # URL too long - use smaller batches
                logger.warning(f"[WARN] URL too long for {len(batch_ids)} banners, trying smaller batch")
                for sub_i in range(0, len(batch_ids), 50):
                    sub_batch = batch_ids[sub_i:sub_i + 50]
                    params["id"] = ",".join(map(str, sub_batch))
                    sub_response = _request_with_retries(
                        "GET", stats_url,
                        headers=_headers(token),
                        params=params,
                        timeout=30,
                        retry_delay=API_RETRY_DELAY_SCALING  # Быстрые ретраи для scaling
                    )
                    if sub_response.status_code == 200:
                        _parse_stats_response(sub_response.json(), stats_by_banner)
                continue

            if response.status_code != 200:
                logger.error(f"[ERROR] HTTP {response.status_code} getting banner stats: {response.text[:200]}")
                continue

            _parse_stats_response(response.json(), stats_by_banner)

            # Small delay between batches
            if i + BANNER_STATS_BATCH_SIZE < len(banner_ids):
                time.sleep(REQUEST_DELAY_SECONDS)

        except requests.RequestException as e:
            logger.error(f"[ERROR] Network error getting banner stats: {e}")

    return stats_by_banner


def _parse_stats_response(payload: dict, stats_by_banner: Dict[int, dict]) -> None:
    """
    Parse VK API statistics response and update stats_by_banner dict.

    Extracts: spent, shows (impressions), clicks, goals (vk.goals), cr (vk.cr)
    """
    items = payload.get("items", [])

    for item in items:
        banner_id = item.get("id")
        if banner_id is None:
            continue

        # Get total.base - aggregated data for the whole period
        total = item.get("total", {})
        base = total.get("base", {}) if isinstance(total, dict) else {}

        # VK metrics are in total.base.vk
        vk_data = base.get("vk", {}) if isinstance(base.get("vk"), dict) else {}
        vk_goals = float(vk_data.get("goals", 0) or 0)
        vk_cr = float(vk_data.get("cr", 0) or 0)  # CR from VK API (goals/clicks * 100)

        # Main metrics
        spent = float(base.get("spent", 0) or 0)
        shows = float(base.get("impressions", 0) or 0)
        clicks = float(base.get("clicks", 0) or 0)

        # If total.base is empty, try to aggregate from rows
        if spent == 0 and shows == 0 and clicks == 0:
            rows = item.get("rows", [])
            total_vk_goals = 0
            for row in rows:
                row_base = row.get("base", {}) if isinstance(row.get("base"), dict) else row
                spent += float(row_base.get("spent", 0) or 0)
                shows += float(row_base.get("impressions", row_base.get("shows", 0)) or 0)
                clicks += float(row_base.get("clicks", 0) or 0)
                row_vk = row_base.get("vk", {}) if isinstance(row_base.get("vk"), dict) else {}
                total_vk_goals += float(row_vk.get("goals", 0) or 0)
            vk_goals = total_vk_goals
            # Recalculate CR from aggregated data
            vk_cr = (vk_goals / clicks * 100) if clicks > 0 else 0.0

        stats_by_banner[banner_id] = {
            "spent": spent,
            "shows": shows,
            "clicks": clicks,
            "goals": vk_goals,
            "vk_cr": vk_cr  # Store VK's CR value
        }


def calculate_derived_metrics(stats: dict) -> dict:
    """
    Calculate derived metrics from base stats.

    Args:
        stats: Dict with spent, shows, clicks, goals, vk_cr

    Returns:
        Dict with original stats + cost_per_goal, ctr, cpc, cr
    """
    spent = float(stats.get("spent", 0) or 0)
    shows = float(stats.get("shows", 0) or 0)
    clicks = float(stats.get("clicks", 0) or 0)
    goals = float(stats.get("goals", 0) or 0)

    # Calculate derived metrics
    cost_per_goal = spent / goals if goals > 0 else float('inf')
    ctr = (clicks / shows * 100) if shows > 0 else 0.0
    cpc = spent / clicks if clicks > 0 else float('inf')

    # Use VK's CR if available, otherwise calculate
    vk_cr = stats.get("vk_cr")
    if vk_cr is not None and vk_cr > 0:
        cr = float(vk_cr)
    else:
        cr = (goals / clicks * 100) if clicks > 0 else 0.0

    return {
        "spent": spent,
        "shows": shows,
        "clicks": clicks,
        "goals": goals,
        "cost_per_goal": cost_per_goal,
        "ctr": ctr,
        "cpc": cpc,
        "cr": cr
    }


def classify_banners_streaming(
    token: str,
    base_url: str,
    date_from: str,
    date_to: str,
    check_conditions_fn,
    include_blocked: bool = True,
    batch_size: int = BANNER_LIST_BATCH_SIZE,  # Max 250 per VK API
    progress_callback=None,
    cancel_check_fn=None
) -> Tuple[Set[int], Set[int], Dict[int, int]]:
    """
    Streaming banner classification - memory efficient.
    Loads banners in batches, classifies them, and stores only IDs.

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        date_from: Start date for statistics
        date_to: End date for statistics
        check_conditions_fn: Function(stats_dict) -> bool to check if banner is positive
        include_blocked: Include blocked banners
        batch_size: Batch size for loading
        progress_callback: Optional callback(processed, total) for progress updates
        cancel_check_fn: Optional function() -> bool to check if task was cancelled

    Returns:
        Tuple of (positive_ids, negative_ids, banner_to_group)
        - positive_ids: Set of banner IDs that match all conditions
        - negative_ids: Set of banner IDs that don't match conditions
        - banner_to_group: Dict mapping banner_id to group_id
    """
    positive_ids: Set[int] = set()
    negative_ids: Set[int] = set()
    banner_to_group: Dict[int, int] = {}

    total_processed = 0
    batch_buffer: List[dict] = []

    logger.info(f"[INFO] Starting streaming banner classification for period {date_from} - {date_to}")

    cancelled = False

    # Iterate through banner batches
    for batch in get_banners_paginated(token, base_url, batch_size=batch_size, include_blocked=include_blocked):
        # Check for cancellation
        if cancel_check_fn and cancel_check_fn():
            logger.warning("[WARN] Classification cancelled by user")
            cancelled = True
            break

        # Accumulate banners
        for banner in batch:
            banner_id = banner.get("id")
            group_id = banner.get("ad_group_id")
            if banner_id and group_id:
                batch_buffer.append(banner)
                banner_to_group[banner_id] = group_id

        # When buffer is full, get stats and classify
        if len(batch_buffer) >= batch_size:
            _process_banner_batch(
                token, base_url, batch_buffer, date_from, date_to,
                check_conditions_fn, positive_ids, negative_ids
            )
            total_processed += len(batch_buffer)

            if progress_callback:
                progress_callback(total_processed, None)

            logger.info(f"[INFO] Processed {total_processed} banners, positive: {len(positive_ids)}, negative: {len(negative_ids)}")
            batch_buffer = []

    # Process remaining banners (only if not cancelled)
    if batch_buffer and not cancelled:
        _process_banner_batch(
            token, base_url, batch_buffer, date_from, date_to,
            check_conditions_fn, positive_ids, negative_ids
        )
        total_processed += len(batch_buffer)

        if progress_callback:
            progress_callback(total_processed, total_processed)

    logger.info(f"[INFO] Classification complete: {total_processed} banners, "
                f"positive: {len(positive_ids)}, negative: {len(negative_ids)}, "
                f"groups: {len(set(banner_to_group.values()))}")

    return positive_ids, negative_ids, banner_to_group


def _process_banner_batch(
    token: str,
    base_url: str,
    banners: List[dict],
    date_from: str,
    date_to: str,
    check_conditions_fn,
    positive_ids: Set[int],
    negative_ids: Set[int]
) -> None:
    """
    Process a batch of banners: get stats and classify.
    Updates positive_ids and negative_ids in place.
    """
    banner_ids = [b["id"] for b in banners]

    # Get statistics for batch
    stats_map = get_banners_stats_batch(token, base_url, banner_ids, date_from, date_to)

    # Classify each banner
    for banner in banners:
        banner_id = banner["id"]
        raw_stats = stats_map.get(banner_id, {})

        # Calculate derived metrics
        stats = calculate_derived_metrics(raw_stats)

        # Check conditions
        if check_conditions_fn(stats):
            positive_ids.add(banner_id)
        else:
            negative_ids.add(banner_id)


def get_groups_with_positive_banners(
    positive_ids: Set[int],
    banner_to_group: Dict[int, int]
) -> Set[int]:
    """
    Get set of group IDs that contain at least one positive banner.

    Args:
        positive_ids: Set of positive banner IDs
        banner_to_group: Dict mapping banner_id to group_id

    Returns:
        Set of group IDs to duplicate
    """
    groups_to_duplicate: Set[int] = set()

    for banner_id in positive_ids:
        group_id = banner_to_group.get(banner_id)
        if group_id:
            groups_to_duplicate.add(group_id)

    return groups_to_duplicate


def get_group_banner_classification(
    group_id: int,
    positive_ids: Set[int],
    negative_ids: Set[int],
    banner_to_group: Dict[int, int]
) -> Tuple[List[int], List[int]]:
    """
    Get positive and negative banner IDs for a specific group.

    Args:
        group_id: Group ID to get banners for
        positive_ids: Set of all positive banner IDs
        negative_ids: Set of all negative banner IDs
        banner_to_group: Dict mapping banner_id to group_id

    Returns:
        Tuple of (positive_banner_ids, negative_banner_ids) for this group
    """
    group_positive: List[int] = []
    group_negative: List[int] = []

    for banner_id, gid in banner_to_group.items():
        if gid == group_id:
            if banner_id in positive_ids:
                group_positive.append(banner_id)
            elif banner_id in negative_ids:
                group_negative.append(banner_id)

    return group_positive, group_negative
