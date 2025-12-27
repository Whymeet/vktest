"""
VK Ads API - Campaign operations
"""
import requests
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers, _request_with_retries

logger = get_logger(service="vk_api")


def get_campaign_full(token: str, base_url: str, campaign_id: int):
    """Get full campaign data"""
    url = f"{base_url}/ad_plans/{campaign_id}.json"

    try:
        response = _request_with_retries("GET", url, headers=_headers(token), timeout=20)

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error loading campaign {campaign_id}: {error_msg}")
            return None

        return response.json()

    except requests.RequestException as e:
        logger.error(f"[ERROR] Network error loading campaign {campaign_id}: {e}")
        return None


def toggle_campaign_status(token: str, base_url: str, campaign_id: int, status: str):
    """
    Change campaign status

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        campaign_id: Campaign ID
        status: New status ("active" or "blocked")

    Returns:
        dict: {"success": bool, "response": dict or "error": str}
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Invalid status '{status}'. Valid values: 'active', 'blocked'"
        logger.error(f"[ERROR] {error_msg}")
        return {"success": False, "error": error_msg}

    url = f"{base_url}/ad_plans/{campaign_id}.json"
    data = {"status": status}

    try:
        action = "enabling" if status == "active" else "blocking"
        logger.info(f"[ACTION] {action.capitalize()} campaign {campaign_id} (-> {status})")

        response = requests.post(url, headers=_headers(token), json=data, timeout=20)

        if response.status_code in (200, 204):
            logger.info(f"[OK] Campaign {campaign_id} successfully changed to '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error changing campaign {campaign_id} status: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error changing campaign {campaign_id} status: {error_msg}")
        return {"success": False, "error": error_msg}
