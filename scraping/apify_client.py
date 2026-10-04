"""Fetch Instagram followers for a seed handle through the Apify actor."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from scraping.settings import PipelineSettings

logger = logging.getLogger("app")

_APIFY_BASE = "https://api.apify.com/v2"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class ScrapingError(RuntimeError):
    """Raised when an upstream scraping API fails in a non-recoverable way."""


def _run_sync_url(actor_id: str) -> str:
    return f"{_APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _has_usable_followers(items: list[dict[str, Any]]) -> bool:
    return any(isinstance(item, dict) and str(item.get("username") or "").strip() for item in items)


def _is_demo_dataset(items: list[dict[str, Any]]) -> bool:
    if not items:
        return True
    return all(isinstance(item, dict) and item.get("demo") for item in items)


def _load_demo_fixture(handle: str) -> list[dict[str, Any]]:
    clean = handle.strip().lower().lstrip("@")
    for name in (f"{clean}_followers.json", "joniecplumbing_followers.json"):
        path = _FIXTURES_DIR / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    raise ScrapingError(
        f"Apify returned demo/empty data for @{handle} and no local fixture was found."
    )


def fetch_followers(
    handle: str,
    *,
    settings: PipelineSettings,
    results_limit: int | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Start the actor, wait for finish, then return dataset items for one handle.

    Uses async run + poll instead of run-sync-get-dataset-items, which is less
    reliable (frequent 502 / gateway timeouts on longer follower scrapes).
    """
    import time

    clean = (handle or "").strip().lstrip("@")
    if not clean:
        raise ScrapingError("Empty seed handle.")

    limit = int(results_limit or settings.max_followers_per_url)
    payload = {
        "getFollowers": True,
        "handles": [clean],
        "resultsLimit": limit,
        "getFollowings": False,
    }
    headers = _auth_headers(settings.apify_token)
    start_url = f"{_APIFY_BASE}/acts/{settings.apify_actor_id}/runs"

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=max(60, settings.apify_timeout_s), headers=headers)
    try:
        resp = client.post(start_url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise ScrapingError(
                f"Apify start failed HTTP {resp.status_code} for @{clean}: {resp.text[:300]}"
            )
        try:
            run = resp.json().get("data") or {}
        except ValueError as exc:
            raise ScrapingError(f"Apify start returned non-JSON for @{clean}.") from exc
        run_id = run.get("id")
        if not run_id:
            raise ScrapingError(f"Apify start missing run id for @{clean}.")

        deadline = time.monotonic() + max(30, settings.apify_timeout_s)
        status = run.get("status") or "READY"
        dataset_id = run.get("defaultDatasetId")
        while status in ("READY", "RUNNING"):
            if time.monotonic() > deadline:
                raise ScrapingError(f"Apify timed out waiting for @{clean} (run {run_id}).")
            time.sleep(3)
            poll = client.get(f"{_APIFY_BASE}/actor-runs/{run_id}", headers=headers)
            if poll.status_code >= 400:
                raise ScrapingError(
                    f"Apify poll HTTP {poll.status_code} for @{clean}: {poll.text[:200]}"
                )
            pdata = poll.json().get("data") or {}
            status = pdata.get("status") or status
            dataset_id = pdata.get("defaultDatasetId") or dataset_id
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                msg = pdata.get("statusMessage") or status
                raise ScrapingError(f"Apify run {status} for @{clean}: {msg}")

        if status != "SUCCEEDED" or not dataset_id:
            raise ScrapingError(f"Apify finished without dataset for @{clean} (status={status}).")

        items_resp = client.get(
            f"{_APIFY_BASE}/datasets/{dataset_id}/items",
            headers=headers,
            params={"limit": limit},
        )
        if items_resp.status_code >= 400:
            raise ScrapingError(
                f"Apify dataset HTTP {items_resp.status_code} for @{clean}: {items_resp.text[:300]}"
            )
        try:
            data = items_resp.json()
        except ValueError as exc:
            raise ScrapingError(f"Apify dataset non-JSON for @{clean}.") from exc
    except httpx.HTTPError as exc:
        raise ScrapingError(f"Apify request failed for @{clean}: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if not isinstance(data, list):
        raise ScrapingError("Unexpected Apify response shape (expected a list of items).")

    if settings.apify_demo_fallback and (_is_demo_dataset(data) or not _has_usable_followers(data)):
        logger.warning(
            "Apify free/demo dataset for @%s (%d item(s)); using local fixture for demo.",
            clean,
            len(data),
        )
        return _load_demo_fixture(clean)

    return data


def follower_usernames(
    items: list[dict[str, Any]],
    *,
    seed_handle: str = "",
    skip_private: bool = True,
) -> list[str]:
    """Unique follower usernames from actor items, dropping the seed and (optionally) private accounts."""
    seed = (seed_handle or "").strip().lower().lstrip("@")
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username") or "").strip().lstrip("@")
        if not username:
            continue
        low = username.lower()
        if low == seed or low in seen:
            continue
        if skip_private and bool(item.get("isPrivate")):
            continue
        seen.add(low)
        out.append(username)
    return out
