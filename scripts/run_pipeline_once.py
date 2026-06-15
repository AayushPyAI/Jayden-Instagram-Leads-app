"""Run the URL pipeline against one or more seed handles from the command line.

Usage:
    .venv/bin/python scripts/run_pipeline_once.py joniecplumbing
    .venv/bin/python scripts/run_pipeline_once.py https://www.instagram.com/acme/ another_handle

This makes live Apify + RapidAPI calls, so credentials must be set in .env.
It does not check leads against MASTER workbooks (dedupe is exercised in the app).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from scraping.settings import load_settings
from scraping.url_pipeline import parse_seed_handles, run_pipeline


def _progress(stage: str, message: str, done: int, total: int) -> None:
    suffix = f" ({done}/{total})" if total else ""
    print(f"  [{stage}] {message}{suffix}")


def main(argv: list[str]) -> int:
    if not argv:
        print("Pass at least one Instagram URL or @handle.")
        return 2

    settings = load_settings()
    if not settings.enabled:
        print("Pipeline disabled. Missing credentials: " + ", ".join(settings.missing_credentials()))
        return 1

    handles, invalid = parse_seed_handles(" ".join(argv), max_count=settings.max_seed_urls)
    if invalid:
        print(f"Ignored invalid inputs: {invalid}")
    if not handles:
        print("No valid seed handles.")
        return 2

    print(f"Seeds: {handles}")
    print(f"Settings: {settings.safe_snapshot()}")
    print("-" * 60)

    result = run_pipeline(handles, settings=settings, master_sources=[], progress=_progress)

    print("-" * 60)
    print("STATS:")
    for key, value in result.stats.as_dict().items():
        print(f"  {key:24} {value}")

    if result.errors:
        print(f"\nFirst errors ({len(result.errors)} total):")
        for line in result.errors[:5]:
            print(f"  - {line}")

    print(f"\nLeads ({len(result.leads)}):")
    for item in result.leads[:25]:
        lead = item["lead"]
        print(
            f"  [{item['status']:14}] {lead.get('Instagram'):24} "
            f"{lead.get('Mobile'):16} {lead.get('Business Name')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
