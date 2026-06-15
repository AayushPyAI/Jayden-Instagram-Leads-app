"""Decide whether a RapidAPI profile becomes a lead.

A profile is kept only when it is a business account, has no link in its bio,
and has a usable phone number. Each rejection carries a stable reason code so
callers can report per-reason counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scraping.lead_extractor import find_phone_in_profile

REASON_OK = "ok"
REASON_NOT_BUSINESS = "not_business"
REASON_HAS_LINK = "has_link"
REASON_NO_PHONE = "no_phone"
REASON_PRIVATE = "private"
REASON_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class FilterResult:
    keep: bool
    reason: str


def unwrap_user(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the user dict from a full RapidAPI response or an unwrapped one."""
    if not isinstance(payload, dict):
        return None
    if "username" in payload and "result" not in payload:
        return payload
    result = payload.get("result")
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            user = first.get("user")
            if isinstance(user, dict):
                return user
    user = payload.get("user")
    if isinstance(user, dict):
        return user
    return None


def is_business(user: dict[str, Any]) -> bool:
    # account_type is unreliable (Instagram's own account reports type 3 with
    # is_business false), so the is_business flag is the source of truth.
    return bool(user.get("is_business"))


def is_private(user: dict[str, Any]) -> bool:
    return bool(user.get("is_private"))


def is_available(user: dict[str, Any]) -> bool:
    if "isAvailable" in user:
        return bool(user.get("isAvailable"))
    return True


def collect_links(user: dict[str, Any]) -> list[str]:
    links: list[str] = []
    ext = str(user.get("external_url") or "").strip()
    if ext:
        links.append(ext)
    bio_links = user.get("bio_links")
    if isinstance(bio_links, list):
        for item in bio_links:
            if isinstance(item, dict):
                url = str(item.get("url") or "").strip()
                if url:
                    links.append(url)
    return links


def has_any_link(user: dict[str, Any]) -> bool:
    return len(collect_links(user)) > 0


def evaluate_profile(
    payload: dict[str, Any],
    *,
    skip_private: bool = True,
) -> FilterResult:
    user = unwrap_user(payload)
    if user is None:
        return FilterResult(False, REASON_UNAVAILABLE)

    if not is_available(user):
        return FilterResult(False, REASON_UNAVAILABLE)

    if skip_private and is_private(user):
        return FilterResult(False, REASON_PRIVATE)

    if not is_business(user):
        return FilterResult(False, REASON_NOT_BUSINESS)

    if has_any_link(user):
        return FilterResult(False, REASON_HAS_LINK)

    if not find_phone_in_profile(user):
        return FilterResult(False, REASON_NO_PHONE)

    return FilterResult(True, REASON_OK)
