"""Turn Instagram seed handles into deduplicated call-list leads.

Per seed URL: Apify followers -> RapidAPI profile detail (bounded pool) -> filter
-> accumulate kept leads; then MASTER dedupe. Follower lists are not merged in RAM.
"""

from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import httpx

from processor import (
    _find_duplicate_required,
    build_master_records_from_workbook_sources,
    normalize_email,
    normalize_phone,
    normalize_username,
)
from scraping.apify_client import ScrapingError, fetch_followers, follower_usernames
from scraping.lead_extractor import extract_lead
from scraping.profile_filter import (
    REASON_HAS_LINK,
    REASON_NO_PHONE,
    REASON_NOT_BUSINESS,
    REASON_PRIVATE,
    REASON_UNAVAILABLE,
    evaluate_profile,
    unwrap_user,
)
from scraping.profile_cache import ProfileCache, get_profile_cache
from scraping.rapidapi_client import fetch_profile
from scraping.settings import PipelineSettings, load_settings

logger = logging.getLogger("app")

_HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,40}$")

ProgressFn = Callable[[str, str, int, int], None]
CancelFn = Callable[[], bool]

_REASON_FIELD = {
    REASON_PRIVATE: "skipped_private",
    REASON_NOT_BUSINESS: "skipped_not_business",
    REASON_HAS_LINK: "skipped_has_link",
    REASON_NO_PHONE: "skipped_no_phone",
    REASON_UNAVAILABLE: "skipped_unavailable",
}


def parse_seed_handle(raw: str) -> str:
    """Normalise one URL or @handle into a bare username, or '' if not valid."""
    s = (raw or "").strip()
    if not s:
        return ""
    if "instagram.com" in s.lower():
        s = re.sub(r"^https?://", "", s, flags=re.IGNORECASE)
        s = s.split("?", 1)[0].split("#", 1)[0]
        parts = [p for p in s.split("/") if p]
        s = parts[1] if len(parts) >= 2 else ""
    s = s.lstrip("@").strip("/")
    return s if _HANDLE_RE.match(s) else ""


def parse_seed_handles(text: str, *, max_count: int) -> tuple[list[str], list[str]]:
    """Split free text / pasted URLs into (valid handles, invalid raw tokens)."""
    handles: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[\s,]+", text or ""):
        token = token.strip()
        if not token:
            continue
        handle = parse_seed_handle(token)
        if not handle:
            invalid.append(token)
            continue
        low = handle.lower()
        if low in seen:
            continue
        seen.add(low)
        handles.append(handle)
    return handles[:max_count], invalid


@dataclass
class PipelineStats:
    seeds: int = 0
    followers_found: int = 0
    candidates: int = 0
    profiles_checked: int = 0
    profiles_fetched: int = 0
    profiles_cached: int = 0
    kept: int = 0
    new_leads: int = 0
    duplicate_leads: int = 0
    skipped_private: int = 0
    skipped_not_business: int = 0
    skipped_has_link: int = 0
    skipped_no_phone: int = 0
    skipped_unavailable: int = 0
    errors: int = 0
    capped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    leads: list[dict[str, Any]] = field(default_factory=list)
    stats: PipelineStats = field(default_factory=PipelineStats)
    invalid_inputs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def save_rows(self) -> list[dict[str, Any]]:
        """Rows stored for the existing save flow (in-batch dups flagged, no display keys)."""
        rows: list[dict[str, Any]] = []
        for item in self.leads:
            row = dict(item["lead"])
            if item.get("status") == "batch_duplicate":
                row["batch_duplicate"] = True
            rows.append(row)
        return rows


def _tally_reason(stats: PipelineStats, reason: str) -> None:
    attr = _REASON_FIELD.get(reason)
    if attr:
        setattr(stats, attr, getattr(stats, attr) + 1)


def _classify_against_master(
    leads: list[dict[str, Any]],
    master_sources: list[tuple[str, bytes]] | None,
) -> list[dict[str, Any]]:
    """Annotate each lead with new / duplicate / batch_duplicate for display and counts."""
    records: list[dict[str, Any]] = []
    if master_sources:
        idx = build_master_records_from_workbook_sources(master_sources)
        if idx.get("ok"):
            records = idx.get("records") or []

    seen_ig: set[str] = set()
    seen_phone: set[str] = set()
    seen_email: set[str] = set()
    annotated: list[dict[str, Any]] = []
    for lead in leads:
        ig = normalize_username(lead.get("Instagram"))
        mob = normalize_phone(lead.get("Mobile"))
        em = normalize_email(lead.get("Email"))

        dup = _find_duplicate_required(ig, mob, em, records) if records else None
        in_batch = bool(
            (ig and ig in seen_ig) or (mob and mob in seen_phone) or (em and em in seen_email)
        )

        if dup:
            status = "duplicate"
            source_file = str(dup.get("source_file") or "")
            source_row = dup.get("excel_row")
        elif in_batch:
            status = "batch_duplicate"
            source_file = ""
            source_row = None
        else:
            status = "new"
            source_file = ""
            source_row = None
            if ig:
                seen_ig.add(ig)
            if mob:
                seen_phone.add(mob)
            if em:
                seen_email.add(em)

        annotated.append(
            {
                "lead": lead,
                "status": status,
                "duplicate_source_file": source_file,
                "duplicate_source_row": source_row,
            }
        )
    return annotated


def _process_profile_result(
    username: str,
    payload: dict[str, Any],
    source: str,
    from_cache: bool,
    *,
    settings: PipelineSettings,
    stats: PipelineStats,
    result: PipelineResult,
    kept: list[dict[str, Any]],
    cache: ProfileCache | None,
    lock: threading.Lock,
) -> None:
    verdict = evaluate_profile(payload, skip_private=settings.skip_private_accounts)
    with lock:
        stats.profiles_checked += 1
        if from_cache:
            stats.profiles_cached += 1
        else:
            stats.profiles_fetched += 1
        _tally_reason(stats, verdict.reason)
        if verdict.keep:
            user = unwrap_user(payload) or {}
            kept.append(extract_lead(user, source_url=source))
            stats.kept += 1
        if cache is not None and not from_cache:
            cache.put(
                username,
                payload,
                filter_reason=verdict.reason,
                kept=verdict.keep,
                source_url=source,
            )


def run_pipeline(
    seed_handles: list[str],
    *,
    settings: PipelineSettings | None = None,
    master_sources: list[tuple[str, bytes]] | None = None,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> PipelineResult:
    settings = settings or load_settings()
    result = PipelineResult()
    stats = result.stats
    stats.seeds = len(seed_handles)

    def emit(stage: str, message: str, done: int, total: int) -> None:
        if progress:
            try:
                progress(stage, message, done, total)
            except Exception:
                pass

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    cap = settings.rapidapi_daily_call_cap
    kept: list[dict[str, Any]] = []
    seen_global: set[str] = set()
    lock = threading.Lock()
    cache: ProfileCache | None = get_profile_cache(
        settings.profile_cache_path,
        max_age_days=settings.profile_cache_days,
        enabled=settings.profile_cache_enabled,
    )
    seed_total = len(seed_handles)
    profile_done = 0
    profile_target = 0

    def check_one(username: str, source: str) -> tuple[dict[str, Any], str, bool]:
        if cache:
            hit = cache.get(username)
            if hit is not None:
                return hit["profile_json"], source, True
        return fetch_profile(username, settings=settings), source, False

    with httpx.Client(timeout=settings.apify_timeout_s) as apify_http:
        for i, seed in enumerate(seed_handles, start=1):
            if cancelled():
                break
            emit("followers", f"Fetching followers for @{seed}", i - 1, seed_total)
            try:
                items = fetch_followers(seed, settings=settings, client=apify_http)
            except ScrapingError as exc:
                stats.errors += 1
                result.errors.append(str(exc))
                continue

            usernames = follower_usernames(
                items, seed_handle=seed, skip_private=settings.skip_private_accounts
            )
            stats.followers_found += len(usernames)
            source_url = f"https://www.instagram.com/{seed}/"

            batch: list[tuple[str, str]] = []
            for username in usernames:
                if cancelled():
                    break
                low = username.lower()
                if low in seen_global:
                    continue
                if stats.candidates >= cap:
                    stats.capped = True
                    break
                seen_global.add(low)
                stats.candidates += 1
                batch.append((username, source_url))

            if batch:
                profile_target += len(batch)
                emit(
                    "profiles",
                    f"Checking profiles for @{seed}",
                    profile_done,
                    profile_target,
                )
                with ThreadPoolExecutor(max_workers=max(1, settings.concurrency)) as pool:
                    futures = {
                        pool.submit(check_one, username, src): username
                        for username, src in batch
                    }
                    for fut in as_completed(futures):
                        if cancelled():
                            break
                        username = futures[fut]
                        profile_done += 1
                        try:
                            payload, src, from_cache = fut.result()
                        except ScrapingError as exc:
                            with lock:
                                stats.errors += 1
                                if len(result.errors) < 50:
                                    result.errors.append(str(exc))
                            continue
                        except Exception as exc:
                            with lock:
                                stats.errors += 1
                                if len(result.errors) < 50:
                                    result.errors.append(f"@{username}: {exc}")
                            continue

                        _process_profile_result(
                            username,
                            payload,
                            src,
                            from_cache,
                            settings=settings,
                            stats=stats,
                            result=result,
                            kept=kept,
                            cache=cache,
                            lock=lock,
                        )
                        if profile_done % 10 == 0 or profile_done == profile_target:
                            emit(
                                "profiles",
                                f"Checked {profile_done}/{profile_target} profiles",
                                profile_done,
                                profile_target,
                            )

    emit("followers", "Followers collected", seed_total, seed_total)

    result.leads = _classify_against_master(kept, master_sources)
    stats.new_leads = sum(1 for it in result.leads if it["status"] == "new")
    stats.duplicate_leads = sum(1 for it in result.leads if it["status"] != "new")
    emit(
        "done",
        "Pipeline complete",
        profile_done,
        max(profile_target, profile_done),
    )
    return result
