#!/usr/bin/env python3
"""Run the filter and extractor against real profile samples (no API calls).

Uses trimmed copies of actual RapidAPI responses to verify each keep/skip
decision and the lead fields extracted from kept profiles.

Usage:
    python scripts/test_filter_samples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scraping import evaluate_profile, extract_lead, unwrap_user  # noqa: E402
from scraping.profile_filter import (  # noqa: E402
    REASON_HAS_LINK,
    REASON_NO_PHONE,
    REASON_NOT_BUSINESS,
    REASON_OK,
)

# Business account with a beacons.ai link in its bio.
SAMPLE_HG_PUREWATER = {
    "result": [
        {
            "user": {
                "username": "hgpurewater.au",
                "full_name": "HG PureWater",
                "is_private": False,
                "is_business": True,
                "account_type": 2,
                "public_email": "info@hgpurewater.com.au",
                "public_phone_country_code": "61",
                "public_phone_number": "1300883058",
                "contact_phone_number": "+611300883058",
                "biography": "💙RO • Whole House • Water Softeners\n📍Australia",
                "external_url": "https://beacons.ai/hgpurewater.au",
                "bio_links": [{"url": "https://beacons.ai/hgpurewater.au"}],
            },
            "status": "ok",
        }
    ]
}

# Verified account that is not flagged as a business.
SAMPLE_INSTAGRAM = {
    "result": [
        {
            "user": {
                "username": "instagram",
                "full_name": "Instagram",
                "is_private": False,
                "is_business": False,
                "account_type": 3,
                "public_email": "",
                "public_phone_number": "",
                "biography": "Creator Week ✨ Happening now on @creators",
                "external_url": "http://help.instagram.com/",
                "bio_links": [{"url": "http://help.instagram.com/"}],
            },
            "status": "ok",
        }
    ]
}

# Business with no link and a phone number written only in the bio text.
SAMPLE_BUSINESS_NO_LINK = {
    "result": [
        {
            "user": {
                "username": "joniecplumbing",
                "full_name": "Joniec Plumbing",
                "is_private": False,
                "is_business": True,
                "public_email": "",
                "public_phone_number": "",
                "contact_phone_number": "",
                "biography": "PLUMBING WITH INTEGRITY\n🔧 Residential • Commercial\n📞 1300 575 862\n📍 Melbourne",
                "external_url": "",
                "bio_links": [],
            },
            "status": "ok",
        }
    ]
}

# Business with no link and no phone, only an email.
SAMPLE_BUSINESS_NO_PHONE = {
    "result": [
        {
            "user": {
                "username": "rh___designs",
                "full_name": "RH Designs",
                "is_private": False,
                "is_business": True,
                "public_email": "hello@example.com",
                "public_phone_number": "",
                "contact_phone_number": "",
                "biography": "Interior design studio",
                "external_url": "",
                "bio_links": [],
            },
            "status": "ok",
        }
    ]
}

CASES = [
    ("hgpurewater.au (business + beacons link)", SAMPLE_HG_PUREWATER, False, REASON_HAS_LINK),
    ("instagram (not a business account)", SAMPLE_INSTAGRAM, False, REASON_NOT_BUSINESS),
    ("joniecplumbing (business, no link, bio phone)", SAMPLE_BUSINESS_NO_LINK, True, REASON_OK),
    ("rh___designs (business, no link, no phone)", SAMPLE_BUSINESS_NO_PHONE, False, REASON_NO_PHONE),
]


def main() -> int:
    print("Phase 1 — filter + extractor sample test")
    print("=" * 60)

    failures = 0
    for label, payload, expect_keep, expect_reason in CASES:
        result = evaluate_profile(payload, skip_private=True)
        ok = result.keep == expect_keep and result.reason == expect_reason
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1

        verdict = "KEEP" if result.keep else "SKIP"
        print(f"[{status}] {label}")
        print(f"        -> {verdict} (reason={result.reason}); "
              f"expected {'KEEP' if expect_keep else 'SKIP'} (reason={expect_reason})")

        if result.keep:
            lead = extract_lead(unwrap_user(payload), source_url="joniecplumbing")
            print(f"        lead: {lead}")
        print()

    print("-" * 60)
    if failures == 0:
        print(f"ALL {len(CASES)} CASES PASSED ✅")
        return 0
    print(f"{failures} of {len(CASES)} CASES FAILED ❌")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
