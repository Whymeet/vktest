"""
LeadsTech ROI Enricher

Enriches ad group statistics with ROI data from LeadsTech.
Used by auto-scaling to support ROI-based conditions.
"""

from typing import Dict, List, Optional, Any
from utils.logging_setup import get_logger
from utils.vk_api.banners import get_banners_active

logger = get_logger(service="leadstech", function="roi_enricher")


def get_all_banners(token: str, base_url: str, fields: str = "id,ad_group_id", limit: int = 200) -> List[Dict[str, Any]]:
    """
    Load banners with status 'active' or 'blocked' for ROI mapping.

    Excludes deleted banners. Makes two separate API calls since VK API
    doesn't support OR filters or negation.
    """
    from utils.vk_api.core import _headers, _request_with_retries

    url = f"{base_url}/banners.json"
    items_all = []

    # Load banners for each status: active and blocked
    for status in ["active", "blocked"]:
        offset = 0
        while True:
            params = {
                "fields": fields,
                "limit": limit,
                "offset": offset,
                "_status": status,
            }
            try:
                r = _request_with_retries("GET", url, headers=_headers(token), params=params, timeout=30)
                if r.status_code != 200:
                    logger.error(f"HTTP {r.status_code} loading {status} banners: {r.text[:200]}")
                    break
                payload = r.json()
                items = payload.get("items", [])
                items_all.extend(items)
                if len(items) < limit:
                    break
                offset += limit
            except Exception as e:
                logger.error(f"Error loading {status} banners after retries: {e}")
                break

    logger.info(f"Loaded {len(items_all)} banners (active + blocked)")
    return items_all


def get_banners_by_ad_group(
    token: str,
    base_url: str
) -> Dict[int, List[int]]:
    """
    Load ALL banners and group them by ad_group_id.

    Uses get_all_banners (no status filter) to include archived banners
    that may have LeadsTech data.

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL

    Returns:
        Dict mapping ad_group_id to list of banner_ids
    """
    try:
        logger.info(f"🔍 Загрузка ВСЕХ баннеров для маппинга ad_group -> banners...")
        banners = get_all_banners(
            token=token,
            base_url=base_url,
            fields="id,ad_group_id",
            limit=200
        )

        result: Dict[int, List[int]] = {}
        skipped = 0
        for banner in banners:
            ad_group_id = banner.get("ad_group_id")
            banner_id = banner.get("id")

            if ad_group_id is None or banner_id is None:
                skipped += 1
                continue

            try:
                gid = int(ad_group_id)
                bid = int(banner_id)
            except (TypeError, ValueError):
                skipped += 1
                continue

            if gid not in result:
                result[gid] = []
            result[gid].append(bid)

        logger.info(f"✅ Загружено {len(banners)} баннеров → {len(result)} групп (пропущено: {skipped})")

        # Логируем первые 5 групп для отладки
        for i, (gid, bids) in enumerate(list(result.items())[:5]):
            logger.debug(f"   Группа {gid}: {len(bids)} баннеров → {bids[:3]}{'...' if len(bids) > 3 else ''}")

        return result

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки баннеров: {e}")
        return {}


def calculate_group_roi(
    banner_ids: List[int],
    lt_data: Dict[int, Dict[str, Any]],
    group_name: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Calculate aggregated ROI for a group from its banner data.

    Sums revenue and spent for all banners, then calculates ROI:
    ROI = (total_revenue - total_spent) / total_spent * 100

    Args:
        banner_ids: List of banner IDs in the group
        lt_data: Dict mapping banner_id to {lt_revenue, vk_spent, profit, roi_percent}
        group_name: Group name for logging

    Returns:
        Dict with {roi, lt_revenue, vk_spent, profit} or None if no data
    """
    total_revenue = 0.0
    total_spent = 0.0
    banners_found = 0
    banners_missing = []

    for bid in banner_ids:
        if bid in lt_data:
            data = lt_data[bid]
            total_revenue += data.get("lt_revenue", 0.0)
            total_spent += data.get("vk_spent", 0.0)
            banners_found += 1
        else:
            banners_missing.append(bid)

    if banners_found == 0:
        logger.debug(f"   ⚠️ Группа '{group_name}': нет LeadsTech данных для баннеров {banner_ids[:5]}{'...' if len(banner_ids) > 5 else ''}")
        return None

    profit = total_revenue - total_spent
    roi = None
    if total_spent > 0:
        roi = (profit / total_spent) * 100.0

    logger.debug(f"   📊 Группа '{group_name}': {banners_found}/{len(banner_ids)} баннеров с данными, "
                 f"revenue={total_revenue:.2f}, spent={total_spent:.2f}, ROI={roi:.1f}%" if roi else f"ROI=N/A")

    return {
        "roi": roi,
        "lt_revenue": total_revenue,
        "vk_spent": total_spent,
        "profit": profit,
        "banners_with_data": banners_found,
    }


def enrich_groups_with_roi(
    groups: List[Dict[str, Any]],
    lt_data: Dict[int, Dict[str, Any]],
    banners_by_group: Dict[int, List[int]]
) -> List[Dict[str, Any]]:
    """
    Add ROI metrics to group stats.

    For each group, finds its banners, looks up LeadsTech data,
    calculates aggregated ROI, and adds it to stats.

    Args:
        groups: List of ad groups with 'id' and 'stats' keys
        lt_data: Dict mapping banner_id to LeadsTech metrics
        banners_by_group: Dict mapping ad_group_id to list of banner_ids

    Returns:
        Same groups list with stats enriched with ROI data
    """
    logger.info(f"🔄 Обогащение {len(groups)} групп данными ROI из LeadsTech...")
    logger.info(f"   LeadsTech данные: {len(lt_data)} баннеров")
    logger.info(f"   Маппинг групп: {len(banners_by_group)} групп с баннерами")

    # Логируем примеры ID для диагностики несовпадения
    if lt_data:
        lt_sample_ids = list(lt_data.keys())[:5]
        logger.info(f"   LeadsTech banner IDs (sample): {lt_sample_ids}")
    if banners_by_group:
        all_banner_ids = []
        for bids in list(banners_by_group.values())[:3]:
            all_banner_ids.extend(bids[:2])
        logger.info(f"   VK API banner IDs (sample): {all_banner_ids[:10]}")

    enriched_count = 0
    no_banners_count = 0
    no_roi_data_count = 0

    for group in groups:
        group_id = group.get("id")
        group_name = group.get("name", "Unknown")
        if group_id is None:
            continue

        try:
            gid = int(group_id)
        except (TypeError, ValueError):
            continue

        # Get banner IDs for this group
        banner_ids = banners_by_group.get(gid, [])
        if not banner_ids:
            no_banners_count += 1
            logger.debug(f"   ⚠️ Группа '{group_name}' (ID:{gid}): нет баннеров в маппинге")
            continue

        # Calculate ROI from LeadsTech data
        roi_data = calculate_group_roi(banner_ids, lt_data, group_name)
        if roi_data is None:
            no_roi_data_count += 1
            continue

        # Add to stats
        if "stats" not in group:
            group["stats"] = {}

        stats = group["stats"]
        stats["roi"] = roi_data["roi"]
        stats["lt_revenue"] = roi_data["lt_revenue"]
        stats["lt_spent"] = roi_data["vk_spent"]
        stats["lt_profit"] = roi_data["profit"]

        enriched_count += 1
        logger.info(f"   ✅ '{group_name}': ROI={roi_data['roi']:.1f}% (revenue={roi_data['lt_revenue']:.0f}₽, spent={roi_data['vk_spent']:.0f}₽)")

    logger.info(f"📊 Итого обогащено: {enriched_count}/{len(groups)} групп")
    if no_banners_count > 0:
        logger.warning(f"   ⚠️ {no_banners_count} групп без баннеров в маппинге")
    if no_roi_data_count > 0:
        logger.warning(f"   ⚠️ {no_roi_data_count} групп без LeadsTech данных")

    return groups
