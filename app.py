"""Custom web app: clean UI with drag/drop and results table."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    MAX_IMAGE_SIDE,
    MAX_SCREENSHOTS_PER_REQUEST,
    PROCESS_CHUNK_SIZE,
    is_workbook_folder_id,
    max_workbook_upload_bytes,
    staged_export_column_keys,
    workbook_folder_display_name,
    workbook_folder_duplicate_id,
    workbook_folder_ids,
    workbook_folder_master_id,
    workbook_folder_new_id,
)
from processor import (
    build_master_records_from_workbook_sources,
    match_lead_rows_to_combined_workbooks,
    master_records_with_staged_batch,
    merge_staged_rows_into_workbook,
    pending_export_rows,
    process_screenshots_only_async,
    staged_rows_to_new_workbook_bytes,
)
from logging_config import get_logger, log_fields, request_id_var, setup_logging
from workbook_storage import get_workbook_storage, normalize_api_key

logger = get_logger("api")

PENDING_RESULTS: dict[str, dict[str, object]] = {}


def _duplicate_workbooks_cache_key(names: list[str]) -> str:
    return "|".join(sorted(names)) if names else "__all__"


def _build_workbook_master_records(
    sources: list[tuple[str, bytes]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    idx = build_master_records_from_workbook_sources(sources)
    if not idx.get("ok"):
        return None, str(idx.get("error", "Workbook index failed."))
    return list(idx["records"]), None


def _workbooks() -> Any:
    return get_workbook_storage()


def _storage_meta() -> dict[str, str]:
    store = _workbooks()
    return {"storage": store.storage_kind(), "storage_uri": store.storage_display()}


def _sanitize_export_stem(raw: str) -> str:
    stem = re.sub(r"[^\w\-.]+", "_", (raw or "").strip()).strip("._")
    if not stem:
        raise HTTPException(status_code=400, detail="Enter a name for the export.")
    return stem


def _export_suffix_for_folder(folder_id: str) -> str:
    if folder_id == workbook_folder_new_id():
        return "new_leads"
    if folder_id == workbook_folder_duplicate_id():
        return "duplicate_leads"
    return "leads"


def _export_suffix_for_scope(scope: str) -> str:
    return {
        "new": "new_leads",
        "duplicates": "duplicate_leads",
        "all": "all_leads",
    }.get(scope, "new_leads")


def _export_workbook_basename(
    export_stem: str,
    *,
    folder_id: str | None = None,
    scope: str | None = None,
) -> str:
    stem = _sanitize_export_stem(export_stem)
    if folder_id is not None:
        suffix = _export_suffix_for_folder(folder_id)
    elif scope is not None:
        suffix = _export_suffix_for_scope(scope)
    else:
        suffix = "leads"
    return f"{stem}_{suffix}.xlsx"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    store = get_workbook_storage()
    logger.info(
        "application_started %s",
        log_fields(
            storage=store.storage_kind(),
            storage_uri=store.storage_display(),
            workbook_folders=list(workbook_folder_ids()),
        ),
    )
    yield
    logger.info("application_shutdown")


app = FastAPI(title="Instagram Call List", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    started = time.perf_counter()
    logger.info(
        "http_request_started %s",
        log_fields(method=request.method, path=request.url.path),
    )
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed %s",
            log_fields(
                method=request.method,
                path=request.url.path,
                duration_ms=int((time.perf_counter() - started) * 1000),
            ),
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 500:
        logger.error(
            "http_request_completed %s",
            log_fields(
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            ),
        )
    elif response.status_code >= 400:
        logger.warning(
            "http_request_completed %s",
            log_fields(
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            ),
        )
    else:
        logger.info(
            "http_request_completed %s",
            log_fields(
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            ),
        )
    return response


def _safe_upload_workbook_basename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        name = "workbook.xlsx"
    if not name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload must use an .xlsx filename.")
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return name


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result_table_columns": staged_export_column_keys(),
            "process_chunk_size": PROCESS_CHUNK_SIZE,
            "max_image_side": MAX_IMAGE_SIDE,
        },
    )


@app.get("/api/excel-sheets")
async def excel_sheets() -> JSONResponse:
    """List .xlsx basenames in MASTER folder (duplicate-check sources only)."""
    store = _workbooks()
    sheets = store.list_master_workbook_names()
    return JSONResponse(
        {
            "sheets": sheets,
            "directory": store.storage_display(),
            "master_folder": workbook_folder_master_id(),
            **_storage_meta(),
        }
    )


def _workbook_index_payload(store: Any) -> dict[str, Any]:
    files = store.list_workbook_index()
    folders: list[dict[str, Any]] = []
    for folder_id in workbook_folder_ids():
        folder_files = [f for f in files if f.get("folder_id") == folder_id]
        folders.append(
            {
                "id": folder_id,
                "label": workbook_folder_display_name(folder_id),
                "files": folder_files,
            }
        )
    return {
        "scan_root": store.storage_display(),
        "folders": folders,
        "files": files,
        **_storage_meta(),
    }


@app.get("/api/codebase-xlsx-index")
async def codebase_xlsx_index() -> JSONResponse:
    store = _workbooks()
    return JSONResponse(_workbook_index_payload(store))


@app.get("/api/codebase-xlsx-file")
async def codebase_xlsx_download(path: str = Query(..., min_length=1, max_length=2048)) -> Response:
    store = _workbooks()
    try:
        body = store.read_workbook(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workbook not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = Path(path).name
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/codebase-xlsx-file")
async def codebase_xlsx_delete(path: str = Query(..., min_length=1, max_length=2048)) -> JSONResponse:
    store = _workbooks()
    try:
        if not store.workbook_exists(path):
            raise HTTPException(status_code=404, detail="Workbook not found.")
        store.delete_workbook(path)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not remove workbook.") from exc
    return JSONResponse(
        {
            "ok": True,
            "message": f"Removed {Path(path).name} from {store.storage_display()}.",
            "relative_path": path,
            **_storage_meta(),
        }
    )


@app.post("/api/codebase-xlsx-upload")
async def codebase_xlsx_upload(
    file: UploadFile = File(...),
    folder: str = Form(workbook_folder_master_id()),
) -> JSONResponse:
    store = _workbooks()
    folder_id = (folder or "").strip().upper()
    if not is_workbook_folder_id(folder_id):
        raise HTTPException(
            status_code=400,
            detail=f"folder must be one of: {', '.join(workbook_folder_ids())}.",
        )
    raw_name = file.filename or "workbook.xlsx"
    basename = _safe_upload_workbook_basename(raw_name)
    body = await file.read()
    limit = max_workbook_upload_bytes()
    if len(body) > limit:
        raise HTTPException(status_code=400, detail="Workbook exceeds the configured upload size limit.")
    if len(body) < 4 or body[:2] != b"PK":
        raise HTTPException(status_code=400, detail="File does not look like a valid .xlsx workbook.")
    rel_key = f"{folder_id}/{basename}"
    try:
        rel = store.write_workbook(rel_key, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not save workbook.") from exc
    label = workbook_folder_display_name(folder_id)
    return JSONResponse(
        {
            "ok": True,
            "relative_path": rel,
            "folder": folder_id,
            "message": f"Saved to {label} ({rel}) in {store.storage_display()}.",
            **_storage_meta(),
        }
    )


def _parse_master_workbook_names(raw: str) -> list[str] | None:
    """
    None => use every .xlsx in the MASTER folder.
    Non-empty list => only those filenames (validated when loading bytes).
    """
    s = (raw or "").strip()
    if not s:
        return None
    try:
        data = json.loads(s)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid duplicate_workbooks JSON.") from exc
    if data is None:
        return None
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="duplicate_workbooks must be a JSON array of filenames.")
    names = [str(x).strip() for x in data if str(x).strip()]
    if not names:
        return None
    return names


def _master_workbook_sources(names: list[str] | None) -> list[tuple[str, bytes]]:
    """Duplicate-check sources: MASTER folder only."""
    store = _workbooks()
    out: list[tuple[str, bytes]] = []
    if names is None:
        for name in store.list_master_workbook_names():
            try:
                out.append((name, store.read_master_workbook(name)))
            except FileNotFoundError:
                continue
        return out
    for name in names:
        _validate_workbook_basename(name)
        if not store.master_workbook_exists(name):
            raise HTTPException(
                status_code=404,
                detail=f"Workbook not found in MASTER folder: {name}",
            )
        try:
            out.append((name, store.read_master_workbook(name)))
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Workbook not found in MASTER folder: {name}",
            ) from exc
    return out


@app.post("/api/process")
async def process(
    duplicate_workbooks: str = Form(""),
    continuation_token: str = Form(""),
    screenshots: list[UploadFile] = File(...),
) -> JSONResponse:
    started = time.perf_counter()
    upload_names = [f.filename or "image" for f in screenshots]
    cont = continuation_token.strip()

    if not screenshots:
        raise HTTPException(status_code=400, detail="Upload at least one screenshot.")

    logger.info(
        "api_process_accepted %s",
        log_fields(
            upload_count=len(screenshots),
            uploads=upload_names,
            continuation=bool(cont),
            continuation_token=cont or None,
        ),
    )

    screenshot_items: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    for file in screenshots:
        filename = file.filename or "image.png"
        ext = filename.lower().split(".")[-1]
        if ext not in {"png", "jpg", "jpeg", "webp"}:
            skipped.append(filename)
            continue
        screenshot_items.append((filename, await file.read()))

    if skipped:
        logger.warning(
            "api_process_skipped_files %s",
            log_fields(skipped=skipped, reason="unsupported_extension"),
        )

    if not screenshot_items:
        raise HTTPException(status_code=400, detail="No valid screenshot files were uploaded.")

    if len(screenshot_items) > MAX_SCREENSHOTS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Send at most {MAX_SCREENSHOTS_PER_REQUEST} screenshot(s) per request. "
                "Hard-refresh the page if you selected many files at once."
            ),
        )

    if not normalize_api_key(os.getenv("GEMINI_API_KEY")):
        logger.error("api_process_rejected %s", log_fields(reason="missing_gemini_api_key"))
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is missing in .env.")

    names = _parse_master_workbook_names(duplicate_workbooks)
    sources = _master_workbook_sources(names)
    dup_label = names if names else "all"

    logger.info(
        "api_process_starting %s",
        log_fields(
            valid_screenshot_count=len(screenshot_items),
            screenshots=[n for n, _ in screenshot_items],
            duplicate_workbooks=dup_label,
            continuation=bool(cont),
        ),
    )

    dup_cache_key = _duplicate_workbooks_cache_key(names)
    initial_master_records: list[dict[str, Any]] | None = None
    if cont:
        pending = PENDING_RESULTS.get(cont)
        if not pending:
            raise HTTPException(
                status_code=400,
                detail="Processing session expired. Process again from the start.",
            )
        cached_mr = pending.get("master_records")
        if (
            isinstance(cached_mr, list)
            and cached_mr
            and pending.get("dup_workbook_key") == dup_cache_key
        ):
            initial_master_records = list(cached_mr)
            logger.info(
                "api_process_continuation_cached_index %s",
                log_fields(master_record_count=len(initial_master_records)),
            )
        else:
            prior_new = pending.get("new_rows")
            if not isinstance(prior_new, list):
                prior_new = []
            records, err = _build_workbook_master_records(sources)
            if err or records is None:
                raise HTTPException(status_code=400, detail=err or "Workbook index failed.")
            initial_master_records = master_records_with_staged_batch(records, prior_new)
            logger.warning(
                "api_process_continuation_rebuilt_index %s",
                log_fields(master_record_count=len(initial_master_records)),
            )
    else:
        records, err = _build_workbook_master_records(sources)
        if err or records is None:
            raise HTTPException(status_code=400, detail=err or "Workbook index failed.")
        initial_master_records = records

    result = await process_screenshots_only_async(
        screenshot_items=screenshot_items,
        duplicate_workbook_sources=sources,
        initial_master_records=initial_master_records,
    )
    if not result.get("ok"):
        err = result.get("error", "Processing failed.")
        logger.error(
            "api_process_failed %s",
            log_fields(error=err, duration_ms=int((time.perf_counter() - started) * 1000)),
        )
        raise HTTPException(status_code=400, detail=err)

    chunk_new_rows = result.get("new_rows") or []
    if not isinstance(chunk_new_rows, list):
        raise HTTPException(status_code=500, detail="Invalid process result.")

    chunk_duplicate_rows = result.get("duplicate_rows") or []
    if not isinstance(chunk_duplicate_rows, list):
        chunk_duplicate_rows = []

    chunk_failed_rows = result.get("failed_rows") or []
    if not isinstance(chunk_failed_rows, list):
        chunk_failed_rows = []

    result_master = result.get("master_records")
    if not isinstance(result_master, list):
        result_master = initial_master_records or []

    if cont:
        token = cont
        pending = PENDING_RESULTS[token]
        merged_new = list(pending.get("new_rows") or [])
        merged_new.extend(chunk_new_rows)
        merged_dup = list(pending.get("duplicate_rows") or [])
        merged_dup.extend(chunk_duplicate_rows)
        pending["new_rows"] = merged_new
        pending["duplicate_rows"] = merged_dup
        pending["master_records"] = result_master
        pending["dup_workbook_key"] = dup_cache_key
        new_rows = merged_new
        duplicate_rows = merged_dup
    else:
        token = uuid.uuid4().hex
        new_rows = chunk_new_rows
        duplicate_rows = chunk_duplicate_rows
        PENDING_RESULTS[token] = {
            "new_rows": new_rows,
            "duplicate_rows": duplicate_rows,
            "master_records": result_master,
            "dup_workbook_key": dup_cache_key,
        }
    counts = result.get("counts") or {}

    logger.info(
        "api_process_succeeded %s",
        log_fields(
            token=token,
            duration_ms=int((time.perf_counter() - started) * 1000),
            **{k: counts.get(k) for k in ("new", "duplicates", "failed", "processed")},
        ),
    )

    return JSONResponse(
        {
            "token": token,
            "counts": result["counts"],
            "new_rows": chunk_new_rows,
            "duplicate_rows": chunk_duplicate_rows,
            "failed_rows": chunk_failed_rows,
        }
    )


def _validate_workbook_basename(filename: str) -> str:
    raw = filename.strip()
    if not raw or raw != Path(raw).name:
        raise HTTPException(status_code=400, detail="Invalid workbook name.")
    if not raw.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Target must be an .xlsx file.")
    return raw


def _allocate_workbook_name(store: Any, folder_id: str, desired: str) -> str:
    """Pick a non-colliding .xlsx basename under the given S3 folder."""
    base = _validate_workbook_basename(desired)
    if not store.workbook_exists(f"{folder_id}/{base}"):
        return base
    stem = Path(base).stem
    for n in range(2, 1000):
        candidate = f"{stem}_{n}.xlsx"
        if not store.workbook_exists(f"{folder_id}/{candidate}"):
            return candidate
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{ts}.xlsx"


def _export_batches_for_scope(
    new_rows: list[Any],
    duplicate_rows: list[Any],
    scope: str,
    *,
    master_sources: list[tuple[str, bytes]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Map save scope to (S3 folder id, rows) batches for NEW / DUPLICATE folders."""
    new_id = workbook_folder_new_id()
    dup_id = workbook_folder_duplicate_id()
    if scope == "all":
        batches: list[tuple[str, list[dict[str, Any]]]] = []
        new_only = pending_export_rows(new_rows, duplicate_rows, "new", workbook_sources=master_sources)
        dup_only = pending_export_rows(
            new_rows, duplicate_rows, "duplicates", workbook_sources=master_sources
        )
        if new_only:
            batches.append((new_id, new_only))
        if dup_only:
            batches.append((dup_id, dup_only))
        return batches
    folder_for_scope = {"new": new_id, "duplicates": dup_id}
    folder_id = folder_for_scope.get(scope)
    if not folder_id:
        raise HTTPException(status_code=400, detail="Invalid save scope.")
    rows = pending_export_rows(new_rows, duplicate_rows, scope, workbook_sources=master_sources)
    if not rows:
        return []
    return [(folder_id, rows)]


@app.post("/api/sheet-row-matches")
async def sheet_row_matches(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    """
    Match rows to workbook(s). Payload:
    - rows: required list of { Instagram, Mobile, Email, ... }
    - sheets: optional JSON array of workbook basenames; omit or [] = all .xlsx in MASTER folder
    - sheet: optional legacy single workbook name
    """
    rows_in = payload.get("rows")
    if not isinstance(rows_in, list):
        raise HTTPException(status_code=400, detail="Invalid rows.")

    sheets_param = payload.get("sheets")
    legacy_sheet = (payload.get("sheet") or "").strip()
    names: list[str] | None = None
    if isinstance(sheets_param, list):
        cleaned = [str(x).strip() for x in sheets_param if str(x).strip()]
        names = cleaned if cleaned else None
    elif legacy_sheet:
        names = [legacy_sheet]

    clean_rows: list[dict[str, Any]] = []
    for item in rows_in:
        if not isinstance(item, dict):
            clean_rows.append({"Instagram": "", "Mobile": "", "Email": ""})
            continue
        clean_rows.append(
            {
                "Instagram": item.get("Instagram", ""),
                "Mobile": item.get("Mobile", ""),
                "Email": item.get("Email", ""),
            }
        )

    sources = _master_workbook_sources(names)
    result = match_lead_rows_to_combined_workbooks(clean_rows, sources)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error", "Match failed.")))

    matches = result.get("matches")
    if not isinstance(matches, list):
        raise HTTPException(status_code=500, detail="Invalid match payload.")

    return JSONResponse({"matches": matches})


def _normalize_save_scope(raw: str | None) -> str:
    s = (raw or "new").strip().lower()
    if s not in {"new", "duplicates", "all"}:
        raise HTTPException(status_code=400, detail="Invalid save scope. Use new, duplicates, or all.")
    return s


def _workbook_sources_for_pending_export(duplicate_workbooks_raw: str) -> list[tuple[str, bytes]]:
    names = _parse_master_workbook_names(duplicate_workbooks_raw)
    return _master_workbook_sources(names)


@app.get("/api/pending-workbook")
async def pending_workbook(
    token: str = Query(..., min_length=8),
    scope: str = Query("new"),
    export_name: str = Query(..., min_length=1),
    duplicate_workbooks: str = Query(""),
) -> Response:
    pending = PENDING_RESULTS.get(token)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending result was found. Process again.")

    new_rows = pending.get("new_rows")
    duplicate_rows = pending.get("duplicate_rows")
    if not isinstance(new_rows, list) or not isinstance(duplicate_rows, list):
        raise HTTPException(status_code=500, detail="Pending result payload is invalid.")

    scope_n = _normalize_save_scope(scope)
    try:
        sources = _workbook_sources_for_pending_export(duplicate_workbooks)
        rows = pending_export_rows(new_rows, duplicate_rows, scope_n, workbook_sources=sources)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not rows:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nothing to export for this row filter. For example, if every lead matched a duplicate-check "
                "workbook, switch “Rows to save” to “Duplicates only” or “All”, then try again."
            ),
        )

    body = staged_rows_to_new_workbook_bytes(rows)
    download_name = _export_workbook_basename(export_name, scope=scope_n)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@app.post("/api/pending-clear")
async def pending_clear(token: str = Form(...)) -> JSONResponse:
    if not PENDING_RESULTS.pop(token, None):
        raise HTTPException(status_code=404, detail="No pending result was found.")
    return JSONResponse({"ok": True, "message": "Session cleared."})


@app.post("/api/save-pending-new")
async def save_pending_new(
    token: str = Form(...),
    save_scope: str = Form("new"),
    export_name: str = Form(...),
    duplicate_workbooks: str = Form(""),
) -> JSONResponse:
    """Write a new .xlsx to server storage (local dir or S3), not the browser filesystem."""
    pending = PENDING_RESULTS.get(token)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending result was found. Process again.")

    new_rows = pending.get("new_rows")
    duplicate_rows = pending.get("duplicate_rows")
    if not isinstance(new_rows, list) or not isinstance(duplicate_rows, list):
        raise HTTPException(status_code=500, detail="Pending result payload is invalid.")

    scope_n = _normalize_save_scope(save_scope)
    try:
        sources = _workbook_sources_for_pending_export(duplicate_workbooks)
        batches = _export_batches_for_scope(
            new_rows, duplicate_rows, scope_n, master_sources=sources
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not batches:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nothing to save for this row filter. For example, if every lead matched a duplicate-check "
                "workbook, switch “Rows to save” to “Duplicates only” or “All”, then try again."
            ),
        )

    store = _workbooks()
    saved_paths: list[str] = []
    total_rows = 0
    for folder_id, rows in batches:
        body = staged_rows_to_new_workbook_bytes(rows)
        desired = _export_workbook_basename(export_name, folder_id=folder_id)
        saved_name = _allocate_workbook_name(store, folder_id, desired)
        rel = store.write_workbook(f"{folder_id}/{saved_name}", body)
        saved_paths.append(rel)
        total_rows += len(rows)

    PENDING_RESULTS.pop(token, None)

    logger.info(
        "api_save_pending_new %s",
        log_fields(
            paths=saved_paths,
            save_scope=scope_n,
            row_count=total_rows,
            storage=store.storage_display(),
        ),
    )

    label_paths = ", ".join(
        f"{workbook_folder_display_name(p.split('/')[0])} ({p})" for p in saved_paths
    )
    msg = f"Saved {total_rows} row(s) to {store.storage_display()}: {label_paths}."

    return JSONResponse(
        {
            "ok": True,
            "paths": saved_paths,
            "message": msg,
            **_storage_meta(),
        }
    )


@app.post("/api/save-to-existing")
async def save_to_existing(
    token: str = Form(...),
    target_sheet: str = Form(...),
    save_scope: str = Form("new"),
    duplicate_workbooks: str = Form(""),
) -> JSONResponse:
    pending = PENDING_RESULTS.get(token)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending result was found. Process again.")

    new_rows = pending.get("new_rows")
    duplicate_rows = pending.get("duplicate_rows")
    if not isinstance(new_rows, list) or not isinstance(duplicate_rows, list):
        raise HTTPException(status_code=500, detail="Pending result payload is invalid.")

    scope_n = _normalize_save_scope(save_scope)
    try:
        sources = _workbook_sources_for_pending_export(duplicate_workbooks)
        staged = pending_export_rows(new_rows, duplicate_rows, scope_n, workbook_sources=sources)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not staged:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nothing to save for this row filter. If every lead matched a duplicate-check workbook, "
                "switch “Rows to save” to “Duplicates only” or “All”, then try again."
            ),
        )

    store = _workbooks()
    target_name = _validate_workbook_basename(target_sheet.strip())
    master_rel = store.master_relative_path(target_name)
    if not store.workbook_exists(master_rel):
        raise HTTPException(
            status_code=404,
            detail="Selected workbook was not found in the MASTER folder.",
        )

    try:
        existing = store.read_master_workbook(target_name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Selected workbook was not found in the MASTER folder.",
        ) from exc

    merged = merge_staged_rows_into_workbook(existing, staged)
    if not merged.get("ok"):
        raise HTTPException(status_code=400, detail=str(merged.get("error", "Could not merge into workbook.")))

    updated_bytes = merged.get("updated_master_bytes")
    if not isinstance(updated_bytes, (bytes, bytearray)):
        raise HTTPException(status_code=500, detail="Merge produced invalid data.")

    updated = bytes(updated_bytes)
    store.write_workbook(master_rel, updated)
    PENDING_RESULTS.pop(token, None)

    logger.info(
        "api_save_to_existing %s",
        log_fields(
            filename=target_name,
            save_scope=scope_n,
            row_count=len(staged),
            appended=int(merged.get("appended") or 0),
            skipped_duplicates=int(merged.get("skipped_duplicates") or 0),
            storage=store.storage_display(),
        ),
    )

    msg = f"Saved to {target_name} ({store.storage_display()})"
    skipped = int(merged.get("skipped_duplicates") or 0)
    appended = int(merged.get("appended") or 0)
    if skipped:
        msg += f" ({appended} new row(s); {skipped} skipped as duplicate(s) in file.)"
    return JSONResponse({"ok": True, "message": msg})


@app.post("/api/cancel")
async def cancel_results(token: str = Form(...)) -> JSONResponse:
    PENDING_RESULTS.pop(token, None)
    return JSONResponse({"ok": True, "message": "Pending results cancelled."})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
