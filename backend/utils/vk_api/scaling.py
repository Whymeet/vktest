"""
VK Ads API - Scaling / Duplication operations
"""
import re
import requests
import time
from utils.logging_setup import get_logger
from utils.vk_api.core import _headers, VK_MIN_DAILY_BUDGET
from utils.vk_api.ad_groups import get_ad_group_full, create_ad_group, update_ad_group
from utils.vk_api.campaigns import get_campaign_full

logger = get_logger(service="vk_api")


def get_banners_by_ad_group(token: str, base_url: str, ad_group_id: int, include_stopped: bool = True):
    """
    Get all non-deleted banners from a group

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        ad_group_id: Ad group ID
        include_stopped: Include stopped banners

    Returns:
        list: List of banners (active + stopped, without deleted)
    """
    # VK Ads API v2: GET /banners.json with group filter
    url = f"{base_url}/banners.json"
    offset = 0
    limit = 200
    all_banners = []

    while True:
        params = {
            "limit": limit,
            "offset": offset,
            # Filter by ad group
            "_ad_group_id": ad_group_id,
            # Request all writable fields according to VK Ads API documentation
            "fields": "id,name,status,ad_group_id,content,textblocks,urls"
        }

        try:
            logger.info(f"[INFO] Loading banners for group {ad_group_id}: GET {url} with filter _ad_group_id={ad_group_id}")
            response = requests.get(url, headers=_headers(token), params=params, timeout=20)

            if response.status_code != 200:
                error_text = response.text[:500] if response.text else 'empty'
                logger.error(f"[ERROR] Error loading banners for group {ad_group_id}: HTTP {response.status_code} - {error_text}")
                break

            data = response.json()
            items = data.get("items", [])
            logger.info(f"[INFO] Group {ad_group_id}: received {len(items)} banners (offset={offset})")

            # Filter: remove deleted
            for banner in items:
                is_deleted = banner.get("deleted", False)
                banner_status = banner.get("status", "unknown")

                if is_deleted or banner_status == "deleted":
                    continue

                # If not including stopped - skip them
                if not include_stopped and banner_status in ["blocked", "stopped"]:
                    continue

                all_banners.append(banner)

            if len(items) < limit:
                break

            offset += limit
            time.sleep(0.1)  # Rate limiting

        except requests.RequestException as e:
            logger.error(f"[ERROR] Network error loading banners for group {ad_group_id}: {e}")
            break

    return all_banners


def create_banner(token: str, base_url: str, banner_data: dict):
    """Create a new banner in a group"""
    ad_group_id = banner_data.get('ad_group_id')
    if not ad_group_id:
        return {"success": False, "error": "ad_group_id is required"}

    # VK Ads API v2: POST /ad_groups/{ad_group_id}/banners.json
    url = f"{base_url}/ad_groups/{ad_group_id}/banners.json"

    # Remove ad_group_id from data - it's already in URL
    data_to_send = {k: v for k, v in banner_data.items() if k != 'ad_group_id'}

    print(f"   [ACTION] Creating banner: POST {url}")
    print(f"   [DATA] Data: {data_to_send}")

    try:
        response = requests.post(url, headers=_headers(token), json=data_to_send, timeout=30)

        print(f"   [RESPONSE] Response: {response.status_code} - {response.text[:500] if response.text else 'empty'}")

        if response.status_code in (200, 201):
            result = response.json()
            logger.info(f"[OK] Banner created: ID={result.get('id')}")
            return {"success": True, "data": result}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"[ERROR] Error creating banner: {error_msg}")
            return {"success": False, "error": error_msg}

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"[ERROR] Error creating banner: {error_msg}")
        return {"success": False, "error": error_msg}


def _generate_copy_name(original_name: str) -> str:
    """
    Generate name for group copy.
    If name already contains "(copy)", adds a number.

    Examples:
        "Group 1" -> "Group 1 (copy)"
        "Group 1 (copy)" -> "Group 1 (copy 2)"
        "Group 1 (copy 2)" -> "Group 1 (copy 3)"
    """
    if not original_name:
        return "Copy"

    # Check pattern "(copy N)" at the end
    pattern_numbered = r'^(.+?)\s*\((?:копия|copy)\s+(\d+)\)\s*$'
    match_numbered = re.match(pattern_numbered, original_name, re.IGNORECASE)

    if match_numbered:
        base_name = match_numbered.group(1).strip()
        current_num = int(match_numbered.group(2))
        return f"{base_name} (копия {current_num + 1})"

    # Check pattern "(copy)" without number
    pattern_simple = r'^(.+?)\s*\((?:копия|copy)\)\s*$'
    match_simple = re.match(pattern_simple, original_name, re.IGNORECASE)

    if match_simple:
        base_name = match_simple.group(1).strip()
        return f"{base_name} (копия 2)"

    # Normal name - add "(copy)"
    return f"{original_name} (копия)"


def duplicate_ad_group_full(
    token: str,
    base_url: str,
    ad_group_id: int,
    new_name: str = None,
    new_budget: float = None,
    auto_activate: bool = False,
    rate_limit_delay: float = 0.03,
    account_name: str = None,  # For logging
    target_campaign_id: int = None  # If set, duplicate to this campaign instead of original
):
    """
    Full duplication of ad group with all non-deleted banners.
    Uses method of creating group with banners in one request (POST /ad_groups.json with banners field).

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        ad_group_id: ID of group to duplicate
        account_name: Account name for logging (optional)
        new_name: New group name. If None or empty - uses ORIGINAL name.
        new_budget: New group budget in rubles. If None or 0 - copies original budget.
        auto_activate: Automatically activate group and banners
        rate_limit_delay: Delay between requests (default 0.03 sec = ~33 req/sec)

    Returns:
        dict: {
            "success": bool,
            "new_ad_group_id": int,
            "duplicated_banners": [...],
            "skipped_banners": [...],
            "errors": [...]
        }
    """
    # Fields we DON'T copy (read-only or statistics)
    EXCLUDED_GROUP_FIELDS = {
        'id', 'created', 'updated', 'created_at', 'updated_at', 'deleted',
        'statistics', 'clicks', 'shows', 'spent', 'ctr',
        'conversions', 'cost_per_conversion', 'impressions',
        'banner_count', 'banners', 'delivery', 'issues', 'read_only',
        'interface_read_only', 'user_id', 'stats_info', 'learning_progress',
        'efficiency_status', 'vkads_status', 'or_status', 'or_migrated',
        'budget_limit_day', 'budget_limit', 'budget_limit_per_day'  # Don't copy, set separately
    }

    # Excluded banner fields (read-only according to VK Ads documentation)
    EXCLUDED_BANNER_FIELDS = {
        'id', 'ad_group_id', 'created', 'updated', 'created_at', 'updated_at',
        'moderation_status', 'moderation_reasons', 'delivery', 'deleted',
        'issues', 'ord_marker', 'user_id', 'read_only', 'interface_read_only',
        # Statistics
        'clicks', 'shows', 'spent', 'ctr', 'conversions',
        'cost_per_conversion', 'impressions',
        # Other read-only fields
        'stats_info', 'preview_url', 'audit_pixels',
        # Field status - remove, as when creating group with banners, status is inherited from group
        'status'
        # Note: 'name' is NOT excluded - we want to preserve banner names
    }

    def clean_content(content_data):
        """Clean content, keeping only media object ids"""
        if not content_data:
            return None
        cleaned = {}
        for key, value in content_data.items():
            if isinstance(value, dict) and 'id' in value:
                # For media objects keep only id
                cleaned[key] = {'id': value['id']}
        return cleaned if cleaned else None

    def clean_urls(urls_data):
        """Clean urls, keeping only ids"""
        if not urls_data:
            return None
        cleaned = {}
        for key, value in urls_data.items():
            if isinstance(value, dict) and 'id' in value:
                cleaned[key] = {'id': value['id']}
        return cleaned if cleaned else None

    # Log prefix with account name
    log_prefix = f"[{account_name}]" if account_name else ""

    try:
        print(f"")
        print(f"{'='*80}")
        print(f"{log_prefix} [TARGET] DUPLICATING GROUP {ad_group_id}")
        print(f"{'='*80}")

        # ===== STEP 1: Load group data =====
        print(f"[INFO] Step 1/2: Loading group data and banners...")
        original_group = get_ad_group_full(token, base_url, ad_group_id)

        if not original_group:
            return {"success": False, "error": "Failed to load group"}

        print(f"[OK] Loaded group: {original_group.get('name', 'Unknown')}")

        time.sleep(rate_limit_delay)

        # Load group banners
        banners = get_banners_by_ad_group(token, base_url, ad_group_id, include_stopped=True)
        print(f"[OK] Found {len(banners)} banners for copying")

        # Copy all group fields except excluded
        new_group_data = {}
        for key, value in original_group.items():
            if key not in EXCLUDED_GROUP_FIELDS and value is not None:
                new_group_data[key] = value

        # If objective is missing, get it from campaign (ad_plan)
        if 'objective' not in new_group_data or not new_group_data.get('objective'):
            campaign_id = original_group.get('ad_plan_id') or original_group.get('campaign_id')
            print(f"[WARN] objective not found in group, looking in campaign {campaign_id}")
            if campaign_id:
                time.sleep(rate_limit_delay)
                campaign = get_campaign_full(token, base_url, campaign_id)
                if campaign and campaign.get('objective'):
                    new_group_data['objective'] = campaign['objective']
                    print(f"[OK] Got objective: {campaign['objective']}")

        # Change name
        # If new_name is specified and not empty - use it
        # If new_name is empty or None - use ORIGINAL group name
        if new_name and new_name.strip():
            new_group_data['name'] = new_name.strip()
        else:
            # Use original group name
            new_group_data['name'] = original_group.get('name', 'Copy')

        # Set budget - VK API requires budget_limit_day
        budget_to_set = None
        if new_budget is not None and new_budget > 0:
            if new_budget >= VK_MIN_DAILY_BUDGET:
                budget_to_set = int(new_budget)
                logger.info(f"[INFO] Set new daily budget: {budget_to_set} rub")
        else:
            original_budget = original_group.get('budget_limit_day')
            logger.debug(f"[DEBUG] Original budget_limit_day: {original_budget} (type: {type(original_budget)})")
            if original_budget:
                try:
                    budget_int = int(float(original_budget))
                    if budget_int >= VK_MIN_DAILY_BUDGET:
                        budget_to_set = budget_int
                        logger.info(f"[INFO] Copied budget from original: {budget_int} rub")
                    else:
                        logger.warning(f"[WARN] Original budget {budget_int} < min {VK_MIN_DAILY_BUDGET}, using minimum")
                        budget_to_set = VK_MIN_DAILY_BUDGET
                except (ValueError, TypeError) as e:
                    logger.warning(f"[WARN] Failed to parse original budget '{original_budget}': {e}")

        # If still no budget, use minimum (VK API requires this field)
        if budget_to_set is None:
            budget_to_set = VK_MIN_DAILY_BUDGET
            logger.info(f"[INFO] No budget specified, using minimum: {budget_to_set} rub")

        # VK API accepts budget_limit_day as integer (in rubles)
        new_group_data['budget_limit_day'] = budget_to_set

        # IMPORTANT: Always create group with 'blocked' status to bypass active banners limit
        # If auto-activation needed - activate after creation
        new_group_data['status'] = 'blocked'

        # Override campaign if target_campaign_id is specified
        if target_campaign_id:
            new_group_data['ad_plan_id'] = target_campaign_id
            print(f"[INFO] Using target campaign: {target_campaign_id}")

        # ===== STEP 2: Prepare banners for creation with group =====
        banners_for_create = []
        original_banner_info = []  # For tracking original IDs

        for banner in banners:
            banner_id = banner.get('id')
            banner_name = banner.get('name', 'Unknown')

            # Copy banner fields
            new_banner_data = {}
            for key, value in banner.items():
                if key not in EXCLUDED_BANNER_FIELDS and value is not None:
                    new_banner_data[key] = value

            # Clean content - keep only id
            if 'content' in new_banner_data:
                cleaned_content = clean_content(new_banner_data['content'])
                if cleaned_content:
                    new_banner_data['content'] = cleaned_content
                else:
                    del new_banner_data['content']

            # Clean urls - keep only id
            if 'urls' in new_banner_data:
                cleaned_urls = clean_urls(new_banner_data['urls'])
                if cleaned_urls:
                    new_banner_data['urls'] = cleaned_urls
                else:
                    del new_banner_data['urls']

            print(f"   [INFO] Banner {banner_id}: content={new_banner_data.get('content')}, urls={new_banner_data.get('urls')}, textblocks={list(new_banner_data.get('textblocks', {}).keys()) if new_banner_data.get('textblocks') else None}")

            banners_for_create.append(new_banner_data)
            original_banner_info.append({
                "original_id": banner_id,
                "name": banner_name
            })

        # Add banners to group data
        if banners_for_create:
            new_group_data['banners'] = banners_for_create
            print(f"[INFO] Prepared {len(banners_for_create)} banners for creation with group")

        # ===== Create group with banners in one request =====
        print(f"[ACTION] Step 2/2: Creating group with banners (status: blocked)...")
        logger.info(f"[INFO] New group settings:")
        logger.info(f"   - Name: {new_group_data['name']}")
        logger.info(f"   - Status: blocked (to bypass active banners limit)")
        logger.info(f"   - Auto-activation after creation: {auto_activate}")
        logger.info(f"   - Objective: {new_group_data.get('objective', 'NOT SET')}")
        logger.info(f"   - Banners: {len(banners_for_create)}")

        time.sleep(rate_limit_delay)

        create_result = create_ad_group(token, base_url, new_group_data)

        if not create_result.get("success"):
            return {"success": False, "error": create_result.get("error", "Error creating group")}

        new_group_id = create_result["data"].get("id")
        created_banners = create_result["data"].get("banners", [])

        logger.info(f"[OK] Group created! ID: {new_group_id}")
        logger.info(f"[OK] Banners created: {len(created_banners)}")

        # Final status (may change after activation)
        final_status = 'blocked'

        # If auto-activation needed - activate group after creation
        if auto_activate:
            logger.info(f"[ACTION] Activating group {new_group_id}...")
            time.sleep(rate_limit_delay)
            activate_result = update_ad_group(token, base_url, new_group_id, {"status": "active"})
            if activate_result.get("success"):
                final_status = 'active'
                logger.info(f"[OK] Group {new_group_id} activated")
            else:
                error_text = str(activate_result.get('error', 'Unknown error'))[:100]
                logger.warning(f"[WARN] Failed to activate group: {error_text}")

        # Form result
        duplicated_banners = []
        for i, created_banner in enumerate(created_banners):
            new_banner_id = created_banner.get("id")
            if i < len(original_banner_info):
                orig_info = original_banner_info[i]
                duplicated_banners.append({
                    "original_id": orig_info["original_id"],
                    "new_id": new_banner_id,
                    "name": orig_info["name"],
                    "status": final_status
                })
            else:
                duplicated_banners.append({
                    "original_id": None,
                    "new_id": new_banner_id,
                    "name": "Unknown",
                    "status": final_status
                })

        # ===== RESULTS =====
        logger.info(f"")
        logger.info(f"{'='*80}")
        logger.info(f"[OK] DUPLICATION COMPLETED")
        logger.info(f"{'='*80}")
        logger.info(f"Original group: {ad_group_id} - {original_group.get('name')}")
        logger.info(f"New group: {new_group_id} - {new_group_data['name']}")
        logger.info(f"Copied banners: {len(duplicated_banners)}/{len(banners)}")
        logger.info(f"{'='*80}")

        return {
            "success": True,
            "original_group_id": ad_group_id,
            "original_group_name": original_group.get('name'),
            "new_group_id": new_group_id,
            "new_group_name": new_group_data['name'],
            "total_banners": len(banners),
            "duplicated_banners": duplicated_banners,
            "skipped_banners": [],
            "errors": []
        }

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": error_msg}


def duplicate_ad_group_to_new_campaign(
    token: str,
    base_url: str,
    ad_group_id: int,
    campaign_data: dict,
    new_name: str = None,
    new_budget: float = None,
    auto_activate: bool = False,
    rate_limit_delay: float = 0.03,
    account_name: str = None
) -> dict:
    """
    Duplicate ad group and create a NEW campaign with it.
    VK API requires campaign to have at least one ad group, so we create them together.

    Args:
        token: VK Ads API token
        base_url: VK Ads API base URL
        ad_group_id: ID of group to duplicate
        campaign_data: Campaign data (name, objective, status, etc.) - without ad_groups
        new_name: New group name (optional)
        new_budget: New group budget (optional)
        auto_activate: Auto-activate after creation
        rate_limit_delay: Delay between API calls
        account_name: Account name for logging

    Returns:
        dict: {
            "success": bool,
            "new_campaign_id": int,
            "new_group_id": int,
            "duplicated_banners": [...],
            "errors": [...]
        }
    """
    from utils.vk_api.campaigns import create_campaign_with_group

    # Same excluded fields as duplicate_ad_group_full
    EXCLUDED_GROUP_FIELDS = {
        'id', 'created', 'updated', 'created_at', 'updated_at', 'deleted',
        'statistics', 'clicks', 'shows', 'spent', 'ctr',
        'conversions', 'cost_per_conversion', 'impressions',
        'banner_count', 'banners', 'delivery', 'issues', 'read_only',
        'interface_read_only', 'user_id', 'stats_info', 'learning_progress',
        'efficiency_status', 'vkads_status', 'or_status', 'or_migrated',
        'budget_limit_day', 'budget_limit', 'budget_limit_per_day',
        'ad_plan_id',  # Don't copy campaign ID - we're creating new campaign
        'priced_goal'  # Can contain invalid/empty values that VK API rejects
    }

    EXCLUDED_BANNER_FIELDS = {
        'id', 'ad_group_id', 'created', 'updated', 'created_at', 'updated_at',
        'moderation_status', 'moderation_reasons', 'delivery', 'deleted',
        'issues', 'ord_marker', 'user_id', 'read_only', 'interface_read_only',
        'clicks', 'shows', 'spent', 'ctr', 'conversions',
        'cost_per_conversion', 'impressions',
        'stats_info', 'preview_url', 'audit_pixels',
        'status'
    }

    def clean_content(content_data):
        if not content_data:
            return None
        cleaned = {}
        for key, value in content_data.items():
            if isinstance(value, dict) and 'id' in value:
                cleaned[key] = {'id': value['id']}
        return cleaned if cleaned else None

    def clean_urls(urls_data):
        if not urls_data:
            return None
        cleaned = {}
        for key, value in urls_data.items():
            if isinstance(value, dict) and 'id' in value:
                cleaned[key] = {'id': value['id']}
        return cleaned if cleaned else None

    log_prefix = f"[{account_name}]" if account_name else ""

    try:
        print(f"")
        print(f"{'='*80}")
        print(f"{log_prefix} [NEW CAMPAIGN] DUPLICATING GROUP {ad_group_id} TO NEW CAMPAIGN")
        print(f"{'='*80}")

        # Step 1: Load original group
        print(f"[INFO] Step 1/2: Loading group data and banners...")
        original_group = get_ad_group_full(token, base_url, ad_group_id)

        if not original_group:
            return {"success": False, "error": "Failed to load group"}

        print(f"[OK] Loaded group: {original_group.get('name', 'Unknown')}")

        time.sleep(rate_limit_delay)

        # Load banners
        banners = get_banners_by_ad_group(token, base_url, ad_group_id, include_stopped=True)
        print(f"[OK] Found {len(banners)} banners for copying")

        # Prepare group data
        new_group_data = {}
        for key, value in original_group.items():
            if key not in EXCLUDED_GROUP_FIELDS and value is not None:
                new_group_data[key] = value

        # Get objective from campaign if missing
        if 'objective' not in new_group_data or not new_group_data.get('objective'):
            # Use campaign objective
            new_group_data['objective'] = campaign_data.get('objective')
            print(f"[INFO] Using campaign objective: {campaign_data.get('objective')}")

        # Set name
        if new_name and new_name.strip():
            new_group_data['name'] = new_name.strip()
        else:
            new_group_data['name'] = original_group.get('name', 'Copy')

        # Set budget
        budget_to_set = None
        if new_budget is not None and new_budget > 0:
            if new_budget >= VK_MIN_DAILY_BUDGET:
                budget_to_set = int(new_budget)
        else:
            original_budget = original_group.get('budget_limit_day')
            if original_budget:
                try:
                    budget_int = int(float(original_budget))
                    if budget_int >= VK_MIN_DAILY_BUDGET:
                        budget_to_set = budget_int
                    else:
                        budget_to_set = VK_MIN_DAILY_BUDGET
                except (ValueError, TypeError):
                    pass

        if budget_to_set is None:
            budget_to_set = VK_MIN_DAILY_BUDGET

        new_group_data['budget_limit_day'] = budget_to_set
        new_group_data['status'] = 'blocked'  # Create blocked, activate later

        # Prepare banners
        banners_for_create = []
        original_banner_info = []

        for banner in banners:
            banner_id = banner.get('id')
            banner_name = banner.get('name', 'Unknown')

            new_banner_data = {}
            for key, value in banner.items():
                if key not in EXCLUDED_BANNER_FIELDS and value is not None:
                    new_banner_data[key] = value

            if 'content' in new_banner_data:
                cleaned_content = clean_content(new_banner_data['content'])
                if cleaned_content:
                    new_banner_data['content'] = cleaned_content
                else:
                    del new_banner_data['content']

            if 'urls' in new_banner_data:
                cleaned_urls = clean_urls(new_banner_data['urls'])
                if cleaned_urls:
                    new_banner_data['urls'] = cleaned_urls
                else:
                    del new_banner_data['urls']

            banners_for_create.append(new_banner_data)
            original_banner_info.append({
                "original_id": banner_id,
                "name": banner_name
            })

        # Add banners to group
        if banners_for_create:
            new_group_data['banners'] = banners_for_create
            print(f"[INFO] Prepared {len(banners_for_create)} banners")

        # Step 2: Create campaign with group
        print(f"[ACTION] Step 2/2: Creating campaign '{campaign_data.get('name')}' with group...")

        result = create_campaign_with_group(token, base_url, campaign_data, new_group_data)

        if not result.get('success'):
            return {"success": False, "error": result.get('error', 'Failed to create campaign')}

        new_campaign_id = result.get('campaign_id')
        new_group_id = result.get('ad_group_id')

        # Get banners from response
        created_banners = result.get('data', {}).get('ad_groups', [{}])[0].get('banners', [])

        print(f"[OK] Campaign created: {new_campaign_id}")
        print(f"[OK] Group created: {new_group_id}")
        print(f"[OK] Banners: {len(created_banners)}")

        # Build result
        duplicated_banners = []
        for i, created_banner in enumerate(created_banners):
            new_banner_id = created_banner.get("id")
            if i < len(original_banner_info):
                orig_info = original_banner_info[i]
                duplicated_banners.append({
                    "original_id": orig_info["original_id"],
                    "new_id": new_banner_id,
                    "name": orig_info["name"],
                    "status": "blocked"
                })

        print(f"")
        print(f"{'='*80}")
        print(f"[OK] NEW CAMPAIGN DUPLICATION COMPLETED")
        print(f"{'='*80}")

        return {
            "success": True,
            "original_group_id": ad_group_id,
            "original_group_name": original_group.get('name'),
            "new_campaign_id": new_campaign_id,
            "new_group_id": new_group_id,
            "new_group_name": new_group_data['name'],
            "total_banners": len(banners),
            "duplicated_banners": duplicated_banners,
            "skipped_banners": [],
            "errors": []
        }

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": error_msg}
