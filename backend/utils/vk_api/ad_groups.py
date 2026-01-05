"""
VK Ads API - Ad Group operations
"""
import requests
import time
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers, _request_with_retries

logger = get_logger(service="vk_api")


def get_ad_groups_active(token: str, base_url: str, fields: str = "id,name,status", limit: int = 200):
    """Load all active ad groups"""
    url = f"{base_url}/ad_groups.json"
    offset = 0
    items_all = []

    while True:
        params = {
            "fields": fields,
            "limit": limit,
            "offset": offset,
            "_status": "active"
        }

        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=20)
            if r.status_code != 200:
                error_text = r.text[:200]
                logger.error(f"[ERROR] HTTP {r.status_code} loading ad groups: {error_text}")
                raise RuntimeError(f"[ad_groups] HTTP {r.status_code}: {r.text}")

            payload = r.json()
            items = payload.get("items", [])
            items_all.extend(items)

            if len(items) < limit:
                break

            offset += limit
            time.sleep(0.25)

        except requests.RequestException as e:
            logger.error(f"[ERROR] Network error loading ad groups: {e}")
            raise

    return items_all


def get_ad_groups_all(token: str, base_url: str, fields: str = "id,name,status", limit: int = 200, include_deleted: bool = False):
    """
    Load all ad groups - active and blocked.
    By default does NOT include deleted groups.

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        fields: Fields to load
        limit: Limit per request
        include_deleted: Include deleted groups (default False)

    Returns:
        list: List of all groups (active + blocked)
    """
    url = f"{base_url}/ad_groups.json"
    offset = 0
    items_all = []

    # Get active and blocked groups separately
    statuses = ["active", "blocked"]
    if include_deleted:
        statuses.append("deleted")

    for status in statuses:
        offset = 0
        while True:
            params = {
                "fields": fields,
                "limit": limit,
                "offset": offset,
                "_status": status
            }

            try:
                r = requests.get(url, headers=_headers(token), params=params, timeout=20)
                if r.status_code != 200:
                    error_text = r.text[:200]
                    logger.error(f"[ERROR] HTTP {r.status_code} loading ad groups (status={status}): {error_text}")
                    raise RuntimeError(f"[ad_groups] HTTP {r.status_code}: {r.text}")

                payload = r.json()
                items = payload.get("items", [])
                items_all.extend(items)

                logger.debug(f"   Loaded {len(items)} groups with status '{status}' (offset={offset})")

                if len(items) < limit:
                    break

                offset += limit
                time.sleep(0.25)

            except requests.RequestException as e:
                logger.error(f"[ERROR] Network error loading ad groups (status={status}): {e}")
                raise

    logger.info(f"[INFO] Total loaded {len(items_all)} groups (active + blocked)")
    return items_all


def get_ad_group_full(token: str, base_url: str, group_id: int):
    """Get full ad group data with all fields"""
    url = f"{base_url}/ad_groups/{group_id}.json"

    # Request all important fields (only API-allowed, without read-only fields)
    params = {
        "fields": "id,name,package_id,ad_plan_id,objective,status,age_restrictions,targetings,budget_limit,budget_limit_day,autobidding_mode,pricelist_id,date_start,date_end,utm,enable_utm,enable_recombination,enable_offline_goals,price,max_price"
    }

    try:
        response = _request_with_retries("GET", url, headers=_headers(token), params=params, timeout=20)

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error loading ad group {group_id}: {error_msg}")
            return None

        return response.json()

    except requests.RequestException as e:
        logger.error(f"[ERROR] Network error loading ad group {group_id}: {e}")
        return None


def disable_ad_group(token: str, base_url: str, group_id: int, dry_run: bool = False):
    """Disable an ad group"""
    if dry_run:
        logger.info(f"[DRY RUN] Ad group {group_id} would be disabled (active -> blocked)")
        return {"success": True, "dry_run": True}

    url = f"{base_url}/ad_groups/{group_id}.json"
    data = {"status": "blocked"}

    try:
        logger.info(f"[ACTION] Disabling ad group {group_id} (active -> blocked)")
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)

        if response.status_code in (200, 204):
            logger.info(f"[OK] Ad group {group_id} successfully disabled (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as e:
                logger.debug(f"Could not parse JSON response for ad group {group_id}: {e}")
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error disabling ad group {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error disabling ad group {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}


def toggle_ad_group_status(token: str, base_url: str, group_id: int, status: str):
    """
    Change ad group status

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        group_id: Ad group ID
        status: New status ("active" or "blocked")

    Returns:
        dict: {"success": bool, "response": dict or "error": str}
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Invalid status '{status}'. Valid values: 'active', 'blocked'"
        logger.error(f"[ERROR] {error_msg}")
        return {"success": False, "error": error_msg}

    url = f"{base_url}/ad_groups/{group_id}.json"
    data = {"status": status}

    try:
        action = "enabling" if status == "active" else "blocking"
        logger.info(f"[ACTION] {action.capitalize()} ad group {group_id} (-> {status})")

        response = requests.post(url, headers=_headers(token), json=data, timeout=20)

        if response.status_code in (200, 204):
            logger.info(f"[OK] Ad group {group_id} successfully changed to '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as e:
                logger.debug(f"Could not parse JSON response for ad group {group_id}: {e}")
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error changing ad group {group_id} status: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error changing ad group {group_id} status: {error_msg}")
        return {"success": False, "error": error_msg}


def create_ad_group(token: str, base_url: str, group_data: dict):
    """Create a new ad group"""
    url = f"{base_url}/ad_groups.json"

    # Log the data being sent for debugging
    logger.debug(f"[DEBUG] Creating ad group with data keys: {list(group_data.keys())}")
    if 'budget_limit_day' in group_data:
        logger.debug(f"[DEBUG] budget_limit_day value: {group_data['budget_limit_day']} (type: {type(group_data['budget_limit_day'])})")

    try:
        response = requests.post(url, headers=_headers(token), json=group_data, timeout=30)

        if response.status_code in (200, 201):
            result = response.json()
            logger.info(f"[OK] Ad group created: ID={result.get('id')}")
            return {"success": True, "data": result}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error creating ad group: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error creating ad group: {error_msg}")
        return {"success": False, "error": error_msg}


def update_ad_group(token: str, base_url: str, group_id: int, update_data: dict):
    """Update an ad group"""
    url = f"{base_url}/ad_groups/{group_id}.json"

    try:
        response = requests.post(url, headers=_headers(token), json=update_data, timeout=20)

        if response.status_code in (200, 204):
            try:
                result = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as e:
                logger.debug(f"Could not parse JSON response for ad group {group_id}: {e}")
                result = {}
            logger.info(f"[OK] Ad group {group_id} updated")
            return {"success": True, "data": result}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error updating ad group {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error updating ad group {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}
