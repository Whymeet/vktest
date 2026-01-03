"""
VK Ads API - Campaign operations
"""
import requests
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers, _request_with_retries

logger = get_logger(service="vk_api")


def get_campaign_full(token: str, base_url: str, campaign_id: int):
    """Get full campaign data including objective and all settings"""
    # Request all important fields explicitly (only allowed fields from VK API)
    fields = "id,name,status,objective,autobidding_mode,budget_limit,budget_limit_day,date_start,date_end,max_price,priced_goal,pricelist_id,enable_offline_goals"
    url = f"{base_url}/ad_plans/{campaign_id}.json?fields={fields}"

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


def create_campaign_with_group(token: str, base_url: str, campaign_data: dict, group_data: dict) -> dict:
    """
    Create a new campaign with an ad group (required by VK API - can't create empty campaign).

    VK Ads API: POST /api/v2/ad_plans.json

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        campaign_data: Campaign parameters (name, objective, status, etc.)
        group_data: Ad group data with banners to create inside campaign

    Returns:
        dict: {
            "success": bool,
            "campaign_id": int,
            "ad_group_id": int,
            "data": {...}
        } or {"success": False, "error": str}
    """
    url = f"{base_url}/ad_plans.json"

    try:
        # Prepare campaign with group
        campaign_payload = campaign_data.copy()
        campaign_payload['ad_groups'] = [group_data]

        logger.info(f"[ACTION] Creating campaign with group: {campaign_data.get('name')}")
        logger.info(f"[DEBUG] Group has {len(group_data.get('banners', []))} banners")

        response = requests.post(
            url,
            headers=_headers(token),
            json=campaign_payload,
            timeout=60  # Longer timeout for campaign+group+banners
        )

        if response.status_code in (200, 201, 204):
            result = response.json()
            campaign_id = result.get('id')

            # Get created ad_group id from response
            ad_groups = result.get('ad_groups', [])
            ad_group_id = ad_groups[0].get('id') if ad_groups else None

            logger.info(f"[OK] Campaign created: ID={campaign_id}, ad_group_id={ad_group_id}")
            return {
                "success": True,
                "campaign_id": campaign_id,
                "ad_group_id": ad_group_id,
                "data": result
            }
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error creating campaign with group: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error creating campaign with group: {error_msg}")
        return {"success": False, "error": error_msg}


def copy_campaign_settings(original_campaign: dict) -> dict:
    """
    Extract copyable settings from original campaign for new campaign creation.

    Args:
        original_campaign: Full campaign data from get_campaign_full()

    Returns:
        dict: Settings to use when creating new campaign
    """
    # Fields to copy from original campaign (only allowed fields from VK API)
    # Note: priced_goal excluded - can contain invalid/empty values that VK API rejects
    COPYABLE_FIELDS = {
        'objective',           # Required: Campaign objective
        'autobidding_mode',    # Bidding strategy
        'budget_limit_day',    # Daily budget
        'budget_limit',        # Total budget
        'pricelist_id',        # Price list
        'max_price',           # Max price limit
        'enable_offline_goals',  # Offline goals
    }

    result = {}
    for field in COPYABLE_FIELDS:
        value = original_campaign.get(field)
        if value is not None:
            result[field] = value

    return result
