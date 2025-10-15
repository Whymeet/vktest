import requests
import time
from datetime import datetime
from logging import getLogger

logger = getLogger("vk_ads_manager")

def _headers(token: str):
    return {"Authorization": f"Bearer {token}"}

def get_ad_groups_active(token: str, base_url: str, fields: str = "id,name,status,delivery,ad_plan_id", limit: int = 200, sleep_between_calls: float = 0.25):
    url = f"{base_url}/ad_groups.json"
    offset = 0
    items_all = []
    page_num = 1
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
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке групп: {r.text[:200]}")
                raise RuntimeError(f"[ad_groups] HTTP {r.status_code}: {r.text}")
            payload = r.json()
            items = payload.get("items", [])
            items_all.extend(items)
            if len(items) < limit:
                break
            offset += limit
            page_num += 1
            time.sleep(sleep_between_calls)
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка сети при загрузке групп: {e}")
            raise
    return items_all

def get_ad_groups_stats_day(token: str, base_url: str, date_from: str, date_to: str, group_ids: list = None, metrics: str = "base"):
    url = f"{base_url}/statistics/ad_groups/day.json"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "metrics": metrics,
    }
    if group_ids:
        params["id"] = ",".join(map(str, group_ids))
    r = requests.get(url, headers=_headers(token), params=params, timeout=30)
    if r.status_code != 200:
        logger.error(f"❌ Ошибка HTTP {r.status_code} при получении статистики: {r.text[:200]}")
        raise RuntimeError(f"[stats day] HTTP {r.status_code}: {r.text}")
    payload = r.json()
    return payload.get("items", [])

def disable_ad_group(token: str, base_url: str, group_id: int, dry_run: bool = True):
    if dry_run:
        logger.info(f"🔸 [DRY RUN] Группа {group_id} была бы отключена (active → blocked)")
        return {"success": True, "dry_run": True}
    url = f"{base_url}/ad_groups/{group_id}.json"
    data = {"status": "blocked"}
    try:
        logger.info(f"🔄 Отключаем группу {group_id} (active → blocked)")
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        if response.status_code in (200, 204):
            logger.info(f"✅ Группа {group_id} успешно отключена (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при отключении группы {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при отключении группы {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}

def toggle_ad_group_status(token: str, base_url: str, group_id: int, status: str):
    """
    Изменяет статус рекламной группы
    
    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        group_id: ID группы
        status: Новый статус ("active" или "stopped")
    
    Returns:
        dict: {"success": bool, "response": dict или "error": str}
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Неверный статус '{status}'. Допустимые значения: 'active', 'blocked'"
        logger.error(f"❌ {error_msg}")
        return {"success": False, "error": error_msg}
    
    url = f"{base_url}/ad_groups/{group_id}.json"
    data = {"status": status}
    
    try:
        status_emoji = "▶️" if status == "active" else "⏸️"
        action = "включаем" if status == "active" else "блокируем"
        logger.info(f"{status_emoji} {action.capitalize()} триггер группу {group_id} (→ {status})")
        
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        
        if response.status_code in (200, 204):
            logger.info(f"✅ Группа {group_id} успешно изменена на '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при изменении статуса группы {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при изменении статуса группы {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}
