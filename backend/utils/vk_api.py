import requests
import time
from datetime import datetime
from utils.logging_setup import get_logger

logger = get_logger(service="vk_api")


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
API_RETRY_DELAY_SECONDS = 15  # Уменьшили с 90 до 30, теперь до 15 секунд
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
                wait = 15  # Уменьшено с 60 до 15 секунд для rate limit
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
                error_text = r.text[:200]
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке объявлений: {error_text}")
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
        error_text = r.text[:200]
        logger.error(f"❌ Ошибка HTTP {r.status_code} при получении статистики: {error_text}")
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

def get_banner_info(token: str, base_url: str, banner_id: int):
    """
    Получает информацию о конкретном объявлении (banner)

    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        banner_id: ID объявления

    Returns:
        dict: Информация о баннере или None при ошибке
    """
    url = f"{base_url}/banners/{banner_id}.json"

    try:
        response = _request_with_retries("GET", url, headers=_headers(token), timeout=20)

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"❌ Ошибка получения информации о баннере {banner_id}: HTTP {response.status_code}")
            return None

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при получении информации о баннере {banner_id}: {e}")
        return None


def toggle_ad_group_status(token: str, base_url: str, group_id: int, status: str):
    """
    Изменяет статус группы объявлений (ad_group)
    
    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        group_id: ID группы объявлений
        status: Новый статус ("active" или "blocked")
    
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
        logger.info(f"{status_emoji} {action.capitalize()} группу объявлений {group_id} (→ {status})")
        
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


def toggle_campaign_status(token: str, base_url: str, campaign_id: int, status: str):
    """
    Изменяет статус рекламной кампании (ad_plan)
    
    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        campaign_id: ID кампании
        status: Новый статус ("active" или "blocked")
    
    Returns:
        dict: {"success": bool, "response": dict или "error": str}
    """
    if status not in ["active", "blocked"]:
        error_msg = f"Неверный статус '{status}'. Допустимые значения: 'active', 'blocked'"
        logger.error(f"❌ {error_msg}")
        return {"success": False, "error": error_msg}
    
    url = f"{base_url}/ad_plans/{campaign_id}.json"
    data = {"status": status}
    
    try:
        status_emoji = "▶️" if status == "active" else "⏸️"
        action = "включаем" if status == "active" else "блокируем"
        logger.info(f"{status_emoji} {action.capitalize()} кампанию {campaign_id} (→ {status})")
        
        response = requests.post(url, headers=_headers(token), json=data, timeout=20)
        
        if response.status_code in (200, 204):
            logger.info(f"✅ Кампания {campaign_id} успешно изменена на '{status}' (HTTP {response.status_code})")
            try:
                resp_json = response.json()
            except Exception:
                resp_json = None
            return {"success": True, "response": resp_json}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка при изменении статуса кампании {campaign_id}: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка при изменении статуса кампании {campaign_id}: {error_msg}")
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
                error_text = r.text[:200]
                logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке групп: {error_text}")
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


def get_ad_groups_all(token: str, base_url: str, fields: str = "id,name,status", limit: int = 200, include_deleted: bool = False):
    """
    Загружает все группы объявлений (ad_groups) - активные и отключенные.
    По умолчанию НЕ включает удалённые группы.
    
    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        fields: Поля для загрузки
        limit: Лимит на запрос
        include_deleted: Включать ли удалённые группы (по умолчанию False)
    
    Returns:
        list: Список всех групп (активных + отключенных)
    """
    url = f"{base_url}/ad_groups.json"
    offset = 0
    items_all = []
    
    # Получаем активные и отключенные группы отдельно
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
                    logger.error(f"❌ Ошибка HTTP {r.status_code} при загрузке групп (status={status}): {error_text}")
                    raise RuntimeError(f"[ad_groups] HTTP {r.status_code}: {r.text}")
                
                payload = r.json()
                items = payload.get("items", [])
                items_all.extend(items)
                
                logger.debug(f"   Загружено {len(items)} групп со статусом '{status}' (offset={offset})")
                
                if len(items) < limit:
                    break
                    
                offset += limit
                time.sleep(0.25)
                
            except requests.RequestException as e:
                logger.error(f"❌ Ошибка сети при загрузке групп (status={status}): {e}")
                raise
    
    logger.info(f"📊 Всего загружено {len(items_all)} групп (активных + отключенных)")
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


# ===== Scaling / Duplication Functions =====

def get_campaign_full(token: str, base_url: str, campaign_id: int):
    """Получает полные данные кампании"""
    url = f"{base_url}/ad_plans/{campaign_id}.json"

    try:
        response = _request_with_retries("GET", url, headers=_headers(token), timeout=20)

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка загрузки кампании {campaign_id}: {error_msg}")
            return None

        return response.json()

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при загрузке кампании {campaign_id}: {e}")
        return None


def get_ad_group_full(token: str, base_url: str, group_id: int):
    """Получает полные данные группы объявлений со всеми полями"""
    url = f"{base_url}/ad_groups/{group_id}.json"

    # Запрашиваем все важные поля (только разрешённые API, без read-only полей)
    params = {
        "fields": "id,name,package_id,ad_plan_id,objective,status,age_restrictions,targetings,budget_limit,budget_limit_day,autobidding_mode,pricelist_id,date_start,date_end,utm,enable_utm,enable_recombination,enable_offline_goals,price,max_price"
    }

    try:
        response = _request_with_retries("GET", url, headers=_headers(token), params=params, timeout=20)

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка загрузки группы {group_id}: {error_msg}")
            return None

        return response.json()

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при загрузке группы {group_id}: {e}")
        return None


def get_banners_by_ad_group(token: str, base_url: str, ad_group_id: int, include_stopped: bool = True):
    """
    Получает все НЕудалённые объявления из группы

    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        ad_group_id: ID группы объявлений
        include_stopped: Включать остановленные объявления

    Returns:
        list: Список объявлений (активные + остановленные, без удалённых)
    """
    # VK Ads API v2: GET /banners.json с фильтром по группе
    url = f"{base_url}/banners.json"
    offset = 0
    limit = 200
    all_banners = []

    while True:
        params = {
            "limit": limit,
            "offset": offset,
            # Фильтр по группе объявлений
            "_ad_group_id": ad_group_id,
            # Запрашиваем все writable поля согласно документации VK Ads API
            "fields": "id,name,status,ad_group_id,content,textblocks,urls"
        }

        try:
            logger.info(f"📥 Загружаем объявления группы {ad_group_id}: GET {url} с фильтром _ad_group_id={ad_group_id}")
            response = requests.get(url, headers=_headers(token), params=params, timeout=20)

            if response.status_code != 200:
                error_text = response.text[:500] if response.text else 'empty'
                logger.error(f"❌ Ошибка загрузки объявлений группы {ad_group_id}: HTTP {response.status_code} - {error_text}")
                break

            data = response.json()
            items = data.get("items", [])
            logger.info(f"📋 Группа {ad_group_id}: получено {len(items)} объявлений (offset={offset})")
            
            # Фильтруем: убираем удалённые
            for banner in items:
                is_deleted = banner.get("deleted", False)
                banner_status = banner.get("status", "unknown")
                
                if is_deleted or banner_status == "deleted":
                    continue
                
                # Если не включаем остановленные - пропускаем их
                if not include_stopped and banner_status in ["blocked", "stopped"]:
                    continue
                
                all_banners.append(banner)
            
            if len(items) < limit:
                break
            
            offset += limit
            time.sleep(0.1)  # Rate limiting
            
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка сети при загрузке объявлений группы {ad_group_id}: {e}")
            break
    
    return all_banners


def create_ad_group(token: str, base_url: str, group_data: dict):
    """Создаёт новую группу объявлений"""
    url = f"{base_url}/ad_groups.json"
    
    try:
        response = requests.post(url, headers=_headers(token), json=group_data, timeout=30)
        
        if response.status_code in (200, 201):
            result = response.json()
            logger.info(f"✅ Группа создана: ID={result.get('id')}")
            return {"success": True, "data": result}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка создания группы: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка создания группы: {error_msg}")
        return {"success": False, "error": error_msg}


def create_banner(token: str, base_url: str, banner_data: dict):
    """Создаёт новое объявление в группе"""
    ad_group_id = banner_data.get('ad_group_id')
    if not ad_group_id:
        return {"success": False, "error": "ad_group_id is required"}
    
    # VK Ads API v2: POST /ad_groups/{ad_group_id}/banners.json
    url = f"{base_url}/ad_groups/{ad_group_id}/banners.json"
    
    # Убираем ad_group_id из данных - он уже в URL
    data_to_send = {k: v for k, v in banner_data.items() if k != 'ad_group_id'}
    
    print(f"   🔄 Создаём баннер: POST {url}")
    print(f"   📋 Данные: {data_to_send}")
    
    try:
        response = requests.post(url, headers=_headers(token), json=data_to_send, timeout=30)
        
        print(f"   📥 Ответ: {response.status_code} - {response.text[:500] if response.text else 'empty'}")
        
        if response.status_code in (200, 201):
            result = response.json()
            logger.info(f"✅ Объявление создано: ID={result.get('id')}")
            return {"success": True, "data": result}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка создания объявления: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка создания объявления: {error_msg}")
        return {"success": False, "error": error_msg}


def update_ad_group(token: str, base_url: str, group_id: int, update_data: dict):
    """Обновляет группу объявлений"""
    url = f"{base_url}/ad_groups/{group_id}.json"
    
    try:
        response = requests.post(url, headers=_headers(token), json=update_data, timeout=20)
        
        if response.status_code in (200, 204):
            try:
                result = response.json()
            except:
                result = {}
            logger.info(f"✅ Группа {group_id} обновлена")
            return {"success": True, "data": result}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Ошибка обновления группы {group_id}: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except requests.RequestException as e:
        error_msg = f"Сетевая ошибка: {str(e)}"
        logger.error(f"❌ Ошибка обновления группы {group_id}: {error_msg}")
        return {"success": False, "error": error_msg}


def _generate_copy_name(original_name: str) -> str:
    """
    Генерирует имя для копии группы.
    Если имя уже содержит "(копия)", добавляет номер.

    Примеры:
        "Группа 1" -> "Группа 1 (копия)"
        "Группа 1 (копия)" -> "Группа 1 (копия 2)"
        "Группа 1 (копия 2)" -> "Группа 1 (копия 3)"
    """
    import re

    if not original_name:
        return "Копия"

    # Проверяем паттерн "(копия N)" в конце
    pattern_numbered = r'^(.+?)\s*\(копия\s+(\d+)\)\s*$'
    match_numbered = re.match(pattern_numbered, original_name, re.IGNORECASE)

    if match_numbered:
        base_name = match_numbered.group(1).strip()
        current_num = int(match_numbered.group(2))
        return f"{base_name} (копия {current_num + 1})"

    # Проверяем паттерн "(копия)" без номера
    pattern_simple = r'^(.+?)\s*\(копия\)\s*$'
    match_simple = re.match(pattern_simple, original_name, re.IGNORECASE)

    if match_simple:
        base_name = match_simple.group(1).strip()
        return f"{base_name} (копия 2)"

    # Обычное имя - добавляем "(копия)"
    return f"{original_name} (копия)"


# Минимальный дневной бюджет VK Ads (100 рублей)
VK_MIN_DAILY_BUDGET = 100


def duplicate_ad_group_full(
    token: str,
    base_url: str,
    ad_group_id: int,
    new_name: str = None,
    new_budget: float = None,
    auto_activate: bool = False,
    rate_limit_delay: float = 0.03
):
    """
    Полное дублирование рекламной группы со всеми НЕудалёнными объявлениями.
    Использует метод создания группы с баннерами в одном запросе (POST /ad_groups.json с полем banners).

    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        ad_group_id: ID группы для дублирования
        new_name: Новое имя группы. Если None или пустая строка - используется ОРИГИНАЛЬНОЕ имя.
        new_budget: Новый бюджет группы в рублях. Если None или 0 - копируется бюджет оригинала.
        auto_activate: Автоматически активировать группу и объявления
        rate_limit_delay: Задержка между запросами (по умолчанию 0.03 сек = ~33 req/sec)

    Returns:
        dict: {
            "success": bool,
            "new_ad_group_id": int,
            "duplicated_banners": [...],
            "skipped_banners": [...],
            "errors": [...]
        }
    """
    # Поля которые НЕ копируем (read-only или статистика)
    EXCLUDED_GROUP_FIELDS = {
        'id', 'created', 'updated', 'created_at', 'updated_at', 'deleted',
        'statistics', 'clicks', 'shows', 'spent', 'ctr',
        'conversions', 'cost_per_conversion', 'impressions',
        'banner_count', 'banners', 'delivery', 'issues', 'read_only',
        'interface_read_only', 'user_id', 'stats_info', 'learning_progress',
        'efficiency_status', 'vkads_status', 'or_status', 'or_migrated',
        'budget_limit_day', 'budget_limit', 'budget_limit_per_day'  # Не копируем, устанавливаем отдельно
    }

    # Исключаемые поля баннеров (read-only согласно документации VK Ads)
    EXCLUDED_BANNER_FIELDS = {
        'id', 'ad_group_id', 'created', 'updated', 'created_at', 'updated_at',
        'moderation_status', 'moderation_reasons', 'delivery', 'deleted',
        'issues', 'ord_marker', 'user_id', 'read_only', 'interface_read_only',
        # Статистика
        'clicks', 'shows', 'spent', 'ctr', 'conversions',
        'cost_per_conversion', 'impressions',
        # Другие read-only поля
        'stats_info', 'preview_url', 'audit_pixels',
        # Поле status - убираем, т.к. при создании группы с баннерами статус наследуется от группы
        'status', 'name'
    }

    def clean_content(content_data):
        """Очищает content, оставляя только id медиа-объектов"""
        if not content_data:
            return None
        cleaned = {}
        for key, value in content_data.items():
            if isinstance(value, dict) and 'id' in value:
                # Для медиа-объектов оставляем только id
                cleaned[key] = {'id': value['id']}
        return cleaned if cleaned else None

    def clean_urls(urls_data):
        """Очищает urls, оставляя только id"""
        if not urls_data:
            return None
        cleaned = {}
        for key, value in urls_data.items():
            if isinstance(value, dict) and 'id' in value:
                cleaned[key] = {'id': value['id']}
        return cleaned if cleaned else None

    try:
        print(f"")
        print(f"{'='*80}")
        print(f"🎯 ДУБЛИРОВАНИЕ ГРУППЫ {ad_group_id}")
        print(f"{'='*80}")

        # ===== ШАГ 1: Загружаем данные группы =====
        print(f"📥 Шаг 1/2: Загружаем данные группы и объявлений...")
        original_group = get_ad_group_full(token, base_url, ad_group_id)

        if not original_group:
            return {"success": False, "error": "Не удалось загрузить группу"}

        print(f"✅ Загружена группа: {original_group.get('name', 'Unknown')}")

        time.sleep(rate_limit_delay)

        # Загружаем объявления группы
        banners = get_banners_by_ad_group(token, base_url, ad_group_id, include_stopped=True)
        print(f"✅ Найдено {len(banners)} объявлений для копирования")

        # Копируем все поля группы кроме исключённых
        new_group_data = {}
        for key, value in original_group.items():
            if key not in EXCLUDED_GROUP_FIELDS and value is not None:
                new_group_data[key] = value

        # Если objective отсутствует, получаем его из кампании (ad_plan)
        if 'objective' not in new_group_data or not new_group_data.get('objective'):
            campaign_id = original_group.get('ad_plan_id') or original_group.get('campaign_id')
            print(f"⚠️ objective не найден в группе, ищем в кампании {campaign_id}")
            if campaign_id:
                time.sleep(rate_limit_delay)
                campaign = get_campaign_full(token, base_url, campaign_id)
                if campaign and campaign.get('objective'):
                    new_group_data['objective'] = campaign['objective']
                    print(f"✅ Получен objective: {campaign['objective']}")

        # Изменяем имя
        # Если new_name указан и не пустой - используем его
        # Если new_name пустой или None - используем ОРИГИНАЛЬНОЕ имя группы
        if new_name and new_name.strip():
            new_group_data['name'] = new_name.strip()
        else:
            # Используем оригинальное имя группы
            new_group_data['name'] = original_group.get('name', 'Копия')

        # Устанавливаем бюджет
        budget_to_set = None
        if new_budget is not None and new_budget > 0:
            if new_budget >= VK_MIN_DAILY_BUDGET:
                budget_to_set = int(new_budget)
                logger.info(f"💰 Установлен новый дневной бюджет: {budget_to_set} руб")
        else:
            original_budget = original_group.get('budget_limit_day')
            if original_budget:
                try:
                    budget_int = int(float(original_budget))
                    if budget_int >= VK_MIN_DAILY_BUDGET:
                        budget_to_set = budget_int
                        logger.info(f"💰 Скопирован бюджет из оригинала: {budget_int} руб")
                except (ValueError, TypeError):
                    pass

        if budget_to_set is not None:
            new_group_data['budget_limit_day'] = str(budget_to_set)

        # ВАЖНО: Всегда создаём группу со статусом 'blocked', чтобы обойти лимит активных баннеров
        # Если нужна автоактивация - активируем после создания
        new_group_data['status'] = 'blocked'

        # ===== ШАГ 2: Подготавливаем баннеры для создания вместе с группой =====
        banners_for_create = []
        original_banner_info = []  # Для отслеживания оригинальных ID

        for banner in banners:
            banner_id = banner.get('id')
            banner_name = banner.get('name', 'Unknown')

            # Копируем поля баннера
            new_banner_data = {}
            for key, value in banner.items():
                if key not in EXCLUDED_BANNER_FIELDS and value is not None:
                    new_banner_data[key] = value

            # Очищаем content - оставляем только id
            if 'content' in new_banner_data:
                cleaned_content = clean_content(new_banner_data['content'])
                if cleaned_content:
                    new_banner_data['content'] = cleaned_content
                else:
                    del new_banner_data['content']

            # Очищаем urls - оставляем только id
            if 'urls' in new_banner_data:
                cleaned_urls = clean_urls(new_banner_data['urls'])
                if cleaned_urls:
                    new_banner_data['urls'] = cleaned_urls
                else:
                    del new_banner_data['urls']

            print(f"   📋 Баннер {banner_id}: content={new_banner_data.get('content')}, urls={new_banner_data.get('urls')}, textblocks={list(new_banner_data.get('textblocks', {}).keys()) if new_banner_data.get('textblocks') else None}")

            banners_for_create.append(new_banner_data)
            original_banner_info.append({
                "original_id": banner_id,
                "name": banner_name
            })

        # Добавляем баннеры в данные группы
        if banners_for_create:
            new_group_data['banners'] = banners_for_create
            print(f"📋 Подготовлено {len(banners_for_create)} баннеров для создания вместе с группой")

        # ===== Создаём группу с баннерами в одном запросе =====
        print(f"🔄 Шаг 2/2: Создаём группу с баннерами (статус: blocked)...")
        logger.info(f"📋 Настройки новой группы:")
        logger.info(f"   • Название: {new_group_data['name']}")
        logger.info(f"   • Статус: blocked (для обхода лимита активных баннеров)")
        logger.info(f"   • Автоактивация после создания: {auto_activate}")
        logger.info(f"   • Objective: {new_group_data.get('objective', 'NOT SET')}")
        logger.info(f"   • Баннеров: {len(banners_for_create)}")

        time.sleep(rate_limit_delay)

        create_result = create_ad_group(token, base_url, new_group_data)

        if not create_result.get("success"):
            return {"success": False, "error": create_result.get("error", "Ошибка создания группы")}

        new_group_id = create_result["data"].get("id")
        created_banners = create_result["data"].get("banners", [])

        logger.info(f"✅ Группа создана! ID: {new_group_id}")
        logger.info(f"✅ Создано баннеров: {len(created_banners)}")

        # Финальный статус (может измениться после активации)
        final_status = 'blocked'

        # Если нужна автоактивация - активируем группу после создания
        if auto_activate:
            logger.info(f"🔄 Активируем группу {new_group_id}...")
            time.sleep(rate_limit_delay)
            activate_result = update_ad_group(token, base_url, new_group_id, {"status": "active"})
            if activate_result.get("success"):
                final_status = 'active'
                logger.info(f"✅ Группа {new_group_id} активирована")
            else:
                error_text = str(activate_result.get('error', 'Unknown error'))[:100]
                logger.warning(f"⚠️ Не удалось активировать группу: {error_text}")

        # Формируем результат
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
        
        # ===== ИТОГИ =====
        logger.info(f"")
        logger.info(f"{'='*80}")
        logger.info(f"✅ ДУБЛИРОВАНИЕ ЗАВЕРШЕНО")
        logger.info(f"{'='*80}")
        logger.info(f"Исходная группа: {ad_group_id} - {original_group.get('name')}")
        logger.info(f"Новая группа: {new_group_id} - {new_group_data['name']}")
        logger.info(f"Скопировано объявлений: {len(duplicated_banners)}/{len(banners)}")
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
        error_msg = f"Неожиданная ошибка: {str(e)}"
        logger.error(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": error_msg}


def get_ad_groups_with_stats(token: str, base_url: str, date_from: str, date_to: str, limit: int = 200, include_blocked: bool = True):
    """
    Получает группы объявлений со статистикой за период
    
    Args:
        token: VK Ads API токен
        base_url: Базовый URL VK Ads API
        date_from: Начало периода (YYYY-MM-DD)
        date_to: Конец периода (YYYY-MM-DD)
        limit: Лимит на запрос
        include_blocked: Включать ли отключенные группы (по умолчанию True)
    
    Returns:
        list: Список групп со статистикой
    """
    # Получаем группы: активные + отключенные (кроме удалённых)
    # Используем только валидные поля VK API (day_limit не поддерживается, используем budget_limit_day)
    if include_blocked:
        groups = get_ad_groups_all(token, base_url, fields="id,name,status,budget_limit_day", limit=limit, include_deleted=False)
    else:
        groups = get_ad_groups_active(token, base_url, fields="id,name,status,budget_limit_day", limit=limit)

    if not groups:
        return []

    # Дополнительно фильтруем deleted группы (на случай если API вернул их)
    groups = [g for g in groups if g.get('status') != 'deleted']

    if not groups:
        return []

    group_ids = [g['id'] for g in groups]

    logger.info(f"📊 Получаем статистику для {len(group_ids)} групп за период {date_from} — {date_to}")

    # Получаем статистику по группам С БАТЧИРОВАНИЕМ
    # Чтобы избежать ошибки 414 (Request-URI Too Large) при большом количестве групп
    stats_url = f"{base_url}/statistics/ad_groups/day.json"
    STATS_BATCH_SIZE = 100  # Максимум групп в одном запросе

    all_stats_data = []

    try:
        # Разбиваем на батчи для избежания 414 ошибки
        total_batches = (len(group_ids) + STATS_BATCH_SIZE - 1) // STATS_BATCH_SIZE
        logger.info(f"📦 Разбиваем {len(group_ids)} групп на {total_batches} батчей по {STATS_BATCH_SIZE}")

        for batch_num, i in enumerate(range(0, len(group_ids), STATS_BATCH_SIZE), 1):
            batch_ids = group_ids[i:i + STATS_BATCH_SIZE]

            params = {
                "date_from": date_from,
                "date_to": date_to,
                "metrics": "base",
                "id": ",".join(map(str, batch_ids))
            }

            logger.info(f"   📊 Батч {batch_num}/{total_batches}: запрашиваем статистику для {len(batch_ids)} групп...")

            response = requests.get(stats_url, headers=_headers(token), params=params, timeout=30)

            if response.status_code == 414:
                # URL слишком длинный - попробуем меньший батч
                logger.warning(f"⚠️ Батч {batch_num}: URL слишком длинный для {len(batch_ids)} групп, пробуем по 50")
                for sub_i in range(0, len(batch_ids), 50):
                    sub_batch = batch_ids[sub_i:sub_i + 50]
                    params["id"] = ",".join(map(str, sub_batch))
                    sub_response = requests.get(stats_url, headers=_headers(token), params=params, timeout=30)
                    if sub_response.status_code == 200:
                        sub_data = sub_response.json().get("items", [])
                        all_stats_data.extend(sub_data)
                    else:
                        logger.error(f"❌ Ошибка при под-батче: HTTP {sub_response.status_code}")
                continue

            if response.status_code != 200:
                error_text = response.text[:300]
                logger.error(f"❌ Ошибка получения статистики батча {batch_num}: HTTP {response.status_code}, Response: {error_text}")
                continue

            batch_stats = response.json().get("items", [])
            all_stats_data.extend(batch_stats)
            logger.info(f"   ✅ Батч {batch_num}: получено {len(batch_stats)} записей")

            # Небольшая пауза между батчами чтобы не превысить rate limit
            if batch_num < total_batches:
                time.sleep(0.1)

        stats_data = all_stats_data
        logger.info(f"📊 Всего получено {len(stats_data)} записей статистики от VK API")

        # Логируем первую запись для отладки
        if stats_data and len(stats_data) > 0:
            logger.info(f"🔍 Пример первой записи статистики: {str(stats_data[0])[:500]}")

        # Агрегируем статистику по группам
        # Используем такую же логику как для баннеров в get_banners_stats_day
        stats_by_group = {}
        for item in stats_data:
            gid = item.get("id")
            if gid is None:
                continue

            # Получаем total.base — агрегированные данные за весь период
            total = item.get("total", {})
            base = total.get("base", {}) if isinstance(total, dict) else {}

            # VK goals находятся в total.base.vk.goals
            vk_data = base.get("vk", {}) if isinstance(base.get("vk"), dict) else {}
            vk_goals = float(vk_data.get("goals", 0) or 0)

            # Дополнительное логирование для отладки (только для первой группы)
            if gid and gid == stats_data[0].get("id") and (base or item.get("rows")):
                logger.info(f"🔍 Детальная структура данных для группы {gid}:")
                logger.info(f"   total keys: {list(total.keys()) if isinstance(total, dict) else 'not dict'}")
                logger.info(f"   base keys: {list(base.keys()) if isinstance(base, dict) else 'not dict'}")
                logger.info(f"   base content: {base}")
                logger.info(f"   vk_data: {vk_data}")
                logger.info(f"   vk_goals из total.base.vk.goals: {vk_goals}")
                if item.get("rows"):
                    logger.info(f"   rows (первые 2): {item.get('rows')[:2]}")
            
            # Основные метрики
            spent = float(base.get("spent", 0) or 0)
            shows = float(base.get("impressions", 0) or 0)  # VK API использует 'impressions'
            clicks = float(base.get("clicks", 0) or 0)
            
            # Если total.base пустой, пробуем агрегировать из rows
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
            
            logger.debug(f"   Группа {gid}: spent={spent:.2f}, shows={shows}, clicks={clicks}, goals={vk_goals}")
        
        # Объединяем группы со статистикой
        for group in groups:
            gid = group["id"]
            if gid in stats_by_group:
                group["stats"] = stats_by_group[gid]
                
                # Вычисляем стоимость результата
                goals = stats_by_group[gid]["goals"]
                spent = stats_by_group[gid]["spent"]
                
                if goals > 0:
                    group["stats"]["cost_per_goal"] = spent / goals
                else:
                    group["stats"]["cost_per_goal"] = None
                    
                logger.info(f"   📋 Группа {gid} ({group.get('name', 'Unknown')}): "
                           f"spent={spent:.2f}₽, goals={goals}, cost_per_goal={group['stats']['cost_per_goal']}")
            else:
                group["stats"] = {
                    "spent": 0,
                    "shows": 0,
                    "clicks": 0,
                    "goals": 0,
                    "cost_per_goal": None
                }
                logger.debug(f"   📋 Группа {gid}: нет статистики")
        
        return groups
        
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка сети при получении статистики: {e}")
        return groups
