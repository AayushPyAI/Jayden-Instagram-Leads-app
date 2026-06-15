"""Fetch a single Instagram profile's detail through the RapidAPI provider."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from scraping.apify_client import ScrapingError
from scraping.settings import PipelineSettings

logger = logging.getLogger("app")


def _headers(settings: PipelineSettings) -> dict[str, str]:
    return {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": settings.rapidapi_host,
        "content-type": "application/json",
    }


def _endpoint(settings: PipelineSettings) -> str:
    return f"https://{settings.rapidapi_host}/{settings.rapidapi_profile_path}"


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

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=settings.rapidapi_timeout_s)
    last_error: str = ""
    try:
        for attempt in range(1, attempts + 1):
            try:
                if method == "GET":
                    resp = client.get(url, headers=_headers(settings), params={param: clean})
                else:
                    resp = client.request(
                        method, url, headers=_headers(settings), json={param: clean}
                    )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                time.sleep(settings.rapidapi_retry_backoff_s * attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(settings.rapidapi_retry_backoff_s * attempt)
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
