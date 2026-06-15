"""URL Lead Pipeline package.

Turns Instagram seed URLs into call-list leads:

    seed URLs → Apify (followers) → RapidAPI (profile detail)
              → filter (business + no link + phone) → dedupe → leads
"""

from scraping.apify_client import ScrapingError, fetch_followers, follower_usernames
from scraping.lead_extractor import extract_lead, find_phone_in_profile
from scraping.profile_filter import FilterResult, evaluate_profile, unwrap_user
from scraping.rapidapi_client import fetch_profile
from scraping.settings import PipelineSettings, load_settings
from scraping.url_pipeline import (
    PipelineResult,
    PipelineStats,
    parse_seed_handles,
    run_pipeline,
)

__all__ = [
    "PipelineSettings",
    "load_settings",
    "FilterResult",
    "evaluate_profile",
    "unwrap_user",
    "extract_lead",
    "find_phone_in_profile",
    "ScrapingError",
    "fetch_followers",
    "follower_usernames",
    "fetch_profile",
    "PipelineResult",
    "PipelineStats",
    "parse_seed_handles",
    "run_pipeline",
]
