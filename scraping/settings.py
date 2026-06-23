"""Immutable settings snapshot for the URL Lead Pipeline, read from config."""

from __future__ import annotations

from dataclasses import dataclass

import config


@dataclass(frozen=True)
class PipelineSettings:
    apify_token: str
    apify_actor_id: str
    rapidapi_key: str
    rapidapi_host: str
    rapidapi_profile_path: str
    rapidapi_profile_method: str
    rapidapi_username_param: str

    max_seed_urls: int
    max_followers_per_url: int
    concurrency: int
    rapidapi_daily_call_cap: int
    rapidapi_timeout_s: int
    rapidapi_max_retries: int
    rapidapi_retry_backoff_s: float
    apify_timeout_s: int
    skip_private_accounts: bool
    apify_demo_fallback: bool
    profile_cache_enabled: bool
    profile_cache_days: int
    profile_cache_path: str

    @property
    def enabled(self) -> bool:
        return bool(
            self.apify_token
            and self.apify_actor_id
            and self.rapidapi_key
            and self.rapidapi_host
        )

    def missing_credentials(self) -> list[str]:
        missing: list[str] = []
        if not self.apify_token:
            missing.append("APIFY_TOKEN")
        if not self.apify_actor_id:
            missing.append("APIFY_FOLLOWERS_ACTOR_ID")
        if not self.rapidapi_key:
            missing.append("RAPIDAPI_KEY")
        if not self.rapidapi_host:
            missing.append("RAPIDAPI_HOST")
        return missing

    def safe_snapshot(self) -> dict[str, object]:
        snap = config.url_pipeline_settings()
        snap.update(config.url_pipeline_credentials_status())
        snap["enabled"] = self.enabled
        return snap


def load_settings() -> PipelineSettings:
    return PipelineSettings(
        apify_token=config.APIFY_TOKEN,
        apify_actor_id=config.APIFY_FOLLOWERS_ACTOR_ID,
        rapidapi_key=config.RAPIDAPI_KEY,
        rapidapi_host=config.RAPIDAPI_HOST,
        rapidapi_profile_path=config.RAPIDAPI_PROFILE_PATH,
        rapidapi_profile_method=config.RAPIDAPI_PROFILE_METHOD,
        rapidapi_username_param=config.RAPIDAPI_USERNAME_PARAM,
        max_seed_urls=config.URL_PIPELINE_MAX_SEED_URLS,
        max_followers_per_url=config.APIFY_MAX_FOLLOWERS_PER_URL,
        concurrency=config.URL_PIPELINE_CONCURRENCY,
        rapidapi_daily_call_cap=config.RAPIDAPI_DAILY_CALL_CAP,
        rapidapi_timeout_s=config.RAPIDAPI_TIMEOUT_S,
        rapidapi_max_retries=config.RAPIDAPI_MAX_RETRIES,
        rapidapi_retry_backoff_s=config.RAPIDAPI_RETRY_BACKOFF_S,
        apify_timeout_s=config.APIFY_TIMEOUT_S,
        skip_private_accounts=config.SKIP_PRIVATE_ACCOUNTS,
        apify_demo_fallback=config.APIFY_DEMO_FALLBACK,
        profile_cache_enabled=config.PROFILE_CACHE_ENABLED,
        profile_cache_days=config.PROFILE_CACHE_DAYS,
        profile_cache_path=config.PROFILE_CACHE_PATH,
    )
