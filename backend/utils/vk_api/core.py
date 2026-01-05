"""
VK Ads API - Core HTTP utilities and constants
"""
import requests
import time
from utils.logging_setup import get_logger

logger = get_logger(service="vk_api")


# ===== Constants =====
API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 15  # Default delay for retries
API_RETRY_DELAY_SCALING = 3   # Shorter delay for scaling operations
API_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
VK_MIN_DAILY_BUDGET = 100  # Minimum daily budget in rubles


def _interruptible_sleep(seconds):
    """
    Interruptible sleep - splits long sleep into short intervals,
    allowing interruption via Ctrl+C
    """
    end_time = time.time() + seconds
    while time.time() < end_time:
        try:
            remaining = min(1.0, end_time - time.time())
            if remaining > 0:
                time.sleep(remaining)
        except KeyboardInterrupt:
            logger.warning("User interrupted during wait")
            raise


def _headers(token: str):
    """Generate authorization headers for VK Ads API"""
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
    Universal requests wrapper with retries for temporary errors:
    429, 500, 502, 503, 504 + network errors.

    On each failure:
      - logs the error
      - waits retry_delay seconds (default 15)
      - retries up to max_retries times
    """
    attempt = 0

    while True:
        attempt += 1
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as e:
            if attempt > max_retries:
                logger.error(
                    f"[ERROR] {method} {url} - network error after {attempt} attempts: {e}"
                )
                raise

            # For network errors use shorter delays
            wait = min(5 + attempt * 3, 15)  # 5, 8, 11 seconds max
            logger.warning(
                f"[WARN] {method} {url} - network error: {e}. "
                f"Pause {wait} sec before retry ({attempt}/{max_retries})"
            )
            _interruptible_sleep(wait)
            continue

        # Temporary/rate limit statuses - wait and retry
        if resp.status_code in API_RETRY_STATUS_CODES:
            # Log response details for diagnostics
            response_headers = dict(resp.headers)
            response_text = resp.text[:500] if resp.text else "Empty response body"

            # Determine error type for statistics
            error_type = "unknown"
            try:
                if resp.text:
                    error_data = resp.json()
                    if "error" in error_data:
                        error_info = error_data["error"]
                        if isinstance(error_info, dict):
                            error_type = error_info.get("code", "unknown")
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Could not parse error response: {e}")

            logger.debug(
                f"[DEBUG] Error {resp.status_code} details (type: {error_type}):\n"
                f"   URL: {url}\n"
                f"   Rate Limit: {response_headers.get('x-ratelimit-hourly-remaining', 'N/A')}/{response_headers.get('x-ratelimit-hourly-limit', 'N/A')}\n"
                f"   Headers: {response_headers}\n"
                f"   Body: {response_text}"
            )

            if attempt > max_retries:
                logger.error(
                    f"[ERROR] {method} {url} - HTTP {resp.status_code} after {attempt} "
                    f"attempts.\n   Response headers: {response_headers}\n"
                    f"   Response body: {response_text}"
                )
                raise RuntimeError(
                    f"HTTP {resp.status_code} after {attempt} attempts: {response_text}"
                )

            # Special case - 429 Too Many Requests
            if resp.status_code == 429:
                wait = retry_delay  # Use configured retry delay for rate limit
                try:
                    retry_after = int(resp.headers.get("Retry-After", "0"))
                    if retry_after > 0:
                        wait = max(wait, retry_after)
                except ValueError:
                    pass

                logger.warning(
                    f"[WARN] {method} {url} - rate limit (429). "
                    f"Waiting {wait} sec before retry ({attempt}/{max_retries})\n"
                    f"   Retry-After: {resp.headers.get('Retry-After', 'not specified')}"
                )
                _interruptible_sleep(wait)
            else:
                # Analyze error type for smarter handling
                error_type = "unknown"
                try:
                    if resp.text:
                        error_data = resp.json()
                        if "error" in error_data:
                            error_info = error_data["error"]
                            if isinstance(error_info, dict):
                                error_type = error_info.get("code", "unknown")
                            else:
                                error_type = str(error_info)
                except (ValueError, KeyError, TypeError) as e:
                    logger.debug(f"Could not parse error response for type detection: {e}")

                # For server errors use shorter delays
                if resp.status_code in [500, 502, 503, 504]:
                    # For unknown_api_error use even shorter intervals
                    if error_type == "unknown_api_error":
                        wait = min(5 + attempt * 3, 15)  # 5, 8, 11 seconds max
                    else:
                        wait = min(10 + attempt * 5, retry_delay)  # 10, 15, 20 seconds
                else:
                    wait = retry_delay

                logger.warning(
                    f"[WARN] {method} {url} - temporary HTTP error {resp.status_code} ({error_type}). "
                    f"Waiting {wait} sec before retry ({attempt}/{max_retries})\n"
                    f"   Headers: {dict(list(resp.headers.items())[:5])}\n"
                    f"   Body: {resp.text[:200] if resp.text else 'Empty'}"
                )
                _interruptible_sleep(wait)

            continue

        # All OK, exit
        if attempt > 1:
            logger.info(f"[OK] {method} {url} - successfully recovered after {attempt-1} attempts")
        return resp
