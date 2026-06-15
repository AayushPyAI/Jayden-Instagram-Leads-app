#!/usr/bin/env python3
"""Print the URL Lead Pipeline configuration and whether it is ready to run.

Shows a non-secret snapshot of settings and which credentials are present,
without ever printing the secret values.

Usage:
    python scripts/check_pipeline_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scraping import load_settings  # noqa: E402


def main() -> int:
    settings = load_settings()
    snapshot = settings.safe_snapshot()

    print("URL Lead Pipeline — configuration check")
    print("=" * 44)
    for key, value in snapshot.items():
        print(f"  {key:28} = {value}")

    print("-" * 44)
    if settings.enabled:
        print("STATUS: ENABLED — all credentials present.")
        return 0

    missing = ", ".join(settings.missing_credentials())
    print(f"STATUS: DISABLED — missing: {missing}")
    print("Add the missing keys to .env to enable the URL Pipeline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
