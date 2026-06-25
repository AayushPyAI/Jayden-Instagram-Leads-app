# Project Knowledge Base

> Living document for developers. Updated whenever a feature is completed or a
> significant implementation decision is made. Tracked in git — commit alongside
> related code changes.

## How to use this file

- Each completed feature gets an entry under **Feature Log** (newest first).
- Record: what changed, why, files touched, and any scope changes.
- Capture non-obvious decisions, trade-offs, and gotchas.
- Cursor is configured (`.cursor/rules/update-knowledge.mdc`) to update this
  file automatically when meaningful work is done in the repo.

## Architecture Overview

| Module | Role |
|--------|------|
| `app.py` | FastAPI entrypoint — screenshot processing API, workbook CRUD, URL pipeline jobs |
| `processor.py` | Gemini vision extraction, duplicate matching, workbook merge/export |
| `config.py` | Central settings (Gemini, workbook folders, URL pipeline env vars) |
| `workbook_storage.py` | Abstract storage layer; S3 in production, local filesystem fallback |
| `scraping/` | Instagram URL pipeline — Apify followers → RapidAPI profiles → lead filter |
| `static/` + `templates/` | Frontend UI (AI Processing, Folders, URL pipeline tab) |
| `scripts/` | One-off helpers (`run_pipeline_once.py`, config checks, filter tests) |

### Workbook folders

Three logical folders (IDs configurable via env in `config.py`):

- **MASTER** — reference workbooks for duplicate detection and append targets
- **NEW** — exported new leads
- **DUPLICATE** — exported duplicate leads

### Two lead-ingestion paths

1. **Screenshot path** — upload Instagram profile screenshots → Gemini extracts
   business name, phone, email, handle → duplicate check against MASTER → save.
2. **URL pipeline path** — seed Instagram handles → per-URL Apify followers →
   RapidAPI enriches profiles (bounded concurrency, no giant in-memory list) →
   filter (business, no link, has phone) → dedupe against MASTER → same save flow.

## Key Decisions

- **Gemini model discovery off by default** (`GEMINI_DISCOVER_MODELS=false`) to
  avoid slow `list_models()` calls at startup; override with `GEMINI_MODEL`.
- **Duplicate matching** uses normalized Instagram handles and phone digits
  (`processor.py`); email is secondary.
- **URL pipeline gated on credentials** — `url_pipeline_enabled()` requires
  Apify token, actor ID, RapidAPI key, and host (`config.py`).
- **Apify demo fallback** — when `APIFY_DEMO_FALLBACK=true`, missing Apify
  credentials load fixture JSON from `scraping/fixtures/` for local dev.
- **Workbook storage is pluggable** — `get_workbook_storage()` picks S3 or local
  based on env; client data folders (`Feedback/`, `MASTER/`, etc.) are gitignored.

- **URL pipeline memory** — processes one seed URL at a time: Apify list is
  checked via a bounded thread pool, then discarded before the next seed. A small
  `seen` set dedupes across URLs; env caps (`APIFY_MAX_FOLLOWERS_PER_URL`,
  `RAPIDAPI_DAILY_CALL_CAP`, etc.) are unchanged. Apify still runs for all seeds
  when the profile cap is hit (same as before).

## Feature Log

### 2026-06-22 — URL pipeline streaming (memory)

- **Summary:** Refactored URL pipeline to avoid holding all followers and all
  profile tasks in memory at once.
- **Changes made:**
  - `scraping/url_pipeline.py` — per-seed Apify → profile check → discard;
    removed `_collect_candidates` mega-list phase
  - `KNOWLEDGE.md` — architecture note and feature log
- **Scope changes:** None; same API calls, caps, filters, and UI behavior.
- **Implementation notes:** `stats.candidates` still counts unique profiles
  queued for check; `stats.capped` when unique total exceeds
  `RAPIDAPI_DAILY_CALL_CAP`. Profile checking starts after each seed's Apify
  response instead of after all seeds.

### 2026-06-15 — Knowledge base & Cursor auto-update rule

- **Summary:** Added this file and a Cursor rule so the AI agent maintains project
  context across sessions and team changes.
- **Changes made:**
  - `KNOWLEDGE.md` — initial architecture snapshot and decision log
  - `.cursor/rules/update-knowledge.mdc` — instructs Cursor to update this file
    when features are completed
- **Scope changes:** None; documentation-only addition.
- **Implementation notes:** Rule uses `alwaysApply: true` so it applies in every
  Cursor session. File is git-tracked so teammates and CI share the same context.

## Known Issues / TODO

- (Add open items, tech debt, and follow-ups here as they arise)
