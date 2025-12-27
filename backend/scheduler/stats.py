"""
Scheduler stats - VK API statistics fetching
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from utils.vk_api import get_banners_stats_day
from scheduler.config import (
    VK_API_BASE_URL,
    STATS_BATCH_SIZE,
    BATCH_DELAY_SECONDS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_RETRIES,
    RATE_LIMIT_RETRY_MULTIPLIER,
)


def parse_banner_stats(item: Dict) -> Dict:
    """
    Parse banner statistics from VK API response item.

    Args:
        item: Single item from VK API statistics response

    Returns:
        Parsed stats dict with spent, clicks, shows, goals, vk_goals
    """
    total = item.get("total", {}).get("base", {})
    vk_data = total.get("vk", {}) if isinstance(total.get("vk"), dict) else {}
    vk_goals = vk_data.get("goals", 0.0)

    return {
        "spent": float(total.get("spent", 0.0)),
        "clicks": float(total.get("clicks", 0.0)),
        "shows": float(total.get("impressions", 0.0)),
        "goals": float(vk_goals),
        "vk_goals": float(vk_goals)
    }


def get_fresh_stats(
    token: str,
    banner_id: int,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    logger=None
) -> Optional[Dict]:
    """
    Get fresh statistics for a single banner from VK API with retry on rate limit.

    Args:
        token: VK API token
        banner_id: Banner ID
        lookback_days: Number of days for statistics
        max_retries: Maximum retry attempts
        logger: Optional logger

    Returns:
        Stats dict or None on error
    """
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    for attempt in range(max_retries):
        try:
            stats = get_banners_stats_day(
                token=token,
                base_url=VK_API_BASE_URL,
                date_from=date_from,
                date_to=date_to,
                banner_ids=[banner_id],
                metrics="base"
            )

            if stats:
                for item in stats:
                    if item.get("id") == banner_id:
                        return parse_banner_stats(item)

            return {"spent": 0, "clicks": 0, "shows": 0, "goals": 0, "vk_goals": 0}

        except Exception as e:
            error_str = str(e)
            # Check for rate limit (HTTP 429)
            if "429" in error_str or "rate" in error_str.lower():
                wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                if logger:
                    logger.warning(
                        f"Rate limit for banner {banner_id}, waiting {wait_time} sec "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                time.sleep(wait_time)
                continue
            else:
                if logger:
                    logger.error(f"Error getting stats for banner {banner_id}: {e}")
                return None

    if logger:
        logger.error(f"Failed to get stats for banner {banner_id} after {max_retries} attempts")
    return None


def get_fresh_stats_batch(
    token: str,
    banner_ids: List[int],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    batch_size: int = STATS_BATCH_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    should_stop_fn=None,
    logger=None
) -> Dict[int, Optional[Dict]]:
    """
    Get statistics for multiple banners in batches (optimized for VK API 35 req/s limit).

    Args:
        token: VK API token
        banner_ids: List of banner IDs
        lookback_days: Number of days for statistics
        batch_size: Batch size (recommended 100-200)
        max_retries: Maximum retry attempts per batch
        should_stop_fn: Optional callable to check if should stop
        logger: Optional logger

    Returns:
        Dict mapping banner_id to stats dict (or None on error)
    """
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    results: Dict[int, Optional[Dict]] = {}
    total_batches = (len(banner_ids) + batch_size - 1) // batch_size

    for batch_num, i in enumerate(range(0, len(banner_ids), batch_size), 1):
        # Check if should stop
        if should_stop_fn and should_stop_fn():
            break

        batch = banner_ids[i:i + batch_size]

        for attempt in range(max_retries):
            try:
                if logger:
                    logger.debug(
                        f"Batch {batch_num}/{total_batches}: "
                        f"requesting stats for {len(batch)} banners"
                    )

                stats = get_banners_stats_day(
                    token=token,
                    base_url=VK_API_BASE_URL,
                    date_from=date_from,
                    date_to=date_to,
                    banner_ids=batch,
                    metrics="base"
                )

                # Parse results
                for item in stats:
                    banner_id = item.get("id")
                    if banner_id:
                        results[banner_id] = parse_banner_stats(item)

                # Add empty stats for banners without data
                for bid in batch:
                    if bid not in results:
                        results[bid] = {"spent": 0, "clicks": 0, "shows": 0, "goals": 0, "vk_goals": 0}

                break  # Success, exit retry loop

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    wait_time = (attempt + 1) * RATE_LIMIT_RETRY_MULTIPLIER  # 3, 6, 9 seconds
                    if logger:
                        logger.warning(
                            f"Rate limit batch {batch_num}, waiting {wait_time} sec "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                    time.sleep(wait_time)
                    continue
                else:
                    if logger:
                        logger.error(f"Error batch {batch_num}: {e}")
                    # Mark banners as errored (None)
                    for bid in batch:
                        if bid not in results:
                            results[bid] = None
                    break

        # Delay between batches (VK API: 35 req/s, we do ~5 req/s for safety)
        if batch_num < total_batches:
            time.sleep(BATCH_DELAY_SECONDS)

    return results
