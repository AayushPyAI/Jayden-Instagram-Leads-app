"""Central settings — avoid scattering magic strings."""

import json
import os

# Optional explicit Gemini model override.
# Leave empty to auto-discover an available model at runtime.
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash").strip()
MAX_IMAGE_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "1600"))
# Screenshots per /api/process request (client sends multiple requests for large batches).
PROCESS_CHUNK_SIZE = max(1, int(os.getenv("PROCESS_CHUNK_SIZE", "25")))
# Hard cap enforced by the API (protects memory / request duration).
MAX_SCREENSHOTS_PER_REQUEST = max(1, int(os.getenv("MAX_SCREENSHOTS_PER_REQUEST", "50")))
# Concurrent Gemini vision calls per batch (I/O-bound; tune down if you hit 429 rate limits).
GEMINI_CONCURRENCY = max(1, int(os.getenv("GEMINI_CONCURRENCY", "8")))
# Retries per model candidate on transient Gemini errors (429, 5xx, timeouts).
GEMINI_MAX_RETRIES = max(1, int(os.getenv("GEMINI_MAX_RETRIES", "2")))
GEMINI_RETRY_BACKOFF_S = max(0.1, float(os.getenv("GEMINI_RETRY_BACKOFF_S", "1.5")))
# Hard cap per Gemini API call (seconds) — prevents hung requests from stalling batches.
GEMINI_TIMEOUT_S = max(5, int(os.getenv("GEMINI_TIMEOUT_S", "25")))
# Optional single fallback model (tried only after primary fails). Leave empty to use primary only.
GEMINI_FALLBACK_MODEL = (os.getenv("GEMINI_FALLBACK_MODEL") or "").strip()
# When false, skip slow genai.list_models() discovery at runtime.
GEMINI_DISCOVER_MODELS = (os.getenv("GEMINI_DISCOVER_MODELS", "false").strip().lower() in {"1", "true", "yes"})

# Suggested filename for "save as new workbook" (without path).
EXPORT_FILENAME_STEM = (os.getenv("EXPORT_FILENAME_STEM") or "instagram_leads").strip() or "instagram_leads"

# Column order when building a fresh .xlsx from staged leads (comma-separated env override).
# Default omits Error and puts Image Name last; merge into existing workbooks is unchanged.
STAGED_LEAD_EXPORT_COLUMNS: tuple[str, ...] = tuple(
    col.strip()
    for col in os.getenv(
        "STAGED_LEAD_EXPORT_COLUMNS",
        "Business Name,Mobile,Email,Instagram,Date & Time,Duplicate Source File,Duplicate Source Row,Image Name",
    ).split(",")
    if col.strip()
)


def staged_export_column_keys() -> list[str]:
    """Column keys for new-sheet export and results table (no Error; Image Name last)."""
    cols = [c for c in STAGED_LEAD_EXPORT_COLUMNS if str(c).strip().lower() != "error"]
    if "Image Name" in cols:
        cols = [c for c in cols if c != "Image Name"] + ["Image Name"]
    return cols


def staged_export_new_workbook_column_pairs() -> list[tuple[str, str]]:
    """
    (Excel column title, internal row dict key) for Save as New / pending-download workbooks.

    Override with env STAGED_LEAD_NEW_WORKBOOK_COLUMN_MAP_JSON as a JSON array of
    [header, rowKey] pairs, e.g. [["Instagram Usernames","Instagram"],["Phone Numbers","Mobile"],...].
    """
    raw = os.getenv("STAGED_LEAD_NEW_WORKBOOK_COLUMN_MAP_JSON", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            out: list[tuple[str, str]] = []
            for item in parsed:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    header = str(item[0]).strip()
                    row_key = str(item[1]).strip()
                    if header and row_key:
                        out.append((header, row_key))
            if out:
                return out
    return [
        ("Instagram Usernames", "Instagram"),
        ("Phone Numbers", "Mobile"),
        ("Business Name", "Business Name"),
        ("Email", "Email"),
        ("Date & Time", "Date & Time"),
        ("Duplicate Source File", "Duplicate Source File"),
        ("Duplicate Source Row", "Duplicate Source Row"),
        ("Image Name", "Image Name"),
    ]


# Minimum core length for fuzzy Instagram duplicate matching (numbered / near-miss handles).
IG_FUZZY_MIN_CORE_LEN = max(1, int(os.getenv("IG_FUZZY_MIN_CORE_LEN", "6")))

# Label shown for duplicate-of-self rows when deduping within one upload batch.
BATCH_DEDUPE_SOURCE_LABEL = (os.getenv("BATCH_DEDUPE_SOURCE_LABEL") or "This batch").strip() or "This batch"


def _workbook_folder_env(name: str, default: str) -> str:
    raw = (os.getenv(name) or default).strip().strip("/\\")
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        return default
    return raw


def workbook_folder_master_id() -> str:
    return _workbook_folder_env("WORKBOOK_FOLDER_MASTER", "MASTER")


def workbook_folder_new_id() -> str:
    return _workbook_folder_env("WORKBOOK_FOLDER_NEW", "NEW")


def workbook_folder_duplicate_id() -> str:
    return _workbook_folder_env("WORKBOOK_FOLDER_DUPLICATE", "DUPLICATE")


def workbook_folder_ids() -> tuple[str, str, str]:
    return (
        workbook_folder_master_id(),
        workbook_folder_new_id(),
        workbook_folder_duplicate_id(),
    )


def workbook_folder_display_name(folder_id: str) -> str:
    labels = {
        workbook_folder_master_id(): "MASTER FOLDER",
        workbook_folder_new_id(): "NEW FOLDER",
        workbook_folder_duplicate_id(): "DUPLICATE FOLDER",
    }
    return labels.get(folder_id, folder_id)


def is_workbook_folder_id(folder_id: str) -> bool:
    return folder_id in workbook_folder_ids()


def max_workbook_upload_bytes() -> int:
    try:
        return max(1_048_576, int(os.getenv("MAX_WORKBOOK_UPLOAD_BYTES", str(80 * 1024 * 1024))))
    except ValueError:
        return 80 * 1024 * 1024


EXTRACTION_SYSTEM_INSTRUCTION = """You read Instagram profile screenshots (mobile UI).
Extract ONLY what is clearly visible.

Return a single JSON object with exactly these keys:
- "business_name": Business/profile display name. Use "" if not visible.
- "mobile": Phone number exactly as shown (may include spaces, +, dashes, parentheses). Use "" if missing, blurry, cropped, or not confident. The app stores AU-style numbers as 0123-456-789 (10 digits) or 1234-567-89 (9 digits).
- "email": Public email visible in screenshot. Use "" if not visible.
- "instagram": Instagram handle without @. Use "" if not visible.
- "notes": Short optional note if something is ambiguous; otherwise "".

Rules:
- Never guess any field.
- If phone is unclear, mobile must be "".
- If email is unclear, email must be "".
- Australian mobiles often appear as 04XX XXX XXX or +61 4XX XXX XXX. When visible, include the leading 0 in mobile (10 digits after the 0, e.g. 0412345678). Do not drop the leading 0.
- Output JSON only, no markdown."""


# ──────────────────────────────────────────────────────────────────────────
# URL Lead Pipeline (Apify followers → RapidAPI profile → filter → leads)
# ──────────────────────────────────────────────────────────────────────────


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


APIFY_TOKEN = (os.getenv("APIFY_TOKEN") or "").strip()
APIFY_FOLLOWERS_ACTOR_ID = (os.getenv("APIFY_FOLLOWERS_ACTOR_ID") or "lezdhAFfa4H5zAb2A").strip()
RAPIDAPI_KEY = (os.getenv("RAPIDAPI_KEY") or "").strip()
RAPIDAPI_HOST = (os.getenv("RAPIDAPI_HOST") or "instagram120.p.rapidapi.com").strip()

# The exact profile endpoint differs per RapidAPI listing; copy these from the
# playground's code snippet if the defaults do not match.
RAPIDAPI_PROFILE_PATH = (os.getenv("RAPIDAPI_PROFILE_PATH") or "api/instagram/userInfoByUsername").strip().lstrip("/")
RAPIDAPI_PROFILE_METHOD = (os.getenv("RAPIDAPI_PROFILE_METHOD") or "POST").strip().upper()
RAPIDAPI_USERNAME_PARAM = (os.getenv("RAPIDAPI_USERNAME_PARAM") or "username").strip()

URL_PIPELINE_MAX_SEED_URLS = _env_int("URL_PIPELINE_MAX_SEED_URLS", 20)
APIFY_MAX_FOLLOWERS_PER_URL = _env_int("APIFY_MAX_FOLLOWERS_PER_URL", 400)
URL_PIPELINE_CONCURRENCY = _env_int("URL_PIPELINE_CONCURRENCY", 5)
RAPIDAPI_DAILY_CALL_CAP = _env_int("RAPIDAPI_DAILY_CALL_CAP", 8000)
RAPIDAPI_TIMEOUT_S = _env_int("RAPIDAPI_TIMEOUT_S", 25, minimum=5)
RAPIDAPI_MAX_RETRIES = _env_int("RAPIDAPI_MAX_RETRIES", 2)
RAPIDAPI_RETRY_BACKOFF_S = _env_float("RAPIDAPI_RETRY_BACKOFF_S", 1.5, minimum=0.1)
APIFY_TIMEOUT_S = _env_int("APIFY_TIMEOUT_S", 120, minimum=10)
SKIP_PRIVATE_ACCOUNTS = _env_bool("SKIP_PRIVATE_ACCOUNTS", True)
APIFY_DEMO_FALLBACK = _env_bool("APIFY_DEMO_FALLBACK", True)


def url_pipeline_settings() -> dict[str, object]:
    """Snapshot of pipeline settings (no secrets) for diagnostics / logging."""
    return {
        "apify_actor_id": APIFY_FOLLOWERS_ACTOR_ID,
        "rapidapi_host": RAPIDAPI_HOST,
        "max_seed_urls": URL_PIPELINE_MAX_SEED_URLS,
        "max_followers_per_url": APIFY_MAX_FOLLOWERS_PER_URL,
        "concurrency": URL_PIPELINE_CONCURRENCY,
        "rapidapi_daily_call_cap": RAPIDAPI_DAILY_CALL_CAP,
        "rapidapi_timeout_s": RAPIDAPI_TIMEOUT_S,
        "rapidapi_max_retries": RAPIDAPI_MAX_RETRIES,
        "apify_timeout_s": APIFY_TIMEOUT_S,
        "skip_private_accounts": SKIP_PRIVATE_ACCOUNTS,
        "apify_demo_fallback": APIFY_DEMO_FALLBACK,
    }


def url_pipeline_credentials_status() -> dict[str, bool]:
    """Whether each required credential is present (booleans only, never the value)."""
    return {
        "apify_token_set": bool(APIFY_TOKEN),
        "apify_actor_id_set": bool(APIFY_FOLLOWERS_ACTOR_ID),
        "rapidapi_key_set": bool(RAPIDAPI_KEY),
        "rapidapi_host_set": bool(RAPIDAPI_HOST),
    }


def url_pipeline_enabled() -> bool:
    """True only when all credentials needed to run the pipeline are present."""
    return all(url_pipeline_credentials_status().values())
