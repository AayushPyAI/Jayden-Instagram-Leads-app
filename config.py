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
