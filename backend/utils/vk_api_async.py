"""
Асинхронная версия VK Ads API клиента.
Использует aiohttp для параллельных HTTP запросов.

Кабинеты обрабатываются полностью параллельно.
Внутри каждого кабинета батчи обрабатываются последовательно.
"""
import asyncio
import aiohttp
from utils.logging_setup import get_logger

logger = get_logger(service="vk_api")

# Константы для ретраев
API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 3  # Уменьшено до 3 секунд
API_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _request_with_retries(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    max_retries: int = API_MAX_RETRIES,
    retry_delay: int = API_RETRY_DELAY_SECONDS,
    **kwargs,
) -> aiohttp.ClientResponse:
    """
    Асинхронная обёртка с ретраями по временным ошибкам:
    429, 500, 502, 503, 504 + сетевые ошибки.
    """
    attempt = 0

    while True:
        attempt += 1
        try:
            resp = await session.request(method, url, **kwargs)
        except aiohttp.ClientError as e:
            if attempt > max_retries:
                logger.error(
                    f"❌ {method} {url} — сетевая ошибка после {attempt} попыток: {e}"
                )
                raise

            wait = min(1 + attempt, 3)
            logger.warning(
                f"⚠️ {method} {url} — сетевая ошибка: {e}. "
                f"Пауза {wait} сек перед повтором ({attempt}/{max_retries})"
            )
            await asyncio.sleep(wait)
            continue

        # Временные/лимитные статусы — ждём и ретраим
        if resp.status in API_RETRY_STATUS_CODES:
            response_text = await resp.text()

            if attempt > max_retries:
                logger.error(
                    f"❌ {method} {url} — HTTP {resp.status} после {attempt} попыток.\n"
                    f"   Тело ответа: {response_text[:200]}"
                )
                raise RuntimeError(
                    f"HTTP {resp.status} после {attempt} попыток: {response_text[:200]}"
                )

            # 429 Too Many Requests
            if resp.status == 429:
                wait = 3  # VK API statistics endpoint limit is 2 RPS, quick recovery
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(wait, int(retry_after))
                    except ValueError:
                        pass

                logger.warning(
                    f"⚠️ {method} {url} — лимит запросов (429). "
                    f"Ждём {wait} сек и повторяем ({attempt}/{max_retries})"
                )
                await asyncio.sleep(wait)
            else:
                wait = min(10 + attempt * 5, retry_delay)
                logger.warning(
                    f"⚠️ {method} {url} — временная ошибка HTTP {resp.status}. "
                    f"Ждём {wait} сек и повторяем ({attempt}/{max_retries})"
                )
                await asyncio.sleep(wait)

            continue

        if attempt > 1:
            logger.info(f"✅ {method} {url} — успешно восстановлено после {attempt-1} попыток")
        return resp


async def get_banners_active(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    fields: str = "id,name,status,delivery,ad_group_id,moderation_status",
    limit: int = 200,
    sleep_between_calls: float = 0.25,
) -> list[dict]:
    """
    Загружаем все активные объявления (banners) асинхронно.
    """
    logger.info("🔄 Начинаем загрузку рекламных объявлений (banners) из VK Ads API")

    url = f"{base_url}/banners.json"
    offset = 0
    items_all: list[dict] = []
    page_num = 1

    while True:
        params = {
            "fields": fields,
            "limit": limit,
            "offset": offset,
            "_status": "active",
            "_ad_group_status": "active",
        }

        resp = await _request_with_retries(
            session,
            "GET",
            url,
            headers=_headers(token),
            params=params,
            timeout=aiohttp.ClientTimeout(total=20),
        )

        if resp.status != 200:
            text = await resp.text()
            error_text = text[:200]
            logger.error(f"❌ Ошибка HTTP {resp.status} при загрузке объявлений: {error_text}")
            raise RuntimeError(f"[banners] HTTP {resp.status}: {text}")

        payload = await resp.json()
        items = payload.get("items", [])
        items_all.extend(items)

        logger.debug(f"✓ Страница {page_num}: получено {len(items)} объявлений (всего {len(items_all)})")

        if len(items) < limit:
            break

        offset += limit
        page_num += 1
        await asyncio.sleep(sleep_between_calls)

    logger.info(f"✅ Загружено {len(items_all)} активных объявлений за {page_num} страниц")
    return items_all


async def get_banners_stats_day(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    date_from: str,
    date_to: str,
    banner_ids: list | None = None,
    metrics: str = "base",
    batch_size: int = 200,  # VK API max is ~250
    sleep_between_calls: float = 0.6,  # VK API statistics limit is 2 RPS
) -> dict:
    """
    Получает статистику по объявлениям асинхронно.
    Возвращает словарь: { banner_id: {"spent": float, "clicks": float, "shows": float, "vk_goals": int} }

    УСТАРЕВШИЙ метод - загружает всю статистику сразу.
    Для потоковой обработки используйте get_banners_stats_batched().
    """
    if banner_ids:
        logger.info(
            f"📊 Запрашиваем статистику за период {date_from} — {date_to} "
            f"для {len(banner_ids)} активных объявлений"
        )
    else:
        logger.info(
            f"📊 Запрашиваем статистику за период {date_from} — {date_to} для всех объявлений"
        )

    url = f"{base_url}/statistics/banners/day.json"
    aggregated_stats: dict = {}

    async def _one_request(ids_chunk: list | None) -> list[dict]:
        params = {
            "date_from": date_from,
            "date_to": date_to,
            "metrics": metrics,
        }
        if ids_chunk:
            params["id"] = ",".join(str(i) for i in ids_chunk)

        resp = await _request_with_retries(
            session,
            "GET",
            url,
            headers=_headers(token),
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        )

        if resp.status != 200:
            text = await resp.text()
            error_text = text[:200]
            logger.error(f"❌ Ошибка HTTP {resp.status} при загрузке статистики: {error_text}")
            raise RuntimeError(f"[stats day] HTTP {resp.status}: {text}")

        payload = await resp.json()
        return payload.get("items", [])

    def _aggregate_batch(items: list[dict]) -> None:
        """Агрегирует статистику из батча в общий словарь"""
        for item in items:
            bid = item.get("id")
            if bid is None:
                continue

            total = item.get("total", {}).get("base", {})
            vk_data = total.get("vk", {}) if isinstance(total.get("vk"), dict) else {}
            vk_goals = vk_data.get("goals", 0.0)

            aggregated_stats[bid] = {
                "spent": float(total.get("spent", 0.0)),
                "clicks": float(total.get("clicks", 0.0)),
                "shows": float(total.get("impressions", 0.0)),
                "vk_goals": float(vk_goals)
            }

    # Если id нет или их мало — один запрос
    if not banner_ids or len(banner_ids) <= batch_size:
        items = await _one_request(banner_ids)
        _aggregate_batch(items)
        logger.info(f"✅ Обработано {len(aggregated_stats)} объявлений")
    else:
        # Разбиваем на батчи и обрабатываем ПОСЛЕДОВАТЕЛЬНО с паузой
        # (VK API имеет строгий rate limit)
        total = len(banner_ids)
        num_batches = (total + batch_size - 1) // batch_size
        logger.info(f"🔁 Разбиваем {total} объявлений на {num_batches} батчей по {batch_size}")

        for batch_num, start in enumerate(range(0, total, batch_size), 1):
            chunk = banner_ids[start:start + batch_size]

            try:
                items = await _one_request(chunk)
                _aggregate_batch(items)
                logger.info(
                    f"  ✓ Батч {batch_num}/{num_batches}: обработано {len(items)} записей "
                    f"(всего: {len(aggregated_stats)})"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка в батче {batch_num}: {e}")
                logger.exception("Batch error traceback:")

            # Пауза между батчами для соблюдения rate limit
            if batch_num < num_batches:
                await asyncio.sleep(sleep_between_calls)

    logger.info(f"✅ Итого агрегировано статистики для {len(aggregated_stats)} объявлений")
    return aggregated_stats


async def get_banners_stats_batched(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    date_from: str,
    date_to: str,
    banner_ids: list,
    banners_info: dict[int, dict],
    metrics: str = "base",
    batch_size: int = 200,  # VK API max is ~250
    sleep_between_calls: float = 0.6,  # VK API statistics limit is 2 RPS
):
    """
    Асинхронный генератор: загружает статистику батчами и yield'ит каждый батч.

    Преимущества:
    - Равномерная нагрузка на сервер (нет пиков)
    - Меньше памяти (не хранит все данные сразу)
    - Можно начинать обработку сразу после первого батча

    Args:
        session: aiohttp сессия
        token: API токен
        base_url: базовый URL API
        date_from: начало периода
        date_to: конец периода
        banner_ids: список ID баннеров
        banners_info: словарь {banner_id: banner_data} с информацией о баннерах
        metrics: тип метрик
        batch_size: размер батча
        sleep_between_calls: пауза между запросами

    Yields:
        dict с ключами:
            - batch_num: номер батча
            - total_batches: всего батчей
            - banners: список баннеров с данными и статистикой
            - stats_map: словарь {banner_id: stats} для этого батча
    """
    if not banner_ids:
        logger.info("📊 Нет объявлений для загрузки статистики")
        return

    url = f"{base_url}/statistics/banners/day.json"
    total = len(banner_ids)
    num_batches = (total + batch_size - 1) // batch_size

    logger.info(f"📊 Потоковая загрузка статистики за {date_from} — {date_to}")
    logger.info(f"🔁 {total} объявлений → {num_batches} батчей по {batch_size}")

    async def _fetch_batch_stats(ids_chunk: list) -> dict:
        """Загружает статистику для одного батча"""
        params = {
            "date_from": date_from,
            "date_to": date_to,
            "metrics": metrics,
            "id": ",".join(str(i) for i in ids_chunk)
        }

        resp = await _request_with_retries(
            session,
            "GET",
            url,
            headers=_headers(token),
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        )

        if resp.status != 200:
            text = await resp.text()
            error_text = text[:200]
            logger.error(f"❌ Ошибка HTTP {resp.status} при загрузке статистики: {error_text}")
            raise RuntimeError(f"[stats day] HTTP {resp.status}: {text}")

        payload = await resp.json()
        items = payload.get("items", [])

        # Преобразуем в словарь
        stats_map = {}
        for item in items:
            bid = item.get("id")
            if bid is None:
                continue

            total_stats = item.get("total", {}).get("base", {})
            vk_data = total_stats.get("vk", {}) if isinstance(total_stats.get("vk"), dict) else {}
            vk_goals = vk_data.get("goals", 0.0)

            stats_map[bid] = {
                "spent": float(total_stats.get("spent", 0.0)),
                "clicks": float(total_stats.get("clicks", 0.0)),
                "shows": float(total_stats.get("impressions", 0.0)),
                "vk_goals": float(vk_goals)
            }

        return stats_map

    processed_total = 0

    for batch_num, start in enumerate(range(0, total, batch_size), 1):
        chunk_ids = banner_ids[start:start + batch_size]

        try:
            # Загружаем статистику для батча
            stats_map = await _fetch_batch_stats(chunk_ids)

            # Собираем баннеры с их статистикой
            banners_with_stats = []
            for bid in chunk_ids:
                banner_info = banners_info.get(bid, {})
                stats = stats_map.get(bid, {"spent": 0.0, "clicks": 0.0, "shows": 0.0, "vk_goals": 0.0})

                banners_with_stats.append({
                    **banner_info,
                    "id": bid,
                    "spent": stats["spent"],
                    "clicks": stats["clicks"],
                    "shows": stats["shows"],
                    "vk_goals": stats["vk_goals"],
                })

            processed_total += len(chunk_ids)

            logger.info(
                f"  ✓ Батч {batch_num}/{num_batches}: загружено {len(stats_map)} записей "
                f"(всего: {processed_total}/{total})"
            )

            yield {
                "batch_num": batch_num,
                "total_batches": num_batches,
                "banners": banners_with_stats,
                "stats_map": stats_map,
                "processed_total": processed_total,
                "total_banners": total
            }

        except Exception as e:
            logger.error(f"❌ Ошибка в батче {batch_num}: {e}")
            logger.exception("Batch error traceback:")
            # Продолжаем со следующим батчем
            continue

        # Пауза между батчами для соблюдения rate limit
        if batch_num < num_batches:
            await asyncio.sleep(sleep_between_calls)

    logger.info(f"✅ Потоковая загрузка завершена: обработано {processed_total} объявлений")


async def disable_banners_mass_action(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    banner_ids: list[int],
    dry_run: bool = True,
) -> dict:
    """
    Массовое отключение баннеров через /banners/mass_action.json (до 200 за раз).

    Это намного эффективнее чем отключать по одному - один запрос вместо N.
    """
    if not banner_ids:
        return {"success": True, "disabled": 0, "banner_ids": []}

    if dry_run:
        logger.info(
            f"🧪 [DRY RUN] {len(banner_ids)} баннеров помечены как убыточные — "
            f"в реальном режиме были бы отключены"
        )
        return {"success": True, "dry_run": True, "disabled": len(banner_ids), "banner_ids": banner_ids}

    url = f"{base_url}/banners/mass_action.json"

    # Формируем тело запроса: [{"id": 123, "status": "blocked"}, ...]
    payload = [{"id": bid, "status": "blocked"} for bid in banner_ids]

    try:
        resp = await _request_with_retries(
            session,
            "POST",
            url,
            headers=_headers(token),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),  # Дольше для массовой операции
        )
    except Exception as e:
        logger.error(f"❌ Ошибка сети при массовом отключении {len(banner_ids)} баннеров: {e}")
        return {"success": False, "error": str(e), "banner_ids": banner_ids}

    # 204 No Content = успех
    if resp.status == 204:
        logger.info(f"✅ Массово отключено {len(banner_ids)} баннеров за 1 запрос")
        return {"success": True, "disabled": len(banner_ids), "banner_ids": banner_ids}

    # Обработка ошибок
    text = await resp.text()
    error_text = text[:500]
    logger.error(f"❌ Ошибка HTTP {resp.status} при массовом отключении: {error_text}")
    return {"success": False, "error": f"HTTP {resp.status}: {error_text}", "banner_ids": banner_ids}


async def disable_banners_batch(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    banners: list[dict],
    dry_run: bool = True,
    whitelist_ids: set | None = None,
    concurrency: int = 5,  # Deprecated, сохранён для обратной совместимости
) -> dict:
    """
    Отключает несколько баннеров через массовый API /banners/mass_action.json.

    Оптимизировано: вместо N запросов делает ceil(N/200) запросов.
    VK API позволяет отключать до 200 баннеров за один запрос.
    """
    if not banners:
        logger.info("✅ Нет убыточных объявлений для отключения")
        return {"disabled": 0, "failed": 0, "skipped": 0, "results": []}

    whitelist_ids = whitelist_ids or set()

    # Разделяем на те что нужно отключить и те что в whitelist
    to_disable = []
    skipped_results = []

    for banner in banners:
        banner_id = banner.get("id")
        banner_name = banner.get("name", "Unknown")
        spent = banner.get("spent", 0)
        ad_group_id = banner.get("ad_group_id", "N/A")

        if banner_id in whitelist_ids:
            logger.info(f"⏳ Пропускаем объявление {banner_id} — находится в белом списке")
            skipped_results.append({
                "banner_id": banner_id,
                "banner_name": banner_name,
                "ad_group_id": ad_group_id,
                "spent": spent,
                "success": False,
                "skipped": True,
                "error": "skipped (whitelisted)"
            })
        else:
            to_disable.append(banner)

    logger.info(f"🎯 {'[DRY RUN] ' if dry_run else ''}Отключение {len(to_disable)} убыточных объявлений (пропущено: {len(skipped_results)})")

    # Результаты отключения
    disabled_results = []
    failed_results = []

    # Массовое отключение чанками по 200 (лимит VK API)
    MASS_ACTION_LIMIT = 200

    for chunk_start in range(0, len(to_disable), MASS_ACTION_LIMIT):
        chunk = to_disable[chunk_start:chunk_start + MASS_ACTION_LIMIT]
        chunk_ids = [b.get("id") for b in chunk]

        result = await disable_banners_mass_action(
            session, token, base_url, chunk_ids, dry_run
        )

        # Формируем результаты для каждого баннера в чанке
        for banner in chunk:
            banner_id = banner.get("id")
            banner_name = banner.get("name", "Unknown")
            spent = banner.get("spent", 0)
            ad_group_id = banner.get("ad_group_id", "N/A")

            banner_result = {
                "banner_id": banner_id,
                "banner_name": banner_name,
                "ad_group_id": ad_group_id,
                "spent": spent,
                "success": result.get("success", False),
                "skipped": False,
                "error": result.get("error") if not result.get("success") else None
            }

            if result.get("success"):
                disabled_results.append(banner_result)
            else:
                failed_results.append(banner_result)

    # Объединяем все результаты
    all_results = disabled_results + failed_results + skipped_results

    disabled_count = len(disabled_results)
    failed_count = len(failed_results)
    skipped_count = len(skipped_results)

    logger.info("=" * 80)
    logger.info(f"🎯 {'[DRY RUN] ' if dry_run else ''}Итоги отключения объявлений:")
    logger.info(f"✅ {'Было бы отключено' if dry_run else 'Отключено'}: {disabled_count}")
    logger.info(f"⏳ Пропущено (whitelist): {skipped_count}")
    logger.info(f"❌ Ошибок: {failed_count}")
    logger.info(f"📊 Всего обработано: {len(banners)}")
    logger.info(f"📡 API запросов: {max(1, (len(to_disable) + MASS_ACTION_LIMIT - 1) // MASS_ACTION_LIMIT) if to_disable else 0}")
    logger.info("=" * 80)

    return {
        "disabled": disabled_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "total": len(banners),
        "results": all_results,
        "dry_run": dry_run
    }


async def toggle_ad_group_status(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    group_id: int,
    new_status: str,
) -> dict:
    """
    Переключает статус группы объявлений асинхронно.
    """
    url = f"{base_url}/ad_groups/{group_id}.json"
    data = {"status": new_status}

    try:
        resp = await _request_with_retries(
            session,
            "POST",
            url,
            headers=_headers(token),
            json=data,
            timeout=aiohttp.ClientTimeout(total=20),
        )
    except Exception as e:
        logger.error(
            f"❌ Ошибка сети при переключении статуса группы {group_id} на {new_status}: {e}"
        )
        return {"success": False, "error": str(e)}

    if resp.status in (200, 204):
        logger.info(f"✅ Группа {group_id} успешно переключена в статус {new_status}")
        return {"success": True}

    text = await resp.text()
    error_msg = f"❌ Ошибка HTTP {resp.status} при переключении группы {group_id} на {new_status}: {text[:200]}"
    logger.error(error_msg)
    return {"success": False, "error": f"HTTP {resp.status}: {text}"}


async def trigger_statistics_refresh(
    session: aiohttp.ClientSession,
    token: str,
    base_url: str,
    trigger_config: dict,
) -> dict:
    """
    Запускает триггер для обновления статистики VK Ads асинхронно.
    """
    if not trigger_config.get("enabled", False):
        logger.debug("🔧 Триггер обновления статистики отключен")
        return {"success": True, "skipped": True}

    group_id = trigger_config.get("group_id")
    wait_seconds = trigger_config.get("wait_seconds", 20)

    if not group_id:
        logger.warning("⚠️ ID группы для триггера не настроен - пропускаем обновление статистики")
        return {"success": False, "error": "Не настроен group_id"}

    logger.info(f"🎯 ЗАПУСК ТРИГГЕРА ОБНОВЛЕНИЯ СТАТИСТИКИ VK (группа {group_id})")

    # Включаем группу
    result1 = await toggle_ad_group_status(session, token, base_url, group_id, "active")
    if not result1.get("success"):
        error_text = result1.get('error')
        logger.error(f"❌ Не удалось включить триггер группу {group_id}: {error_text}")
        return {"success": False, "error": f"Ошибка включения: {error_text}"}

    # Ждем
    logger.info(f"⏳ Ожидание {wait_seconds} сек. для обновления статистики VK...")
    await asyncio.sleep(wait_seconds)

    # Отключаем группу обратно
    result2 = await toggle_ad_group_status(session, token, base_url, group_id, "blocked")
    if not result2.get("success"):
        error_text = result2.get('error')
        logger.error(f"❌ Не удалось отключить триггер группу {group_id}: {error_text}")
        return {"success": False, "error": f"Ошибка отключения: {error_text}"}

    logger.info(f"✅ Триггер обновления статистики завершен (группа {group_id})")
    return {"success": True, "group_id": group_id, "wait_seconds": wait_seconds}
