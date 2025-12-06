import requests
import time
from datetime import datetime
from logging import getLogger

logger = getLogger("vk_ads_manager")


def _interruptible_sleep(seconds):
    """
    Прерываемый sleep - разбивает длительный сон на короткие интервалы,
    чтобы можно было прервать выполнение через Ctrl+C
    """
    end_time = time.time() + seconds
    while time.time() < end_time:
        try:
            remaining = min(1.0, end_time - time.time())
            if remaining > 0:
                time.sleep(remaining)
        except KeyboardInterrupt:
            logger.warning("🛑 Прерывание пользователем во время ожидания")
            raise

# Константы для ретраев (импортируются из main.py при необходимости)
API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 30  # Уменьшили с 90 до 30 секунд
API_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

def _headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def _request_with_retries(
    method: str,
    url: str,
    *,
    max_retries: int = API_MAX_RETRIES,
    retry_delay: int = API_RETRY_DELAY_SECONDS,
    **kwargs,
):
    """
    Универсальный обёртка над requests с ретраями по временным ошибкам:
    429, 500, 502, 503, 504 + сетевые ошибки.

    На каждый фэйл:
      - пишет в лог
      - ждёт retry_delay секунд (по умолчанию 90)
      - повторяет до max_retries раз
    """
    attempt = 0

    while True:
        attempt += 1
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as e:
            if attempt > max_retries:
                logger.error(
                    f"❌ {method} {url} — сетевая ошибка после {attempt} попыток: {e}"
                )
                raise

            # Для сетевых ошибок используем более короткие задержки
            wait = min(5 + attempt * 3, 15)  # 5, 8, 11 секунд максимум
            logger.warning(
                f"⚠️ {method} {url} — сетевая ошибка: {e}. "
                f"Пауза {wait} сек перед повтором ({attempt}/{max_retries})"
            )
            _interruptible_sleep(wait)
            continue

        # Временные/лимитные статусы — ждём и ретраим
        if resp.status_code in API_RETRY_STATUS_CODES:
            # Логируем подробности ответа для диагностики
            response_headers = dict(resp.headers)
            response_text = resp.text[:500] if resp.text else "Пустое тело ответа"
            
            # Определяем тип ошибки для статистики
            error_type = "неизвестная"
            try:
                if resp.text:
                    error_data = resp.json()
                    if "error" in error_data:
                        error_info = error_data["error"]
                        if isinstance(error_info, dict):
                            error_type = error_info.get("code", "неизвестная")
            except:
                pass
            
            logger.debug(
                f"🔍 Подробности ошибки {resp.status_code} (тип: {error_type}):\n"
                f"   URL: {url}\n"
                f"   Rate Limit: {response_headers.get('x-ratelimit-hourly-remaining', 'N/A')}/{response_headers.get('x-ratelimit-hourly-limit', 'N/A')}\n"
                f"   Headers: {response_headers}\n"
                f"   Body: {response_text}"
            )
            
            if attempt > max_retries:
                logger.error(
                    f"❌ {method} {url} — HTTP {resp.status_code} после {attempt} "
                    f"попыток.\n   Заголовки ответа: {response_headers}\n"
                    f"   Тело ответа: {response_text}"
                )
                raise RuntimeError(
                    f"HTTP {resp.status_code} после {attempt} попыток: {response_text}"
                )

            # Специальный случай — 429 Too Many Requests
            if resp.status_code == 429:
                wait = 60  # 1 минута для rate limit
                try:
                    retry_after = int(resp.headers.get("Retry-After", "0"))
                    if retry_after > 0:
                        wait = max(wait, retry_after)
                except ValueError:
                    pass

                logger.warning(
                    f"⚠️ {method} {url} — лимит запросов (429). "
                    f"Ждём {wait} сек и повторяем ({attempt}/{max_retries})\n"
                    f"   Retry-After: {resp.headers.get('Retry-After', 'не указан')}"
                )
                _interruptible_sleep(wait)
            else:
                # Анализируем тип ошибки для более умной обработки
                error_type = "неизвестная"
                try:
                    if resp.text:
                        error_data = resp.json()
                        if "error" in error_data:
                            error_info = error_data["error"]
                            if isinstance(error_info, dict):
                                error_type = error_info.get("code", "неизвестная")
                            else:
                                error_type = str(error_info)
                except:
                    pass
                
                # Для серверных ошибок используем более короткие задержки
                if resp.status_code in [500, 502, 503, 504]:
                    # Для unknown_api_error используем еще более короткие интервалы
                    if error_type == "unknown_api_error":
                        wait = min(5 + attempt * 2, 15)  # 5, 7, 9 секунд максимум
                    else:
                        wait = min(10 + attempt * 5, retry_delay)  # 10, 15, 20 секунд
                else:
                    wait = retry_delay
                
                logger.warning(
                    f"⚠️ {method} {url} — временная ошибка HTTP {resp.status_code} ({error_type}). "
                    f"Ждём {wait} сек и повторяем ({attempt}/{max_retries})\n"
                    f"   Заголовки: {dict(list(resp.headers.items())[:5])}\n"
                    f"   Тело: {resp.text[:200] if resp.text else 'Пустое'}"
                )
                _interruptible_sleep(wait)

            continue

        # Всё ок, выходим
        if attempt > 1:
            logger.info(f"✅ {method} {url} — успешно восстановлено после {attempt-1} попыток")
        return resp

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


def get_ad_groups_active(token: str, base_url: str, fields: str = "id,name,status", limit: int = 200):
    """Загружает все активные группы объявлений (ad_groups)"""
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
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке групп: {r.text[:200]}")
                raise RuntimeError(f"[ad_groups] HTTP {r.status_code}: {r.text}")
            
            payload = r.json()
            items = payload.get("items", [])
            items_all.extend(items)
            
            if len(items) < limit:
                break
                
            offset += limit
            time.sleep(0.25)
            
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка сети при загрузке групп: {e}")
            raise
    
    return items_all


def disable_ad_group(token: str, base_url: str, group_id: int, dry_run: bool = False):
    """Отключает группу объявлений (ad_group)"""
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
