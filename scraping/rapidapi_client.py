"""Fetch a single Instagram profile's detail through the RapidAPI provider."""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import httpx

from scraping.apify_client import ScrapingError
from scraping.settings import PipelineSettings

logger = logging.getLogger("app")

# Process-wide spacing so ThreadPool workers do not stampede RapidAPI.
_rate_lock = threading.Lock()
_next_allowed = 0.0


def _headers(settings: PipelineSettings) -> dict[str, str]:
    return {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.rapidapi_host,
        "content-type": "application/json",
    }


def _endpoint(settings: PipelineSettings) -> str:
    return f"https://{settings.rapidapi_host}/{settings.rapidapi_profile_path}"


def _throttle(min_interval_s: float) -> None:
    """Enforce a minimum gap between RapidAPI calls across all threads."""
    global _next_allowed
    if min_interval_s <= 0:
        return
    with _rate_lock:
        now = time.monotonic()
        wait = _next_allowed - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _next_allowed = now + min_interval_s


def _retry_after_seconds(resp: httpx.Response, fallback: float) -> float:
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return fallback
    try:
        return max(fallback, float(raw))
    except ValueError:
        return fallback


def fetch_profile(
    username: str,
    *,
    settings: PipelineSettings,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Return the raw profile JSON for one username, retrying transient failures."""
    clean = (username or "").strip().lstrip("@")
    if not clean:
        raise ScrapingError("Empty username.")

    url = _endpoint(settings)
    method = settings.rapidapi_profile_method or "POST"
    param = settings.rapidapi_username_param or "username"
    attempts = max(1, settings.rapidapi_max_retries)
    min_interval = float(getattr(settings, "rapidapi_min_interval_s", 0.35) or 0.0)

    global _next_allowed

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=settings.rapidapi_timeout_s)
    last_error: str = ""
    try:
        for attempt in range(1, attempts + 1):
            try:
                _throttle(min_interval)
                if method == "GET":
                    resp = client.get(url, headers=_headers(settings), params={param: clean})
                else:
                    resp = client.request(
                        method, url, headers=_headers(settings), json={param: clean}
                    )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                delay = settings.rapidapi_retry_backoff_s * (2 ** (attempt - 1))
                delay += random.uniform(0, 0.5)
                time.sleep(delay)
                continue

            if resp.status_code == 429:
                last_error = "HTTP 429"
                base = settings.rapidapi_retry_backoff_s * (2 ** (attempt - 1))
                delay = _retry_after_seconds(resp, base)
                delay = max(delay, 3.0) + random.uniform(0, 1.0)
                logger.warning(
                    "RapidAPI 429 for @%s (attempt %s/%s); sleeping %.1fs",
                    clean,
                    attempt,
                    attempts,
                    delay,
                )
                # Push the global throttle out so other workers also back off.
                with _rate_lock:
                    _next_allowed = max(_next_allowed, time.monotonic() + delay * 0.5)
                time.sleep(delay)
                continue

            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                delay = settings.rapidapi_retry_backoff_s * (2 ** (attempt - 1))
                delay += random.uniform(0, 0.5)
                time.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise ScrapingError(
                    f"RapidAPI HTTP {resp.status_code} for @{clean}: {resp.text[:200]}"
                )
            try:
                return resp.json()
            except ValueError as exc:
                raise ScrapingError(f"RapidAPI returned non-JSON for @{clean}.") from exc

        raise ScrapingError(f"RapidAPI failed for @{clean} after {attempts} attempt(s): {last_error}")
    finally:
        if owns_client:
            client.close()
