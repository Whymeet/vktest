"""
LeadsTech Analyzer - fetches data from LeadsTech and VK Ads, calculates ROI
Reads configuration from database and saves results back to database
"""

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import uuid

import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.time_utils import get_moscow_time
from utils.logging_setup import get_logger, setup_logging as init_logging

from database import SessionLocal
from database import crud

# Setup logging
logger = get_logger(service="leadstech")


def setup_logging():
    """Setup logging configuration (совместимость со старым API)"""
    init_logging()
    logger.info("LeadsTech Analyzer инициализирован")


# === LeadsTech Client ===

@dataclass
class LeadstechClientConfig:
    base_url: str
    login: str
    password: str
    page_size: int = 500
    banner_sub_fields: List[str] = None  # List of sub fields to analyze (e.g. ["sub4", "sub5"])

    def __post_init__(self):
        if self.banner_sub_fields is None:
            self.banner_sub_fields = ["sub4"]


class LeadstechClient:
    """LeadsTech API client"""

    def __init__(self, cfg: LeadstechClientConfig):
        self.cfg = cfg
        self._token: Optional[str] = None

    @property
    def _login_url(self) -> str:
        return f"{self.cfg.base_url.rstrip('/')}/v1/front/authorization/login"

    @property
    def _by_subid_url(self) -> str:
        return f"{self.cfg.base_url.rstrip('/')}/v1/front/stat/by-subid"

    def _login(self) -> str:
        """Authenticate and get token"""
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
        }
        payload = {
            "login": self.cfg.login,
            "password": self.cfg.password,
        }

        logger.info(f"LeadsTech: authenticating as {self.cfg.login}")

        resp = requests.post(self._login_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        if not data.get("success"):
            # Extract error code for better diagnostics
            error_codes = data.get("error", [])
            error_msg = ", ".join(str(e) for e in error_codes) if error_codes else "unknown"
            logger.error(f"LeadsTech authentication failed. Error code: {error_msg}")
            logger.error(f"Response status: {resp.status_code}, login used: {self.cfg.login}")
            # Use repr() to escape curly braces, preventing Loguru format conflicts
            raise RuntimeError(f"LeadsTech login error (code: {error_msg}): {repr(data)}")

        token = data.get("data", {}).get("jsonAccessWebToken")
        if not token:
            # Use repr() to escape curly braces, preventing Loguru format conflicts
            raise RuntimeError(f"jsonAccessWebToken not found in response: {repr(data)}")

        logger.info(f"LeadsTech: token received (length {len(token)})")
        return token

    def _get_token(self) -> str:
        if self._token is None:
            self._token = self._login()
        return self._token

    def get_stat_by_subid(
        self,
        date_from: date,
        date_to: date,
        sub1_value: str,
        subs_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch stats by subid with pagination"""
        token = self._get_token()
        subs_fields = subs_fields or self.cfg.banner_sub_fields

        headers = {
            "X-Auth-Token": token,
            "Accept": "application/json",
        }

        all_rows: List[Dict[str, Any]] = []
        page = 1

        while True:
            # Build params with multiple subs[] fields
            params: List[tuple] = [
                ("page", page),
                ("pageSize", self.cfg.page_size),
                ("dateStart", date_from.strftime("%d-%m-%Y")),
                ("dateEnd", date_to.strftime("%d-%m-%Y")),
                ("sub1", sub1_value),
                ("strictSubs", 0),
                ("untilCurrentTime", 0),
                ("limitLowerDay", 0),
                ("limitUpperDay", 0),
            ]
            # Add all sub fields
            for sub_field in subs_fields:
                params.append(("subs[]", sub_field))

            logger.info(f"LeadsTech: by-subid page={page} (sub1={sub1_value}, subs[]={subs_fields}, {date_from.strftime('%d-%m-%Y')}..{date_to.strftime('%d-%m-%Y')})")

            resp = requests.get(
                self._by_subid_url,
                headers=headers,
                params=params,
                timeout=30,
            )

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                logger.error(f"LeadsTech: error requesting by-subid page={page}: {exc}, body={resp.text}")
                raise

            payload = resp.json()
            rows = self._extract_rows(payload)

            logger.info(f"LeadsTech: page={page} - {len(rows)} rows")

            if not rows:
                break

            all_rows.extend(rows)

            if len(rows) < self.cfg.page_size:
                break

            page += 1

        logger.info(f"LeadsTech: total {len(all_rows)} rows received")
        return all_rows

    @staticmethod
    def _extract_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract rows from API response"""
        data = payload.get("data")
        if isinstance(data, dict):
            if isinstance(data.get("rows"), list):
                return data["rows"]
            for key in ("items", "list", "stats"):
                if isinstance(data.get(key), list):
                    return data[key]

        if isinstance(payload, list):
            return payload

        if isinstance(payload.get("rows"), list):
            return payload["rows"]

        # Use repr() to escape curly braces, preventing Loguru format conflicts
        raise ValueError(f"Could not extract rows from LeadsTech response: {repr(payload)}")


# === VK Ads Client ===

@dataclass
class VkAdsConfig:
    base_url: str
    api_token: str


class VkAdsClient:
    """VK Ads API client"""

    def __init__(self, cfg: VkAdsConfig):
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_token}"}

    def get_banners_stats_day(
        self,
        date_from: date,
        date_to: date,
        banner_ids: List[int],
        metrics: str = "base",
    ) -> List[Dict[str, Any]]:
        """Fetch banner stats with retry on rate limit"""
        import time

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
        logger.info(f"VK Ads: requesting stats for {len(banner_ids)} banners (period {params['date_from']}..{params['date_to']}), token={token_prefix}...")

        max_retries = 5
        backoff = 1.0

        for attempt in range(1, max_retries + 1):
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )

            if resp.status_code == 429:
                logger.warning(f"VK Ads: 429 Too Many Requests, attempt {attempt}/{max_retries}, waiting {backoff:.1f} sec")
                time.sleep(backoff)
                backoff *= 2
                continue

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                logger.error(f"VK Ads: error requesting banner stats: {exc}, body={resp.text}")
                raise

            payload = resp.json()
            items = payload.get("items", [])
            
            # Log which banners were returned
            returned_ids = [item.get("id") for item in items if item.get("id")]
            logger.info(f"VK Ads: requested {len(banner_ids)} banners, received {len(items)} in response")
            if len(items) == 0 and len(banner_ids) > 0:
                logger.warning(f"VK Ads: API returned 0 items! Banner IDs may not exist in this VK account. Requested: {banner_ids[:5]}")
            
            return items

        logger.error(f"VK Ads: failed to get stats after {max_retries} attempts due to rate limiting")
        return []

    def get_spent_by_banner(
        self,
        date_from: date,
        date_to: date,
        banner_ids: List[int],
    ) -> Dict[int, float]:
        """Get spending by banner with chunking"""
        if not banner_ids:
            return {}

        spent_by_id: Dict[int, float] = {}
        chunk_size = 150

        total_ids = len(banner_ids)
        logger.info(f"VK Ads: calculating spend for {total_ids} banners (chunks of {chunk_size})")

        for start in range(0, total_ids, chunk_size):
            chunk = banner_ids[start:start + chunk_size]

            items = self.get_banners_stats_day(date_from, date_to, chunk, metrics="base")

            for item in items:
                bid = item.get("id")
                if bid is None:
                    continue

                total_base = item.get("total", {}).get("base", {})
                spent = float(total_base.get("spent", 0) or 0)

                try:
                    banner_id_int = int(bid)
                except (TypeError, ValueError):
                    continue

                spent_by_id[banner_id_int] = spent

        logger.info(f"VK Ads: collected spend for {len(spent_by_id)} banners")
        return spent_by_id


# === Aggregation ===

def aggregate_leadstech_by_banner(
    rows: List[Dict[str, Any]],
    banner_sub_fields: List[str] = None,
) -> Dict[int, Dict[str, Any]]:
    """Aggregate LeadsTech data by banner ID from multiple sub fields"""
    if banner_sub_fields is None:
        banner_sub_fields = ["sub4"]

    logger.info(f"Aggregating LeadsTech by fields: {banner_sub_fields}")

    result: Dict[int, Dict[str, Any]] = {}

    for row in rows:
        # Try each sub field to extract banner_id
        banner_id = None
        for sub_field in banner_sub_fields:
            sub_value = row.get(sub_field)
            if sub_value:
                try:
                    banner_id = int(str(sub_value))
                    break  # Found valid banner_id, stop looking
                except (TypeError, ValueError):
                    continue

        if banner_id is None:
            continue

        revenue = float(row.get("sumwebmaster", 0) or 0)
        clicks = int(row.get("clicks", 0) or 0)
        conversions = int(row.get("conversions", 0) or 0)
        inprogress = int(row.get("inprogress", 0) or 0)
        approved = int(row.get("approved", 0) or 0)
        rejected = int(row.get("rejected", 0) or 0)

        if banner_id not in result:
            result[banner_id] = {
                "banner_id": banner_id,
                "lt_revenue": 0.0,
                "lt_clicks": 0,
                "lt_conversions": 0,
                "lt_inprogress": 0,
                "lt_approved": 0,
                "lt_rejected": 0,
            }

        agg = result[banner_id]
        agg["lt_revenue"] += revenue
        agg["lt_clicks"] += clicks
        agg["lt_conversions"] += conversions
        agg["lt_inprogress"] += inprogress
        agg["lt_approved"] += approved
        agg["lt_rejected"] += rejected

    logger.info(f"Aggregated {len(result)} banners from LeadsTech")
    return result


# === Main Analysis ===

def run_analysis():
    """Main analysis function"""
    setup_logging()
    logger.info("=== LeadsTech Analysis Starting ===")

    # Get user_id from environment
    user_id = os.environ.get("VK_ADS_USER_ID")
    if not user_id:
        logger.error("VK_ADS_USER_ID environment variable not set")
        return
    try:
        user_id = int(user_id)
    except ValueError:
        logger.error("VK_ADS_USER_ID must be an integer")
        return
    logger.info(f"Running analysis for user_id={user_id}")

    db = SessionLocal()

    try:
        # Get LeadsTech config for this user
        lt_config = crud.get_leadstech_config(db, user_id=user_id)
        if not lt_config:
            logger.error(f"LeadsTech not configured for user {user_id}")
            return

        # Get enabled cabinets for this user
        cabinets = crud.get_leadstech_cabinets(db, user_id=user_id, enabled_only=True)
        if not cabinets:
            logger.error(f"No enabled LeadsTech cabinets for user {user_id}")
            return
        
        logger.info(f"Found {len(cabinets)} enabled cabinet(s)")
        for cab in cabinets:
            logger.info(f"  - Cabinet ID {cab.id}: account_id={cab.account_id}, label='{cab.leadstech_label}', enabled={cab.enabled}")

        # Calculate date range from config or use defaults (last 10 days)
        today = get_moscow_time().date()
        if lt_config.date_from and lt_config.date_to:
            date_from = datetime.strptime(lt_config.date_from, "%Y-%m-%d").date()
            date_to = datetime.strptime(lt_config.date_to, "%Y-%m-%d").date()
        else:
            # Default to last 10 days if no dates configured
            date_to = today
            date_from = date_to - timedelta(days=10)
        logger.info(f"Analysis period: {date_from} to {date_to}")

        # Get banner_sub_fields (with backwards compatibility)
        banner_sub_fields = lt_config.banner_sub_fields or ["sub4"]
        logger.info(f"Analyzing sub fields: {banner_sub_fields}")

        # Create LeadsTech client (shared for all cabinets)
        # Strip whitespace from credentials to avoid authentication issues
        lt_client_cfg = LeadstechClientConfig(
            base_url=lt_config.base_url.strip() if lt_config.base_url else "https://api.leads.tech",
            login=lt_config.login.strip() if lt_config.login else "",
            password=lt_config.password.strip() if lt_config.password else "",
            banner_sub_fields=banner_sub_fields,
        )
        lt_client = LeadstechClient(lt_client_cfg)

        all_results = []

        for cabinet in cabinets:
            account = cabinet.account
            if not account:
                logger.warning(f"Cabinet {cabinet.id} has no linked account, skipping")
                continue

            cabinet_name = account.name
            lt_label = cabinet.leadstech_label

            logger.info(f"--- Processing cabinet: {cabinet_name} (label={lt_label}) ---")

            # 1. Fetch LeadsTech data
            try:
                lt_rows = lt_client.get_stat_by_subid(
                    date_from=date_from,
                    date_to=date_to,
                    sub1_value=lt_label,
                    subs_fields=banner_sub_fields,
                )
            except Exception as e:
                # Use repr() to escape curly braces in error message for Loguru
                logger.error(f"Failed to fetch LeadsTech data for {cabinet_name}: {repr(str(e))}")
                continue

            lt_by_banner = aggregate_leadstech_by_banner(lt_rows, banner_sub_fields)

            if not lt_by_banner:
                logger.warning(f"Cabinet {cabinet_name}: no LeadsTech data, skipping")
                continue

            banner_ids = sorted(lt_by_banner.keys())
            logger.info(f"Cabinet {cabinet_name}: {len(banner_ids)} banners from LeadsTech")
            logger.info(f"Cabinet {cabinet_name}: first 10 banner IDs: {banner_ids[:10]}")

            # 2. Fetch VK Ads spending
            token_prefix = account.api_token[:25] if account.api_token else "NONE"
            logger.info(f"Cabinet {cabinet_name}: using VK API token {token_prefix}...")

            vk_cfg = VkAdsConfig(
                base_url="https://ads.vk.com/api/v2",
                api_token=account.api_token,
            )
            vk_client = VkAdsClient(vk_cfg)

            try:
                vk_spent_by_banner = vk_client.get_spent_by_banner(date_from, date_to, banner_ids)
            except Exception as e:
                logger.error(f"Failed to fetch VK Ads data for {cabinet_name}: {e}")
                vk_spent_by_banner = {}

            # Log how many banners have spending data
            banners_with_spent = sum(1 for v in vk_spent_by_banner.values() if v > 0)
            logger.info(f"Cabinet {cabinet_name}: VK returned spend for {len(vk_spent_by_banner)}/{len(banner_ids)} banners ({banners_with_spent} with non-zero spent)")

            if len(vk_spent_by_banner) == 0:
                logger.warning(f"Cabinet {cabinet_name}: VK API returned NO data for any banners! Check if banner IDs exist in this VK account.")

            # 3. Merge and calculate ROI - ONLY include banners found in VK
            valid_banners = 0
            skipped_banners = 0
            for banner_id, lt_data in lt_by_banner.items():
                # Skip banners not found in VK (invalid IDs from sub fields)
                if banner_id not in vk_spent_by_banner:
                    skipped_banners += 1
                    continue

                valid_banners += 1
                lt_revenue = float(lt_data.get("lt_revenue", 0.0))
                vk_spent = float(vk_spent_by_banner.get(banner_id, 0.0))

                profit = lt_revenue - vk_spent
                roi_percent = None
                if vk_spent > 0:
                    roi_percent = (profit / vk_spent) * 100.0

                result = {
                    "cabinet_name": cabinet_name,
                    "leadstech_label": lt_label,
                    "banner_id": banner_id,
                    "vk_spent": round(vk_spent, 2),
                    "lt_revenue": round(lt_revenue, 2),
                    "profit": round(profit, 2),
                    "roi_percent": round(roi_percent, 2) if roi_percent is not None else None,
                    "lt_clicks": int(lt_data.get("lt_clicks", 0)),
                    "lt_conversions": int(lt_data.get("lt_conversions", 0)),
                    "lt_approved": int(lt_data.get("lt_approved", 0)),
                    "lt_inprogress": int(lt_data.get("lt_inprogress", 0)),
                    "lt_rejected": int(lt_data.get("lt_rejected", 0)),
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                }
                all_results.append(result)

            logger.info(f"Cabinet {cabinet_name}: {valid_banners} valid banners, {skipped_banners} skipped (not found in VK)")

        # 4. Clear old results and save new ones
        if all_results:
            # Set user_id for all results
            for result in all_results:
                result['user_id'] = user_id
            logger.info(f"Clearing old results and saving {len(all_results)} new results...")
            count = crud.replace_leadstech_analysis_results(db, all_results, user_id=user_id)
            logger.info(f"✅ Saved {count} results to database (replaced all previous)")
        else:
            logger.warning("⚠️ No results to save")

        logger.info("=== LeadsTech Analysis Complete ===")

    except Exception as e:
        logger.exception(f"❌ Analysis failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_analysis()
