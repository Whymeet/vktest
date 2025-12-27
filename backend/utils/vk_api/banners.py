"""
VK Ads API - Banner operations
"""
import requests
import time
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers, _request_with_retries

logger = get_logger(service="vk_api")


def get_banners_active(token: str, base_url: str, fields: str = "id,name,status,delivery,ad_group_id", limit: int = 200, sleep_between_calls: float = 0.25):
    """Load all active banners (ads)"""
    url = f"{base_url}/banners.json"
    offset = 0
    items_all = []
    page_num = 1
    while True:
        params = {
            "fields": fields,
            "limit": limit,
            "offset": offset,
            "_status": "active",
            "_ad_group_status": "active"  # Only banners from active ad groups
        }
        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=20)
            if r.status_code != 200:
                error_text = r.text[:200]
                logger.error(f"[ERROR] HTTP {r.status_code} loading banners: {error_text}")
                raise RuntimeError(f"[banners] HTTP {r.status_code}: {r.text}")
            payload = r.json()
            items = payload.get("items", [])
            items_all.extend(items)
            if len(items) < limit:
                break
            offset += limit
            page_num += 1
            time.sleep(sleep_between_calls)
        except requests.RequestException as e:
            logger.error(f"[ERROR] Network error loading banners: {e}")
            raise
    return items_all


def get_banners_stats_day(token: str, base_url: str, date_from: str, date_to: str, banner_ids: list = None, metrics: str = "base"):
    """Get banner statistics"""
    url = f"{base_url}/statistics/banners/day.json"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metrics,
    }
    if banner_ids:
        params["id"] = ",".join(map(str, banner_ids))
    r = requests.get(url, headers=_headers(token), params=params, timeout=30)
    if r.status_code != 200:
        error_text = r.text[:200]
        logger.error(f"[ERROR] HTTP {r.status_code} getting statistics: {error_text}")
        raise RuntimeError(f"[banners stats] HTTP {r.status_code}: {r.text}")
    payload = r.json()
    return payload.get("items", [])


def get_banner_info(token: str, base_url: str, banner_id: int):
    """
    Get information about a specific banner

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        banner_id: Banner ID

    Returns:
        dict: Banner information or None on error
    """
    url = f"{base_url}/banners/{banner_id}.json"

    try:
        response = _request_with_retries("GET", url, headers=_headers(token), timeout=20)

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"[ERROR] Error getting banner {banner_id} info: HTTP {response.status_code}")
            return None

    except requests.RequestException as e:
        logger.error(f"[ERROR] Network error getting banner {banner_id} info: {e}")
        return None


def disable_banner(token: str, base_url: str, banner_id: int, dry_run: bool = True):
    """Disable a banner (ad)"""
    if dry_run:
        logger.info(f"[DRY RUN] Banner {banner_id} would be disabled (active -> blocked)")
        return {"success": True, "dry_run": True}
    url = f"{base_url}/banners/{banner_id}.json"
    data = {"status": "blocked"}
    try:
        logger.info(f"[ACTION] Disabling banner {banner_id} (active -> blocked)")
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        if response.status_code in (200, 204):
            logger.info(f"[OK] Banner {banner_id} successfully disabled (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error disabling banner {banner_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error disabling banner {banner_id}: {error_msg}")
        return {"success": False, "error": error_msg}


def toggle_banner_status(token: str, base_url: str, banner_id: int, status: str):
    """
    Change banner status

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        banner_id: Banner ID
        status: New status ("active" or "blocked")

    Returns:
        dict: {"success": bool, "response": dict or "error": str}
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Invalid status '{status}'. Valid values: 'active', 'blocked'"
        logger.error(f"[ERROR] {error_msg}")
        return {"success": False, "error": error_msg}

    url = f"{base_url}/banners/{banner_id}.json"
    data = {"status": status}

    try:
        action = "enabling" if status == "active" else "blocking"
        logger.info(f"[ACTION] {action.capitalize()} banner {banner_id} (-> {status})")

        response = requests.post(url, headers=_headers(token), json=data, timeout=20)

        if response.status_code in (200, 204):
            logger.info(f"[OK] Banner {banner_id} successfully changed to '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error changing banner {banner_id} status: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error changing banner {banner_id} status: {error_msg}")
        return {"success": False, "error": error_msg}
