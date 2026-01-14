"""
LeadsTech API Client

Handles authentication and data fetching from LeadsTech API.
Supports token caching in database to avoid 429 Too Many Requests.
"""

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import requests

from utils.logging_setup import get_logger
from utils.time_utils import get_moscow_time

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(service="leadstech", function="client")

# Token TTL: 23 hours (LeadsTech JWT lives 24 hours)
TOKEN_TTL_HOURS = 23


@dataclass
class LeadstechClientConfig:
    """Configuration for LeadsTech API client."""
    base_url: str
    login: str
    password: str
    page_size: int = 500
    banner_sub_fields: List[str] = field(default_factory=lambda: ["sub4", "sub5"])


class LeadstechClient:
    """LeadsTech API client for fetching statistics."""

    def __init__(
        self,
        cfg: LeadstechClientConfig,
        db: Optional["Session"] = None,
        user_id: Optional[int] = None
    ):
        self.cfg = cfg
        self._token: Optional[str] = None
        self._db = db
        self._user_id = user_id

    @property
    def _login_url(self) -> str:
        return f"{self.cfg.base_url.rstrip('/')}/v1/front/authorization/login"

    @property
    def _by_subid_url(self) -> str:
        return f"{self.cfg.base_url.rstrip('/')}/v1/front/stat/by-subid"

    def _login(self) -> str:
        """Authenticate and get token with retry logic."""
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
        }
        payload = {
            "login": self.cfg.login,
            "password": self.cfg.password,
        }

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"LeadsTech: authenticating as {self.cfg.login} (attempt {attempt}/{max_retries})")

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

            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # 2, 4, 8 seconds
                    logger.warning(f"LeadsTech login network error: {e}. Retrying in {wait_time}s ({attempt}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"LeadsTech login failed after {max_retries} attempts: {e}")
                    raise

            except requests.HTTPError as e:
                last_error = e
                # Retry only for server errors (5xx)
                if e.response is not None and e.response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"LeadsTech server error {e.response.status_code}. Retrying in {wait_time}s ({attempt}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"LeadsTech login HTTP error: {e}")
                    raise

        # Should not reach here, but just in case
        raise RuntimeError(f"LeadsTech login failed after {max_retries} attempts: {last_error}")

    def _get_token(self) -> str:
        """Get cached token or login to get a new one.

        Priority:
        1. In-memory cache (self._token)
        2. Database cache (if db and user_id provided)
        3. Fresh login
        """
        # 1. Check in-memory cache
        if self._token is not None:
            return self._token

        # 2. Check database cache
        if self._db is not None and self._user_id is not None:
            from database.crud.leadstech import get_cached_token
            cached = get_cached_token(self._db, self._user_id)
            if cached:
                self._token = cached
                return self._token

        # 3. Fresh login
        self._token = self._login()

        # Save to database cache
        if self._db is not None and self._user_id is not None:
            from database.crud.leadstech import save_cached_token
            expires_at = get_moscow_time() + timedelta(hours=TOKEN_TTL_HOURS)
            save_cached_token(self._db, self._user_id, self._token, expires_at)

        return self._token

    def _clear_token_cache(self) -> None:
        """Clear token from memory and database (call on 401/403 errors)."""
        self._token = None
        if self._db is not None and self._user_id is not None:
            from database.crud.leadstech import clear_cached_token
            clear_cached_token(self._db, self._user_id)

    def _refresh_token(self) -> str:
        """Force refresh token (clear cache and login again)."""
        self._clear_token_cache()
        return self._get_token()

    def _request_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        params: List[tuple],
        page: int,
        max_retries: int = 3,
    ) -> requests.Response:
        """
        Make HTTP request with retry logic for transient errors.
        
        Retries on:
        - 503 Service Unavailable
        - 504 Gateway Timeout
        - Connection errors
        - Timeouts
        
        Uses exponential backoff: 2s, 4s, 8s between retries.
        """
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                
                # Check for retryable HTTP errors
                if resp.status_code in (503, 504):
                    if attempt < max_retries:
                        wait_time = 2 ** attempt  # 2, 4, 8 seconds
                        logger.warning(
                            f"LeadsTech: HTTP {resp.status_code} on page={page}, "
                            f"retrying in {wait_time}s ({attempt}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Last attempt failed, raise the error
                        resp.raise_for_status()
                
                return resp
                
            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"LeadsTech: network error on page={page}: {e}. "
                        f"Retrying in {wait_time}s ({attempt}/{max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"LeadsTech: request failed after {max_retries} attempts: {e}")
                    raise
        
        # Should not reach here
        raise RuntimeError(f"LeadsTech request failed after {max_retries} attempts: {last_error}")

    def get_stat_by_subid(
        self,
        date_from: date,
        date_to: date,
        sub1_value: str,
        subs_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch stats by subid with pagination.

        Args:
            date_from: Start date for statistics
            date_to: End date for statistics
            sub1_value: Value for sub1 filter (usually LeadsTech label)
            subs_fields: List of sub fields to fetch (e.g., ["sub4", "sub5"])

        Returns:
            List of statistics rows
        """
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

            logger.info(
                f"LeadsTech: by-subid page={page} "
                f"(sub1={sub1_value}, subs[]={subs_fields}, "
                f"{date_from.strftime('%d-%m-%Y')}..{date_to.strftime('%d-%m-%Y')})"
            )

            resp = self._request_with_retry(
                self._by_subid_url,
                headers=headers,
                params=params,
                page=page,
            )

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                # Handle expired token (401/403) - refresh and retry once
                if exc.response is not None and exc.response.status_code in (401, 403):
                    logger.warning(f"LeadsTech token expired (HTTP {exc.response.status_code}), refreshing...")
                    token = self._refresh_token()
                    headers["X-Auth-Token"] = token
                    # Retry the same request with new token
                    resp = self._request_with_retry(
                        self._by_subid_url,
                        headers=headers,
                        params=params,
                        page=page,
                    )
                    resp.raise_for_status()
                else:
                    error_msg = f"LeadsTech: error requesting by-subid page={page}: {exc}, body={resp.text}"
                    logger.error(error_msg)
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

    def get_stat_by_subid_with_filter(
        self,
        date_from: date,
        date_to: date,
        sub1_value: str,
        sub_field: str,
        sub_filter: str,
        subs_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch stats by subid with additional filter on a specific sub field.

        Uses LeadsTech search syntax:
        - "!" for strict search
        - "#" to exclude
        - "|" for OR search (e.g., "123|456|789")
        - "@" for AND search

        Args:
            date_from: Start date for statistics
            date_to: End date for statistics
            sub1_value: Value for sub1 filter (usually LeadsTech label)
            sub_field: Which sub field to filter (e.g., "sub4")
            sub_filter: Filter value (e.g., "123|456|789" for OR search)
            subs_fields: List of sub fields to fetch

        Returns:
            List of statistics rows
        """
        token = self._get_token()
        subs_fields = subs_fields or [sub_field]

        headers = {
            "X-Auth-Token": token,
            "Accept": "application/json",
        }

        all_rows: List[Dict[str, Any]] = []
        page = 1

        while True:
            # Build params with sub field filter
            params: List[tuple] = [
                ("page", page),
                ("pageSize", self.cfg.page_size),
                ("dateStart", date_from.strftime("%d-%m-%Y")),
                ("dateEnd", date_to.strftime("%d-%m-%Y")),
                ("sub1", sub1_value),
                (sub_field, sub_filter),  # Filter on specific sub field
                ("strictSubs", 0),
                ("untilCurrentTime", 0),
                ("limitLowerDay", 0),
                ("limitUpperDay", 0),
            ]
            # Add all sub fields
            for sf in subs_fields:
                params.append(("subs[]", sf))

            logger.info(
                f"LeadsTech: by-subid page={page} "
                f"(sub1={sub1_value}, {sub_field}=<batch>, "
                f"{date_from.strftime('%d-%m-%Y')}..{date_to.strftime('%d-%m-%Y')})"
            )

            resp = self._request_with_retry(
                self._by_subid_url,
                headers=headers,
                params=params,
                page=page,
            )

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                # Handle expired token (401/403) - refresh and retry once
                if exc.response is not None and exc.response.status_code in (401, 403):
                    logger.warning(f"LeadsTech token expired (HTTP {exc.response.status_code}), refreshing...")
                    token = self._refresh_token()
                    headers["X-Auth-Token"] = token
                    # Retry the same request with new token
                    resp = self._request_with_retry(
                        self._by_subid_url,
                        headers=headers,
                        params=params,
                        page=page,
                    )
                    resp.raise_for_status()
                else:
                    error_msg = f"LeadsTech: error requesting by-subid page={page}: {exc}, body={resp.text}"
                    logger.error(error_msg)
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

        logger.info(f"LeadsTech: total {len(all_rows)} rows with filter")
        return all_rows

    @staticmethod
    def _extract_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract rows from API response."""
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
