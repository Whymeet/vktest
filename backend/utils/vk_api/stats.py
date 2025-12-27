"""
VK Ads API - Statistics operations
"""
import requests
import time
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers
from utils.vk_api.ad_groups import get_ad_groups_active, get_ad_groups_all

logger = get_logger(service="vk_api")


def get_ad_groups_with_stats(token: str, base_url: str, date_from: str, date_to: str, limit: int = 200, include_blocked: bool = True):
    """
    Get ad groups with statistics for period

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        limit: Limit per request
        include_blocked: Include blocked groups (default True)

    Returns:
        list: List of ad groups with statistics
    """
    # Get groups: active + blocked (except deleted)
    # Use only valid VK API fields (day_limit not supported, use budget_limit_day)
    if include_blocked:
        groups = get_ad_groups_all(token, base_url, fields="id,name,status,budget_limit_day", limit=limit, include_deleted=False)
    else:
        groups = get_ad_groups_active(token, base_url, fields="id,name,status,budget_limit_day", limit=limit)

    if not groups:
        return []

    # Additionally filter deleted groups (in case API returned them)
    groups = [g for g in groups if g.get('status') != 'deleted']

    if not groups:
        return []

    group_ids = [g['id'] for g in groups]

    logger.info(f"[INFO] Getting statistics for {len(group_ids)} groups for period {date_from} - {date_to}")

    # Get group statistics WITH BATCHING
    # To avoid 414 error (Request-URI Too Large) with many groups
    stats_url = f"{base_url}/statistics/ad_groups/day.json"
    STATS_BATCH_SIZE = 100  # Max groups per request

    all_stats_data = []

    try:
        # Split into batches to avoid 414 error
        total_batches = (len(group_ids) + STATS_BATCH_SIZE - 1) // STATS_BATCH_SIZE
        logger.info(f"[INFO] Splitting {len(group_ids)} groups into {total_batches} batches of {STATS_BATCH_SIZE}")

        for batch_num, i in enumerate(range(0, len(group_ids), STATS_BATCH_SIZE), 1):
            batch_ids = group_ids[i:i + STATS_BATCH_SIZE]

            params = {
                "date_from": date_from,
                "date_to": date_to,
                "metrics": "base",
                "id": ",".join(map(str, batch_ids))
            }

            logger.info(f"   [INFO] Batch {batch_num}/{total_batches}: requesting statistics for {len(batch_ids)} groups...")

            response = requests.get(stats_url, headers=_headers(token), params=params, timeout=30)

            if response.status_code == 414:
                # URL too long - try smaller batch
                logger.warning(f"[WARN] Batch {batch_num}: URL too long for {len(batch_ids)} groups, trying 50")
                for sub_i in range(0, len(batch_ids), 50):
                    sub_batch = batch_ids[sub_i:sub_i + 50]
                    params["id"] = ",".join(map(str, sub_batch))
                    sub_response = requests.get(stats_url, headers=_headers(token), params=params, timeout=30)
                    if sub_response.status_code == 200:
                        sub_data = sub_response.json().get("items", [])
                        all_stats_data.extend(sub_data)
                    else:
                        logger.error(f"[ERROR] Error in sub-batch: HTTP {sub_response.status_code}")
                continue

            if response.status_code != 200:
                error_text = response.text[:300]
                logger.error(f"[ERROR] Error getting statistics batch {batch_num}: HTTP {response.status_code}, Response: {error_text}")
                continue

            batch_stats = response.json().get("items", [])
            all_stats_data.extend(batch_stats)
            logger.info(f"   [OK] Batch {batch_num}: received {len(batch_stats)} records")

            # Small pause between batches to avoid rate limit
            if batch_num < total_batches:
                time.sleep(0.1)

        stats_data = all_stats_data
        logger.info(f"[INFO] Total received {len(stats_data)} statistics records from VK API")

        # Log first record for debugging
        if stats_data and len(stats_data) > 0:
            logger.info(f"[DEBUG] First statistics record example: {str(stats_data[0])[:500]}")

        # Aggregate statistics by group
        # Use same logic as for banners in get_banners_stats_day
        stats_by_group = {}
        for item in stats_data:
            gid = item.get("id")
            if gid is None:
                continue

            # Get total.base - aggregated data for the whole period
            total = item.get("total", {})
            base = total.get("base", {}) if isinstance(total, dict) else {}

            # VK goals are in total.base.vk.goals
            vk_data = base.get("vk", {}) if isinstance(base.get("vk"), dict) else {}
            vk_goals = float(vk_data.get("goals", 0) or 0)

            # Additional logging for debugging (only for first group)
            if gid and gid == stats_data[0].get("id") and (base or item.get("rows")):
                logger.info(f"[DEBUG] Detailed data structure for group {gid}:")
                logger.info(f"   total keys: {list(total.keys()) if isinstance(total, dict) else 'not dict'}")
                logger.info(f"   base keys: {list(base.keys()) if isinstance(base, dict) else 'not dict'}")
                logger.info(f"   base content: {base}")
                logger.info(f"   vk_data: {vk_data}")
                logger.info(f"   vk_goals from total.base.vk.goals: {vk_goals}")
                if item.get("rows"):
                    logger.info(f"   rows (first 2): {item.get('rows')[:2]}")

            # Main metrics
            spent = float(base.get("spent", 0) or 0)
            shows = float(base.get("impressions", 0) or 0)  # VK API uses 'impressions'
            clicks = float(base.get("clicks", 0) or 0)

            # If total.base is empty, try to aggregate from rows
            if spent == 0 and shows == 0 and clicks == 0:
                rows = item.get("rows", [])
                for row in rows:
                    row_base = row.get("base", {}) if isinstance(row.get("base"), dict) else row
                    spent += float(row_base.get("spent", 0) or 0)
                    shows += float(row_base.get("impressions", row_base.get("shows", 0)) or 0)
                    clicks += float(row_base.get("clicks", 0) or 0)
                    row_vk = row_base.get("vk", {}) if isinstance(row_base.get("vk"), dict) else {}
                    vk_goals += float(row_vk.get("goals", 0) or 0)

            stats_by_group[gid] = {
                "spent": spent,
                "shows": shows,
                "clicks": clicks,
                "goals": vk_goals
            }

            logger.debug(f"   Group {gid}: spent={spent:.2f}, shows={shows}, clicks={clicks}, goals={vk_goals}")

        # Combine groups with statistics
        for group in groups:
            gid = group["id"]
            if gid in stats_by_group:
                group["stats"] = stats_by_group[gid]

                # Calculate cost per goal
                goals = stats_by_group[gid]["goals"]
                spent = stats_by_group[gid]["spent"]

                if goals > 0:
                    group["stats"]["cost_per_goal"] = spent / goals
                else:
                    group["stats"]["cost_per_goal"] = None

                logger.info(f"   [INFO] Group {gid} ({group.get('name', 'Unknown')}): "
                           f"spent={spent:.2f}rub, goals={goals}, cost_per_goal={group['stats']['cost_per_goal']}")
            else:
                group["stats"] = {
                    "spent": 0,
                    "shows": 0,
                    "clicks": 0,
                    "goals": 0,
                    "cost_per_goal": None
                }
                logger.debug(f"   [INFO] Group {gid}: no statistics")

        return groups

    except requests.RequestException as e:
        logger.error(f"[ERROR] Network error getting statistics: {e}")
        return groups
