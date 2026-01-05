"""
VK Ads API Client for LeadsTech Analysis

Synchronous client for fetching banner statistics from VK Ads API.
"""

import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Set, Tuple

import requests

from utils.logging_setup import get_logger

logger = get_logger(service="leadstech", function="vk_client")


@dataclass
class VkAdsConfig:
    """Configuration for VK Ads API client."""
    base_url: str
    api_token: str


class VkAdsClient:
    """VK Ads API client for fetching banner statistics."""

    def __init__(self, cfg: VkAdsConfig):
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        return {"Authorization": f"Bearer {self.cfg.api_token}"}

    def get_banners_stats_day(
        self,
        date_from: date,
        date_to: date,
        banner_ids: List[int],
        metrics: str = "base",
    ) -> List[Dict[str, Any]]:
        """
        Fetch banner stats with retry on rate limit.

        Args:
            date_from: Start date for statistics
            date_to: End date for statistics
            banner_ids: List of banner IDs to fetch
            metrics: Metrics type (default: "base")

        Returns:
            List of banner statistics
        """
        url = self.cfg.base_url.rstrip("/") + "/statistics/banners/day.json"

        params: Dict[str, Any] = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "metrics": metrics,
        }

        if banner_ids:
            params["id"] = ",".join(map(str, banner_ids))

        # Log API token prefix for debugging
        token_prefix = self.cfg.api_token[:20] if self.cfg.api_token else "NONE"
        logger.info(
            f"VK Ads: requesting stats for {len(banner_ids)} banners "
            f"(period {params['date_from']}..{params['date_to']}), token={token_prefix}..."
        )

        max_retries = 5
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=60,  # Increased timeout
                )

                # Rate limit (429) or server error (5xx) - retry
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8, 16, 32 seconds
                    logger.warning(
                        f"VK Ads: HTTP {resp.status_code}, attempt {attempt}/{max_retries}, "
                        f"waiting {wait_time} sec"
                    )
                    if attempt < max_retries:
                        time.sleep(wait_time)
                        continue
                    else:
                        resp.raise_for_status()

                resp.raise_for_status()

                payload = resp.json()
                items = payload.get("items", [])

                # Log which banners were returned
                logger.info(f"VK Ads: requested {len(banner_ids)} banners, received {len(items)} in response")

                if len(items) == 0 and len(banner_ids) > 0:
                    logger.warning(
                        f"VK Ads: API returned 0 items! Banner IDs may not exist in this VK account. "
                        f"Requested: {banner_ids[:5]}"
                    )

                return items

            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"VK Ads: network error, attempt {attempt}/{max_retries}, "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"VK Ads: failed to get banner stats after {max_retries} attempts: {e}")
                    raise

            except requests.HTTPError as exc:
                error_msg = f"VK Ads: error requesting banner stats: {exc}, body={resp.text}"
                logger.error(error_msg)
                raise

        logger.error(f"VK Ads: failed to get stats after {max_retries} attempts: {last_error}")
        return []

    def get_spent_by_banner(
        self,
        date_from: date,
        date_to: date,
        banner_ids: List[int],
    ) -> Tuple[Dict[int, float], Set[int]]:
        """
        Get spending by banner with chunking.

        Args:
            date_from: Start date for statistics
            date_to: End date for statistics
            banner_ids: List of banner IDs to fetch

        Returns:
            Tuple of:
            - Dictionary mapping banner ID to spent amount (only non-zero)
            - Set of all valid banner IDs that VK API returned data for
        """
        if not banner_ids:
            return {}, set()

        spent_by_id: Dict[int, float] = {}
        valid_ids: Set[int] = set()
        chunk_size = 150
        chunk_delay = 0.5  # Delay between chunks to avoid rate limiting

        total_ids = len(banner_ids)
        total_chunks = (total_ids + chunk_size - 1) // chunk_size
        logger.info(
            f"VK Ads: calculating spend for {total_ids} banners "
            f"({total_chunks} chunks of {chunk_size})"
        )

        for chunk_num, start in enumerate(range(0, total_ids, chunk_size), 1):
            chunk = banner_ids[start:start + chunk_size]

            # Add delay between chunks to avoid rate limiting (skip first chunk)
            if chunk_num > 1:
                time.sleep(chunk_delay)

            items = self.get_banners_stats_day(date_from, date_to, chunk, metrics="base")

            for item in items:
                bid = item.get("id")
                if bid is None:
                    continue

                try:
                    banner_id_int = int(bid)
                except (TypeError, ValueError):
                    continue

                # This banner ID is valid (VK returned data for it)
                valid_ids.add(banner_id_int)

                total_base = item.get("total", {}).get("base", {})
                spent = float(total_base.get("spent", 0) or 0)

                # Store all spent values (including zero)
                spent_by_id[banner_id_int] = spent

        non_zero_count = sum(1 for v in spent_by_id.values() if v > 0)
        logger.info(
            f"VK Ads: {len(valid_ids)} valid banner IDs, "
            f"{non_zero_count} with non-zero spent"
        )
        return spent_by_id, valid_ids

    def get_total_spent(self, date_from: date, date_to: date) -> float:
        """
        Get total spent for entire account (no banner filter).

        Makes a request without banner ID filter to get total account spending.

        Args:
            date_from: Start date for statistics
            date_to: End date for statistics

        Returns:
            Total spent amount for the account
        """
        url = self.cfg.base_url.rstrip("/") + "/statistics/banners/day.json"
        params = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "metrics": "base",
        }
        # No 'id' parameter - returns total statistics for entire account

        logger.info(
            f"VK Ads: requesting total spent for account "
            f"(period {params['date_from']}..{params['date_to']})"
        )

        max_retries = 5
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=60,
                )

                # Rate limit (429) or server error (5xx) - retry
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8, 16, 32 seconds
                    logger.warning(
                        f"VK Ads: HTTP {resp.status_code}, attempt {attempt}/{max_retries}, "
                        f"waiting {wait_time} sec"
                    )
                    if attempt < max_retries:
                        time.sleep(wait_time)
                        continue
                    else:
                        resp.raise_for_status()

                resp.raise_for_status()

                payload = resp.json()
                total_spent = float(payload.get("total", {}).get("base", {}).get("spent", 0) or 0)
                logger.info(f"VK Ads: total spent for account = {total_spent}")
                return total_spent

            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"VK Ads: network error (total spent), attempt {attempt}/{max_retries}, "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"VK Ads: failed to get total spent after {max_retries} attempts: {e}")
                    raise

            except requests.HTTPError as exc:
                logger.error(f"VK Ads: error requesting total spent: {exc}, body={resp.text}")
                raise

        logger.error(f"VK Ads: failed to get total spent after {max_retries} attempts: {last_error}")
        return 0.0
