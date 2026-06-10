#!/usr/bin/env python3
"""Extract Instagram + phone from a screenshot folder and write a two-column CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from processor import extract_from_screenshot, format_phone_for_storage  # noqa: E402


def load_images(folder: Path) -> list[tuple[str, bytes]]:
    items: list[tuple[str, bytes]] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and path.is_file():
            items.append((path.name, path.read_bytes()))
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Folder containing screenshots")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV path (default: <folder>/leads.csv)",
    )
    args = parser.parse_args()
    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        raise SystemExit(f"Not a directory: {folder}")

    out = args.output or (folder / "leads.csv")
    images = load_images(folder)
    if not images:
        raise SystemExit(f"No screenshots in {folder}")

    rows: list[tuple[str, str]] = []
    for i, (name, raw) in enumerate(images, start=1):
        print(f"[{i}/{len(images)}] {name}", flush=True)
        extracted = extract_from_screenshot(raw, name, "")
        ig = str(extracted.get("instagram") or "").strip().lstrip("@")
        mobile = format_phone_for_storage(str(extracted.get("mobile") or ""))
        rows.append((ig, mobile))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["instagram", "mobile"])
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
