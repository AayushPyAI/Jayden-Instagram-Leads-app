"""Turn a RapidAPI profile into a lead row.

Maps the profile onto the column keys the existing app and Excel exports use
(Business Name, Mobile, Email, Instagram, Source URL). Phone and email are read
from the structured fields first and fall back to the biography text, since many
businesses only list contact details there. Formatting reuses the processor
helpers so values match the screenshot flow.
"""

from __future__ import annotations

import re
from typing import Any

from processor import format_phone_for_storage, normalize_email

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
_MIN_PHONE_DIGITS = 8


def _digit_count(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def find_email_in_bio(biography: str) -> str:
    if not biography:
        return ""
    match = _EMAIL_RE.search(biography)
    return match.group(0).strip() if match else ""


def find_phone_in_bio(biography: str) -> str:
    if not biography:
        return ""
    for candidate in _PHONE_RE.findall(biography):
        if _digit_count(candidate) >= _MIN_PHONE_DIGITS:
            return candidate.strip()
    return ""


def find_phone_in_profile(user: dict[str, Any]) -> str:
    number = str(user.get("public_phone_number") or "").strip()
    if number:
        cc = str(user.get("public_phone_country_code") or "").strip()
        return f"+{cc}{number}" if cc else number

    contact = str(user.get("contact_phone_number") or "").strip()
    if contact:
        return contact

    return find_phone_in_bio(str(user.get("biography") or ""))


def find_email_in_profile(user: dict[str, Any]) -> str:
    public = str(user.get("public_email") or "").strip()
    if public:
        return public
    return find_email_in_bio(str(user.get("biography") or ""))


def extract_lead(user: dict[str, Any], source_url: str = "") -> dict[str, str]:
    raw_phone = find_phone_in_profile(user)
    raw_email = find_email_in_profile(user)
    return {
        "Business Name": str(user.get("full_name") or "").strip(),
        "Mobile": format_phone_for_storage(raw_phone),
        "Email": normalize_email(raw_email),
        "Instagram": str(user.get("username") or "").strip().lstrip("@"),
        "Source URL": str(source_url or "").strip(),
    }
