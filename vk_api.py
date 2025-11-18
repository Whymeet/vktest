import requests
import time
from datetime import datetime
from logging import getLogger

logger = getLogger("vk_ads_manager")

def _headers(token: str):
    return {"Authorization": f"Bearer {token}"}

def get_banners_active(token: str, base_url: str, fields: str = "id,name,status,delivery,ad_group_id", limit: int = 200, sleep_between_calls: float = 0.25):
    """Загружает все активные рекламные объявления (banners)"""
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
            "_ad_group_status": "active"  # Только объявления из активных групп
        }
        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=20)
            if r.status_code != 200:
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке объявлений: {r.text[:200]}")
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
            logger.error(f"❌ Ошибка сети при загрузке объявлений: {e}")
            raise
    return items_all

def get_banners_stats_day(token: str, base_url: str, date_from: str, date_to: str, banner_ids: list = None, metrics: str = "base"):
    """Получает статистику по рекламным объявлениям (banners)"""
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
        logger.error(f"❌ Ошибка HTTP {r.status_code} при получении статистики: {r.text[:200]}")
        raise RuntimeError(f"[banners stats] HTTP {r.status_code}: {r.text}")
    payload = r.json()
    return payload.get("items", [])

def disable_banner(token: str, base_url: str, banner_id: int, dry_run: bool = True):
    """Отключает рекламное объявление (banner)"""
    if dry_run:
        logger.info(f"🔸 [DRY RUN] Объявление {banner_id} было бы отключено (active → blocked)")
        return {"success": True, "dry_run": True}
    url = f"{base_url}/banners/{banner_id}.json"
    data = {"status": "blocked"}
    try:
        logger.info(f"🔄 Отключаем объявление {banner_id} (active → blocked)")
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        if response.status_code in (200, 204):
            logger.info(f"✅ Объявление {banner_id} успешно отключено (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при отключении объявления {banner_id}: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при отключении объявления {banner_id}: {error_msg}")
        return {"success": False, "error": error_msg}

def toggle_banner_status(token: str, base_url: str, banner_id: int, status: str):
    """
    Изменяет статус рекламного объявления (banner)
    
    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        banner_id: ID объявления
        status: Новый статус ("active" или "blocked")
    
    Returns:
        dict: {"success": bool, "response": dict или "error": str}
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Неверный статус '{status}'. Допустимые значения: 'active', 'blocked'"
        logger.error(f"❌ {error_msg}")
        return {"success": False, "error": error_msg}
    
    url = f"{base_url}/banners/{banner_id}.json"
    data = {"status": status}
    
    try:
        status_emoji = "▶️" if status == "active" else "⏸️"
        action = "включаем" if status == "active" else "блокируем"
        logger.info(f"{status_emoji} {action.capitalize()} триггер объявление {banner_id} (→ {status})")
        
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        
        if response.status_code in (200, 204):
            logger.info(f"✅ Объявление {banner_id} успешно изменено на '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при изменении статуса объявления {banner_id}: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при изменении статуса объявления {banner_id}: {error_msg}")
        return {"success": False, "error": error_msg}
