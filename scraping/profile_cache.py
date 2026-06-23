"""Persistent cache of RapidAPI profile responses keyed by Instagram username."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "profile_cache.db"


class ProfileCache:
    """SQLite-backed store of profile JSON and last filter outcome per username."""

    def __init__(self, db_path: Path | str, *, max_age_days: int) -> None:
        self.db_path = Path(db_path)
        self.max_age_days = max(1, int(max_age_days))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with _lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS profile_cache (
                        username TEXT PRIMARY KEY,
                        profile_json TEXT NOT NULL,
                        filter_reason TEXT NOT NULL,
                        kept INTEGER NOT NULL,
                        source_url TEXT,
                        checked_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def get(self, username: str) -> dict[str, Any] | None:
        """Return a fresh cache entry or None if missing / expired."""
        key = (username or "").strip().lower().lstrip("@")
        if not key:
            return None
        with _lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM profile_cache WHERE username = ?",
                    (key,),
                ).fetchone()
        if row is None:
            return None
        checked_at = datetime.fromisoformat(str(row["checked_at"]))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - checked_at).total_seconds() / 86400.0
        if age_days > self.max_age_days:
            return None
        try:
            profile_json = json.loads(row["profile_json"])
        except ValueError:
            return None
        if not isinstance(profile_json, dict):
            return None
        return {
            "username": str(row["username"]),
            "profile_json": profile_json,
            "filter_reason": str(row["filter_reason"]),
            "kept": bool(row["kept"]),
            "source_url": str(row["source_url"] or ""),
            "checked_at": str(row["checked_at"]),
        }

    def put(
        self,
        username: str,
        profile_json: dict[str, Any],
        *,
        filter_reason: str,
        kept: bool,
        source_url: str = "",
    ) -> None:
        key = (username or "").strip().lower().lstrip("@")
        if not key or not isinstance(profile_json, dict):
            return
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(profile_json, ensure_ascii=False)
        with _lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO profile_cache (
                        username, profile_json, filter_reason, kept, source_url, checked_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        profile_json = excluded.profile_json,
                        filter_reason = excluded.filter_reason,
                        kept = excluded.kept,
                        source_url = excluded.source_url,
                        checked_at = excluded.checked_at
                    """,
                    (key, payload, filter_reason, 1 if kept else 0, source_url or "", now),
                )
                conn.commit()


_cache_singleton: ProfileCache | None = None
_cache_singleton_key: tuple[str, int] | None = None


def get_profile_cache(
    db_path: str | Path,
    *,
    max_age_days: int,
    enabled: bool,
) -> ProfileCache | None:
    if not enabled:
        return None
    global _cache_singleton, _cache_singleton_key
    path = str(Path(db_path) if db_path else _DEFAULT_PATH)
    key = (path, max(1, int(max_age_days)))
    if _cache_singleton is None or _cache_singleton_key != key:
        _cache_singleton = ProfileCache(path, max_age_days=key[1])
        _cache_singleton_key = key
    return _cache_singleton
