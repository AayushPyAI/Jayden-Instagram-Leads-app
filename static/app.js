const screenshotsInput = document.getElementById("screenshots");
const screenshotsFolderInput = document.getElementById("screenshotsFolder");
const chooseFolderBtn = document.getElementById("chooseFolderBtn");
const dropZone = document.getElementById("dropZone");
const fileCount = document.getElementById("fileCount");

/** Accumulated File objects — the native input replaces its list on each picker open. */
let screenshotSelection = [];

const SCREENSHOT_ACCEPT_EXT = new Set(["png", "jpg", "jpeg", "webp"]);
const processBtn = document.getElementById("processBtn");
const loadingModal = document.getElementById("loadingModal");
const loadingProgress = document.getElementById("loadingProgress");
const loadingProgressTrack = document.getElementById("loadingProgressTrack");
const loadingProgressBar = document.getElementById("loadingProgressBar");
const loadingDetail = document.getElementById("loadingDetail");
const loadingTitle = document.querySelector("#loadingModal .loading-title");
const errorText = document.getElementById("errorText");
const previewWrap = document.getElementById("previewRowWrap");
const previewRow = document.getElementById("previewRow");
const imageViewer = document.getElementById("imageViewer");
const viewerImage = document.getElementById("viewerImage");
const resultSection = document.getElementById("resultSection");
const tableBody = document.querySelector("#resultTable tbody");
const tableSummary = document.getElementById("tableSummary");
const pageSizeGroup = document.getElementById("pageSizeGroup");
const tablePagination = document.getElementById("tablePagination");
const paginationInfo = document.getElementById("paginationInfo");
const paginationFirst = document.getElementById("paginationFirst");
const paginationPrev = document.getElementById("paginationPrev");
const paginationPages = document.getElementById("paginationPages");
const paginationNext = document.getElementById("paginationNext");
const paginationLast = document.getElementById("paginationLast");
const newCount = document.getElementById("newCount");
const dupCount = document.getElementById("dupCount");
const copyNewLeadsBtn = document.getElementById("copyNewLeadsBtn");
const copyDupLeadsBtn = document.getElementById("copyDupLeadsBtn");
const copyAllLeadsBtn = document.getElementById("copyAllLeadsBtn");
const copyFeedback = document.getElementById("copyFeedback");
const dupCheckDropdown = document.getElementById("dupCheckDropdown");
const dupCheckButton = document.getElementById("dupCheckButton");
const dupCheckMenu = document.getElementById("dupCheckMenu");
const selectedDupCheckText = document.getElementById("selectedDupCheckText");
const saveModeDropdown = document.getElementById("saveModeDropdown");
const saveModeButton = document.getElementById("saveModeButton");
const saveModeMenu = document.getElementById("saveModeMenu");
const selectedSaveModeText = document.getElementById("selectedSaveModeText");
const saveRowScopeDropdown = document.getElementById("saveRowScopeDropdown");
const saveRowScopeButton = document.getElementById("saveRowScopeButton");
const saveRowScopeMenu = document.getElementById("saveRowScopeMenu");
const selectedSaveRowScopeText = document.getElementById("selectedSaveRowScopeText");
const saveTargetWrap = document.getElementById("saveTargetWrap");
const saveTargetDropdown = document.getElementById("saveTargetDropdown");
const saveTargetButton = document.getElementById("saveTargetButton");
const saveTargetMenu = document.getElementById("saveTargetMenu");
const selectedSaveTargetText = document.getElementById("selectedSaveTargetText");
const saveConfirmBtn = document.getElementById("saveConfirm");
const saveScopeHint = document.getElementById("saveScopeHint");
const cancelResultsBtn = document.getElementById("cancelResults");
const exportNameModal = document.getElementById("exportNameModal");
const exportNameInput = document.getElementById("exportNameInput");
const exportNamePreview = document.getElementById("exportNamePreview");
const exportNameError = document.getElementById("exportNameError");
const exportNameCancel = document.getElementById("exportNameCancel");
const exportNameConfirm = document.getElementById("exportNameConfirm");

const pageAi = document.getElementById("pageAi");
const pageFolders = document.getElementById("pageFolders");
const sidebarLinks = document.querySelectorAll(".sidebar-link");
const foldersRefresh = document.getElementById("foldersRefresh");
const foldersScanRoot = document.getElementById("foldersScanRoot");
const foldersError = document.getElementById("foldersError");
const foldersGroups = document.getElementById("foldersGroups");
const foldersFileInput = document.getElementById("foldersFileInput");

const TEXT_DUP_SOURCES_ALL = "All workbooks (default)";

const PROCESS_CHUNK_SIZE = (() => {
  const raw = document.querySelector('meta[name="process-chunk-size"]')?.getAttribute("content");
  const n = parseInt(String(raw || "25"), 10);
  return Number.isFinite(n) && n > 0 ? n : 25;
})();

const CLIENT_MAX_IMAGE_SIDE = (() => {
  const raw = document.querySelector('meta[name="max-image-side"]')?.getAttribute("content");
  const n = parseInt(String(raw || "1600"), 10);
  return Number.isFinite(n) && n > 0 ? n : 1600;
})();

/** Downscale screenshots before upload to cut network time and server memory. */
async function compressScreenshotForUpload(file) {
  if (!file || !(file instanceof File)) {
    return file;
  }
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (!SCREENSHOT_ACCEPT_EXT.has(ext)) {
    return file;
  }
  if (typeof createImageBitmap !== "function") {
    return file;
  }
  try {
    const bitmap = await createImageBitmap(file);
    const maxSide = CLIENT_MAX_IMAGE_SIDE;
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    if (scale >= 1 && file.size < 400_000) {
      bitmap.close();
      return file;
    }
    const mime = ext === "png" ? "image/png" : "image/jpeg";
    let blob = null;
    if (typeof OffscreenCanvas !== "undefined") {
      const canvas = new OffscreenCanvas(width, height);
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(bitmap, 0, 0, width, height);
        blob = await canvas.convertToBlob({ type: mime, quality: 0.88 });
      }
    } else {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(bitmap, 0, 0, width, height);
        blob = await new Promise((resolve) => canvas.toBlob(resolve, mime, 0.88));
      }
    }
    bitmap.close();
    if (!blob || blob.size >= file.size) {
      return file;
    }
    return new File([blob], file.name, { type: mime, lastModified: file.lastModified });
  } catch {
    return file;
  }
}

async function prepareScreenshotsForUpload(files) {
  const prepared = [];
  for (const file of files) {
    prepared.push(await compressScreenshotForUpload(file));
  }
  return prepared;
}

function chunkFiles(files, size) {
  const chunks = [];
  for (let i = 0; i < files.length; i += size) {
    chunks.push(files.slice(i, i + size));
  }
  return chunks;
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function fetchProcessWithRetry(formData, progress, maxAttempts = 4) {
  let lastResponse = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const response = await fetch("/api/process", {
      method: "POST",
      body: formData,
    });
    lastResponse = response;
    const retryable =
      response.status === 502 || response.status === 503 || response.status === 504;
    if (!retryable || attempt === maxAttempts) {
      return response;
    }
    if (progress) {
      setLoadingProgress(
        progress.current,
        progress.total,
        `Server busy, retrying (${attempt}/${maxAttempts - 1})...`
      );
    }
    await sleep(1500 * attempt);
  }
  return lastResponse;
}

async function parseProcessResponse(response) {
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (contentType.includes("application/json")) {
    return { payload: await response.json(), nonJsonBody: "" };
  }
  const nonJsonBody = await response.text();
  return { payload: null, nonJsonBody };
}

function processErrorMessage(response, payload, nonJsonBody, err) {
  if (err?.name === "AbortError") {
    return "Processing was cancelled.";
  }
  if (payload?.detail) {
    return typeof payload.detail === "string" ? payload.detail : "Failed to process files.";
  }
  if (response) {
    if (response.status === 504 || response.status === 502) {
      return "Server timed out while processing. Try fewer screenshots at once or retry.";
    }
    if (response.status >= 500) {
      return `Server error (${response.status}). Try again in a moment.`;
    }
    if (!response.ok) {
      return `Request failed (${response.status}).`;
    }
  }
  if (nonJsonBody && /<html/i.test(nonJsonBody)) {
    return "Server timed out or returned an invalid response. Large batches are processed in smaller groups — retry if this persists.";
  }
  if (err?.message) {
    return `Network error: ${err.message}`;
  }
  return "Unexpected error while processing files.";
}

let selectedDupCheckSheets = [];
let availableDupCheckSheets = [];

let pendingToken = "";
let exportNameResolver = null;

/** New/duplicate totals aligned with the status column (incl. sheet match overlay); used for stats + save scope hints. */
let lastProcessCounts = { new: 0, duplicates: 0 };

const TEXT_CHOOSE_SAVE = "Choose how to save…";
const TEXT_SELECT_SHEET = "Select Sheet";
const SAVE_MODE_CHOICES = [
  { value: "new", label: "Save as new workbook (server)" },
  { value: "existing", label: "Save to existing workbook (server)" },
];

const SAVE_ROW_SCOPE_CHOICES = [
  { value: "new", label: "New leads only" },
  { value: "duplicates", label: "Duplicates only" },
  { value: "all", label: "All (new + duplicates)" },
];

let selectedSaveMode = "";
let selectedSaveRowScope = "new";
let availableTargetSheets = [];
let selectedTargetSheet = "";
let saveModeMenuActiveIdx = -1;
let saveTargetMenuActiveIdx = -1;
let saveRowScopeMenuActiveIdx = -1;

const TABLE_PAGE_SIZE_OPTIONS = [3, 5, 10, 20, 50, 100];
let tableAllRows = [];
let tableCurrentPage = 1;
let tablePageSize = 10;

function visiblePageList(current, totalPages) {
  if (totalPages <= 1) {
    return totalPages === 1 ? [1] : [];
  }
  if (totalPages <= 9) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const delta = 2;
  const range = [];
  for (let i = 1; i <= totalPages; i += 1) {
    if (i === 1 || i === totalPages || (i >= current - delta && i <= current + delta)) {
      range.push(i);
    }
  }
  const out = [];
  let prev = 0;
  for (const i of range) {
    if (prev && i - prev > 1) {
      out.push(null);
    }
    out.push(i);
    prev = i;
  }
  return out;
}

function clampCurrentPage() {
  const total = tableAllRows.length;
  if (total === 0) {
    tableCurrentPage = 1;
    return;
  }
  const totalPages = Math.ceil(total / tablePageSize);
  tableCurrentPage = Math.max(1, Math.min(tableCurrentPage, totalPages));
}

let foldersIndexLoaded = false;

function formatFileSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  if (kb < 1024) return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  const mb = kb / 1024;
  return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
}

function groupFolderFiles(files) {
  const groups = new Map();
  for (const file of files) {
    const rel = String(file.relative_path || "");
    const idx = rel.lastIndexOf("/");
    const folder = idx === -1 ? "." : rel.slice(0, idx);
    if (!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(file);
  }
  return [...groups.entries()].sort((a, b) =>
    a[0].localeCompare(b[0], undefined, { sensitivity: "base" }),
  );
}

function setFoldersError(msg) {
  if (!msg) {
    foldersError.textContent = "";
    foldersError.classList.add("hidden");
    return;
  }
  foldersError.textContent = msg;
  foldersError.classList.remove("hidden");
}

function apiDetailMessage(data) {
  const d = data && data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    const parts = d.map((x) => (x && (x.msg || x.message)) || "").filter(Boolean);
    return parts.length ? parts.join(" ") : "Request failed.";
  }
  return "Request failed.";
}

let foldersUploadNotice = "";
let pendingUploadFolderId = "MASTER";

const WORKBOOK_FOLDER_DEFAULTS = [
  { id: "MASTER", label: "MASTER FOLDER", files: [] },
  { id: "NEW", label: "NEW FOLDER", files: [] },
  { id: "DUPLICATE", label: "DUPLICATE FOLDER", files: [] },
];

function resolveWorkbookFolders(payload) {
  const fromApi = Array.isArray(payload.folders) ? payload.folders : [];
  if (fromApi.length === 0) {
    return WORKBOOK_FOLDER_DEFAULTS.map((d) => ({ ...d, files: [] }));
  }
  const byId = new Map(fromApi.map((f) => [String(f.id || ""), f]));
  return WORKBOOK_FOLDER_DEFAULTS.map((def) => {
    const hit = byId.get(def.id);
    if (!hit) {
      return { ...def, files: [] };
    }
    return {
      id: def.id,
      label: String(hit.label || def.label),
      files: Array.isArray(hit.files) ? hit.files : [],
    };
  });
}

function renderFoldersIndex(payload) {
  if (foldersUploadNotice) {
    foldersScanRoot.textContent = foldersUploadNotice;
    foldersScanRoot.classList.remove("hidden");
  } else {
    foldersScanRoot.textContent = "";
    foldersScanRoot.classList.add("hidden");
  }

  const folders = resolveWorkbookFolders(payload);
  setFoldersError("");
  foldersGroups.textContent = "";
  let totalFiles = 0;

  for (const folder of folders) {
    const folderId = String(folder.id || "");
    const label = String(folder.label || folderId);
    const items = Array.isArray(folder.files) ? folder.files : [];
    totalFiles += items.length;
    const section = document.createElement("section");
    section.className = "folder-group";
    const head = document.createElement("div");
    head.className = "folder-group-head";
    const title = document.createElement("span");
    title.textContent = label;
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className =
      folderId === "MASTER" ? "btn-primary btn-compact" : "btn-secondary btn-compact";
    addBtn.textContent = folderId === "MASTER" ? "Upload workbook" : "Add workbook";
    addBtn.setAttribute("aria-label", `Add workbook to ${label}`);
    addBtn.addEventListener("click", () => {
      pendingUploadFolderId = folderId;
      foldersFileInput.click();
    });
    head.appendChild(title);
    head.appendChild(addBtn);
    const sorted = [...items].sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
    );
    if (sorted.length === 0) {
      const emptyMsg = document.createElement("p");
      emptyMsg.className = "folder-group-empty muted";
      emptyMsg.textContent =
        folderId === "MASTER"
          ? "No workbooks yet. Upload .xlsx files here for duplicate checking."
          : "No workbooks yet.";
      section.appendChild(head);
      section.appendChild(emptyMsg);
      foldersGroups.appendChild(section);
      continue;
    }
    const ul = document.createElement("ul");
    ul.className = "folder-file-list";
    for (const f of sorted) {
      const li = document.createElement("li");
      li.className = "folder-file-row";
      const main = document.createElement("div");
      main.className = "folder-file-main";
      const nameEl = document.createElement("span");
      nameEl.className = "folder-file-name";
      nameEl.textContent = f.name || "—";
      main.appendChild(nameEl);
      const aside = document.createElement("div");
      aside.className = "folder-file-aside";
      const meta = document.createElement("span");
      meta.className = "folder-file-meta";
      meta.textContent = formatFileSize(f.size_bytes);
      const actions = document.createElement("div");
      actions.className = "folder-file-actions";
      const relPath = String(f.relative_path || "");
      const downloadBtn = document.createElement("button");
      downloadBtn.type = "button";
      downloadBtn.className = "btn-secondary btn-compact";
      downloadBtn.textContent = "Download";
      downloadBtn.setAttribute("aria-label", `Download ${f.name || "workbook"}`);
      downloadBtn.addEventListener("click", () => {
        void downloadCodebaseWorkbook(relPath);
      });
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn-compact-danger";
      removeBtn.textContent = "Remove";
      removeBtn.setAttribute("aria-label", `Remove ${f.name || "workbook"}`);
      removeBtn.addEventListener("click", () => {
        void removeCodebaseWorkbook(relPath, f.name || "");
      });
      actions.appendChild(downloadBtn);
      actions.appendChild(removeBtn);
      aside.appendChild(meta);
      aside.appendChild(actions);
      li.appendChild(main);
      li.appendChild(aside);
      ul.appendChild(li);
    }
    section.appendChild(head);
    section.appendChild(ul);
    foldersGroups.appendChild(section);
  }
}

async function loadFoldersIndex() {
  setFoldersError("");
  try {
    const res = await fetch("/api/codebase-xlsx-index");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setFoldersError(apiDetailMessage(data) || "Could not load workbook index.");
      return;
    }
    renderFoldersIndex(data);
    foldersIndexLoaded = true;
  } catch (err) {
    setFoldersError("Could not load workbook index.");
  }
}

async function downloadCodebaseWorkbook(relativePath) {
  if (!relativePath) return;
  setFoldersError("");
  try {
    const u = new URL("/api/codebase-xlsx-file", window.location.origin);
    u.searchParams.set("path", relativePath);
    const res = await fetch(u.toString());
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setFoldersError(apiDetailMessage(data) || "Download failed.");
      return;
    }
    const blob = await res.blob();
    const slash = relativePath.lastIndexOf("/");
    let filename = slash === -1 ? relativePath : relativePath.slice(slash + 1);
    const cd = res.headers.get("Content-Disposition");
    if (cd) {
      const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
      const plain = /filename="([^"]+)"/i.exec(cd);
      if (star && star[1]) {
        try {
          filename = decodeURIComponent(star[1].trim());
        } catch (e) {
          /* keep basename */
        }
      } else if (plain && plain[1]) {
        filename = plain[1].trim();
      }
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename || "workbook.xlsx";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    setFoldersError("Download failed.");
  }
}

async function removeCodebaseWorkbook(relativePath, displayName) {
  if (!relativePath) return;
  const label = displayName || relativePath;
  if (!confirm(`Remove "${label}" from disk? This cannot be undone.`)) return;
  setFoldersError("");
  try {
    const u = new URL("/api/codebase-xlsx-file", window.location.origin);
    u.searchParams.set("path", relativePath);
    const res = await fetch(u.toString(), { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setFoldersError(apiDetailMessage(data) || "Could not remove file.");
      return;
    }
    foldersIndexLoaded = false;
    await loadFoldersIndex();
    void populateDupCheckSheets();
  } catch (err) {
    setFoldersError("Could not remove file.");
  }
}

async function uploadCodebaseWorkbook(file, folderId) {
  if (!file) return;
  setFoldersError("");
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".xlsx")) {
    setFoldersError("Please choose an .xlsx file.");
    return;
  }
  const formData = new FormData();
  formData.append("file", file, file.name);
  formData.append("folder", folderId || pendingUploadFolderId || "MASTER");
  try {
    const res = await fetch("/api/codebase-xlsx-upload", { method: "POST", body: formData });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setFoldersError(apiDetailMessage(data) || "Upload failed.");
      return;
    }
    foldersUploadNotice =
      data.message != null ? String(data.message) : "Workbook saved to server storage.";
    foldersIndexLoaded = false;
    await loadFoldersIndex();
    void populateDupCheckSheets();
  } catch (err) {
    setFoldersError("Upload failed.");
  }
}

function setAppPage(pageId) {
  const isAi = pageId === "ai";
  const isFolders = pageId === "folders";
  if (!isAi && !isFolders) return;
  pageAi.classList.toggle("hidden", !isAi);
  pageFolders.classList.toggle("hidden", !isFolders);
  sidebarLinks.forEach((btn) => {
    const active = btn.dataset.page === pageId;
    btn.classList.toggle("is-active", active);
    if (active) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  if (isFolders && !foldersIndexLoaded) {
    void loadFoldersIndex();
  }
}

sidebarLinks.forEach((btn) => {
  btn.addEventListener("click", () => {
    const page = btn.dataset.page;
    if (page) setAppPage(page);
  });
});

foldersRefresh.addEventListener("click", () => {
  foldersIndexLoaded = false;
  void loadFoldersIndex();
});

foldersFileInput.addEventListener("change", () => {
  const file = foldersFileInput.files && foldersFileInput.files[0];
  const folderId = pendingUploadFolderId;
  foldersFileInput.value = "";
  if (file) void uploadCodebaseWorkbook(file, folderId);
});

function appendTextCell(tr, value, ellipsis = false) {
  const td = document.createElement("td");
  if (ellipsis) td.classList.add("cell-ellipsis");
  const s = value == null ? "" : String(value);
  td.textContent = s;
  if (s.length > 36) td.title = s;
  tr.appendChild(td);
}

function isTableDuplicateForStats(row) {
  if (row._serverStatus === "failed") {
    return false;
  }
  if (row._serverStatus === "batchDup") {
    return true;
  }
  const sheetDup = row._sheetDup != null && typeof row._sheetDup.excel_row === "number";
  return row._serverStatus === "duplicate" || sheetDup;
}

/** Match the status column so summary numbers agree with the table (incl. workbook overlay). */
function syncResultStatsFromTable() {
  let newN = 0;
  let dupN = 0;
  for (const row of tableAllRows) {
    if (row._serverStatus === "failed") {
      continue;
    }
    if (isTableDuplicateForStats(row)) {
      dupN += 1;
    } else {
      newN += 1;
    }
  }
  newCount.textContent = String(newN);
  dupCount.textContent = String(dupN);
  lastProcessCounts.new = newN;
  lastProcessCounts.duplicates = dupN;
  updateCopyLeadsButtonsState();
}

let copyFeedbackHideTimer = null;

function showCopyFeedback(message, isOk) {
  if (!copyFeedback) return;
  if (copyFeedbackHideTimer) {
    clearTimeout(copyFeedbackHideTimer);
    copyFeedbackHideTimer = null;
  }
  copyFeedback.textContent = message;
  copyFeedback.classList.remove("hidden");
  if (isOk) {
    copyFeedback.classList.add("copy-feedback--ok");
  } else {
    copyFeedback.classList.remove("copy-feedback--ok");
  }
  copyFeedbackHideTimer = window.setTimeout(() => {
    copyFeedback.classList.add("hidden");
    copyFeedbackHideTimer = null;
  }, 3200);
}

function cellClipboardValue(row, key) {
  const v = row[key];
  if (v == null) return "";
  return String(v).replace(/\r\n|\r|\n|\t/g, " ").trim();
}

function buildInstagramPhoneTsv(rows) {
  const lines = ["Instagram username\tPhone"];
  for (const row of rows) {
    lines.push(`${cellClipboardValue(row, "Instagram")}\t${cellClipboardValue(row, "Mobile")}`);
  }
  return lines.join("\n");
}

function getRowsForCopyLeads(filter) {
  if (filter === "new") {
    return tableAllRows.filter((r) => r._serverStatus !== "failed" && !isTableDuplicateForStats(r));
  }
  if (filter === "dup") {
    return tableAllRows.filter((r) => r._serverStatus !== "failed" && isTableDuplicateForStats(r));
  }
  return [...tableAllRows];
}

async function copyLeadsToClipboard(filter) {
  const subset = getRowsForCopyLeads(filter);
  if (subset.length === 0) {
    showCopyFeedback("Nothing to copy for this selection.", false);
    return;
  }
  const text = buildInstagramPhoneTsv(subset);
  try {
    await navigator.clipboard.writeText(text);
    const label = filter === "new" ? "new" : filter === "dup" ? "duplicate" : "all";
    showCopyFeedback(`Copied ${subset.length} row(s) to clipboard (${label}) — Instagram + Phone.`, true);
  } catch (err) {
    showCopyFeedback("Could not access the clipboard. Use HTTPS or allow clipboard permission.", false);
  }
}

function updateCopyLeadsButtonsState() {
  if (!copyNewLeadsBtn || !copyDupLeadsBtn || !copyAllLeadsBtn) return;
  const noData = tableAllRows.length === 0;
  copyNewLeadsBtn.disabled = noData || (lastProcessCounts.new || 0) === 0;
  copyDupLeadsBtn.disabled = noData || (lastProcessCounts.duplicates || 0) === 0;
  copyAllLeadsBtn.disabled = noData;
}

function duplicatePillTitle(row) {
  if (row._sheetDup != null && typeof row._sheetDup.excel_row === "number") {
    const fn = row._sheetDup.source_file || "workbook";
    return `Duplicate: ${fn} · spreadsheet row ${row._sheetDup.excel_row}`;
  }
  if (row._serverStatus === "duplicate") {
    const file = row["Duplicate Source File"] ?? "";
    const rno = row["Duplicate Source Row"];
    const rowStr = rno == null ? "" : String(rno);
    if (file && rowStr && rowStr !== "—") {
      return `Duplicate: ${file} · spreadsheet row ${rowStr}`;
    }
    if (file) {
      return `Duplicate: ${file}`;
    }
    return "Duplicate";
  }
  return "";
}

function appendStatusCell(tr, row) {
  const td = document.createElement("td");
  td.className = "col-status";
  if (row._serverStatus === "failed") {
    const span = document.createElement("span");
    span.className = "status-pill status-pill--failed";
    span.textContent = "Failed";
    const err = String(row.Error || row.error || "").trim();
    if (err) {
      span.title = err;
      span.setAttribute("aria-label", `Failed: ${err}`);
    }
    td.appendChild(span);
    tr.appendChild(td);
    return;
  }
  const sheetDup = row._sheetDup != null && typeof row._sheetDup.excel_row === "number";
  const isSheetDuplicate = row._serverStatus === "duplicate" || sheetDup;

  if (isSheetDuplicate) {
    const span = document.createElement("span");
    span.className = "status-pill status-pill--duplicate";
    span.textContent = "Duplicate";
    const tip = duplicatePillTitle(row) || "Duplicate";
    span.title = tip;
    span.setAttribute("aria-label", tip);
    td.appendChild(span);
    tr.appendChild(td);
    return;
  }
  if (row._serverStatus === "batchDup") {
    const span = document.createElement("span");
    span.className = "status-pill status-pill--batch";
    span.textContent = "In batch";
    span.title = "Same lead as another row in this upload (not in the server workbooks used for duplicate check).";
    span.setAttribute("aria-label", span.title);
    td.appendChild(span);
    tr.appendChild(td);
    return;
  }
  const span = document.createElement("span");
  span.className = "status-pill status-pill--new";
  span.textContent = "New";
  td.appendChild(span);
  tr.appendChild(td);
}

function resultsRowVariant(row) {
  if (row._serverStatus === "failed") {
    return "failed";
  }
  if (row._serverStatus === "duplicate") {
    return "duplicate";
  }
  if (row._sheetDup != null && typeof row._sheetDup.excel_row === "number") {
    return "duplicate";
  }
  if (row._serverStatus === "batchDup") {
    return "batchDup";
  }
  return "new";
}

async function refreshSheetDuplicateOverlay() {
  tableAllRows.forEach((row) => {
    delete row._sheetDup;
  });
  try {
    const rowsPayload = tableAllRows.map((row) => ({
      Instagram: row.Instagram,
      Mobile: row.Mobile,
      Email: row.Email,
    }));
    const body = {
      rows: rowsPayload,
      sheets: selectedDupCheckSheets.length > 0 ? [...selectedDupCheckSheets] : null,
    };
    const response = await fetch("/api/sheet-row-matches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(payload.detail || "Could not compare against server workbooks.");
      renderResultsTable();
      syncResultStatsFromTable();
      return;
    }
    const matches = payload.matches;
    if (!Array.isArray(matches) || matches.length !== tableAllRows.length) {
      setError("Unexpected response while checking duplicates.");
      renderResultsTable();
      syncResultStatsFromTable();
      return;
    }
    setError("");
    matches.forEach((m, i) => {
      const row = tableAllRows[i];
      if (!row || row._serverStatus === "failed" || row._serverStatus === "duplicate") {
        return;
      }
      if (m != null) {
        const raw = m.excel_row;
        const er = typeof raw === "number" ? raw : Number(raw);
        if (Number.isFinite(er)) {
          row._sheetDup = { excel_row: er, source_file: m.source_file };
        }
      } else {
        delete row._sheetDup;
      }
    });
    renderResultsTable();
    syncResultStatsFromTable();
  } catch (err) {
    setError("Could not compare against server workbooks.");
    renderResultsTable();
    syncResultStatsFromTable();
  }
}

let cachedResultTableColumnKeys = null;

function getResultTableColumnKeys() {
  if (cachedResultTableColumnKeys) {
    return cachedResultTableColumnKeys;
  }
  const headers = Array.from(document.querySelectorAll("#resultTable thead th"));
  cachedResultTableColumnKeys = headers.map((th) => th.textContent.trim());
  if (cachedResultTableColumnKeys.length === 0) {
    cachedResultTableColumnKeys = [
      "Status",
      "Business Name",
      "Mobile",
      "Email",
      "Instagram",
      "Date & Time",
      "Image Name",
    ];
  }
  return cachedResultTableColumnKeys;
}

function updatePaginationBar(total, totalPages, rangeStart, rangeEnd) {
  paginationInfo.textContent = `Showing ${rangeStart}–${rangeEnd} of ${total}`;
  paginationFirst.disabled = tableCurrentPage <= 1;
  paginationPrev.disabled = tableCurrentPage <= 1;
  paginationNext.disabled = tableCurrentPage >= totalPages;
  paginationLast.disabled = tableCurrentPage >= totalPages;

  paginationPages.innerHTML = "";
  visiblePageList(tableCurrentPage, totalPages).forEach((item) => {
    if (item === null) {
      const span = document.createElement("span");
      span.className = "pagination-gap";
      span.textContent = "…";
      span.setAttribute("aria-hidden", "true");
      paginationPages.appendChild(span);
      return;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pagination-num";
    btn.textContent = String(item);
    if (item === tableCurrentPage) {
      btn.classList.add("is-current");
      btn.setAttribute("aria-current", "page");
    }
    btn.addEventListener("click", () => {
      if (item === tableCurrentPage) return;
      tableCurrentPage = item;
      renderResultsTable();
    });
    paginationPages.appendChild(btn);
  });
}

function renderResultsTable() {
  clampCurrentPage();
  const total = tableAllRows.length;

  if (total === 0) {
    tableSummary.textContent = "No rows to display";
    tablePagination.classList.add("hidden");
    tableBody.innerHTML = "";
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = getResultTableColumnKeys().length;
    td.className = "table-empty-cell";
    td.textContent = "Process screenshots to see extracted leads here.";
    tr.appendChild(td);
    tableBody.appendChild(tr);
    updateCopyLeadsButtonsState();
    return;
  }

  const totalPages = Math.ceil(total / tablePageSize);
  const start = (tableCurrentPage - 1) * tablePageSize;
  const end = Math.min(start + tablePageSize, total);
  const slice = tableAllRows.slice(start, end);

  tableSummary.textContent = `${total} total row${total === 1 ? "" : "s"} · Page ${tableCurrentPage} of ${totalPages}`;
  tableBody.innerHTML = "";

  slice.forEach((row) => {
    const tr = document.createElement("tr");
    tr.classList.add("results-row", `results-row--${resultsRowVariant(row)}`);
    getResultTableColumnKeys().forEach((colKey) => {
      if (colKey === "Status") {
        appendStatusCell(tr, row);
        return;
      }
      appendTextCell(tr, row[colKey], true);
    });
    tableBody.appendChild(tr);
  });

  tablePagination.classList.remove("hidden");
  updatePaginationBar(total, totalPages, start + 1, end);
  updateCopyLeadsButtonsState();
}

function mapNewRowServerStatus(r) {
  if (r.batch_duplicate === true) {
    return { ...r, _status: "batchDup", _serverStatus: "batchDup" };
  }
  return { ...r, _status: "new", _serverStatus: "new" };
}

function setTableData(newRows, duplicateRows, failedRows = []) {
  tableAllRows = [
    ...newRows.map(mapNewRowServerStatus),
    ...duplicateRows.map((r) => ({ ...r, _status: "duplicate", _serverStatus: "duplicate" })),
    ...failedRows.map((r) => ({ ...r, _status: "failed", _serverStatus: "failed" })),
  ];
  tableCurrentPage = 1;
  renderResultsTable();
}

function syncPageSizeButtonStyles() {
  pageSizeGroup.querySelectorAll(".page-size-btn").forEach((b) => {
    b.classList.toggle("is-active", Number(b.dataset.size) === tablePageSize);
  });
}

function initPageSizeButtons() {
  pageSizeGroup.innerHTML = "";
  TABLE_PAGE_SIZE_OPTIONS.forEach((size) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "page-size-btn";
    btn.dataset.size = String(size);
    btn.textContent = String(size);
    btn.addEventListener("click", () => {
      if (tablePageSize === size) return;
      tablePageSize = size;
      syncPageSizeButtonStyles();
      clampCurrentPage();
      renderResultsTable();
    });
    pageSizeGroup.appendChild(btn);
  });
  syncPageSizeButtonStyles();
}

function setLoadingProgress(current, total, detail = "") {
  const showProgress = total > 0;
  if (loadingProgress) {
    loadingProgress.textContent = showProgress ? `${current} / ${total}` : "";
    loadingProgress.classList.toggle("hidden", !showProgress);
  }
  if (loadingProgressTrack && loadingProgressBar) {
    loadingProgressTrack.classList.toggle("hidden", !showProgress);
    const pct = showProgress ? Math.min(100, Math.round((current / total) * 100)) : 0;
    loadingProgressBar.style.width = `${pct}%`;
  }
  if (loadingDetail) {
    loadingDetail.textContent = detail || "";
  }
}

function setLoading(isLoading, options = {}) {
  loadingModal.classList.toggle("hidden", !isLoading);
  if (!isLoading) {
    setLoadingProgress(0, 0, "");
    if (loadingTitle) {
      loadingTitle.textContent = "Processing screenshots with AI...";
    }
    return;
  }
  if (options.message && loadingTitle) {
    loadingTitle.textContent = options.message;
  } else if (loadingTitle) {
    loadingTitle.textContent = "Processing screenshots with AI...";
  }
  if (options.showProgress === false) {
    setLoadingProgress(0, 0, options.detail || "");
  }
}

function setError(message) {
  if (!message) {
    errorText.classList.add("hidden");
    errorText.textContent = "";
    return;
  }
  errorText.classList.remove("hidden");
  errorText.textContent = message;
}

function isScreenshotFile(file) {
  if (!file || !file.name) {
    return false;
  }
  const ext = file.name.split(".").pop()?.toLowerCase() || "";
  return SCREENSHOT_ACCEPT_EXT.has(ext);
}

function screenshotFileKey(file) {
  return `${file.name}\0${file.size}\0${file.lastModified}`;
}

function syncScreenshotsInputFromSelection() {
  const dt = new DataTransfer();
  screenshotSelection.forEach((f) => {
    dt.items.add(f);
  });
  screenshotsInput.files = dt.files;
}

function mergeScreenshotsIntoSelection(incoming) {
  const seen = new Set(screenshotSelection.map(screenshotFileKey));
  let added = 0;
  for (const file of incoming) {
    if (!isScreenshotFile(file)) {
      continue;
    }
    const k = screenshotFileKey(file);
    if (seen.has(k)) {
      continue;
    }
    seen.add(k);
    screenshotSelection.push(file);
    added += 1;
  }
  return added;
}

function readDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const entries = [];
    const readBatch = () => {
      reader.readEntries(
        (batch) => {
          if (!batch.length) {
            resolve(entries);
            return;
          }
          entries.push(...batch);
          readBatch();
        },
        (err) => reject(err)
      );
    };
    readBatch();
  });
}

async function traverseFileSystemEntry(entry, outFiles) {
  if (!entry) {
    return;
  }
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    outFiles.push(file);
    return;
  }
  if (!entry.isDirectory) {
    return;
  }
  const reader = entry.createReader();
  const children = await readDirectoryEntries(reader);
  await Promise.all(children.map((child) => traverseFileSystemEntry(child, outFiles)));
}

async function collectFilesFromDataTransfer(dataTransfer) {
  if (!dataTransfer) {
    return [];
  }

  const items = dataTransfer.items;
  const getEntry = (item) => item.getAsEntry?.() || item.webkitGetAsEntry?.();
  if (items && items.length > 0 && typeof getEntry(items[0]) !== "undefined") {
    const entries = [];
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.kind !== "file") {
        continue;
      }
      const entry = getEntry(item);
      if (entry) {
        entries.push(entry);
      }
    }
    if (entries.length > 0) {
      const fromEntries = [];
      await Promise.all(entries.map((entry) => traverseFileSystemEntry(entry, fromEntries)));
      if (fromEntries.length > 0) {
        return fromEntries;
      }
    }
  }

  return Array.from(dataTransfer.files || []);
}

function applyIncomingScreenshots(incoming) {
  const list = Array.isArray(incoming) ? incoming : [];
  const imageCount = list.filter(isScreenshotFile).length;
  const added = mergeScreenshotsIntoSelection(list);
  syncScreenshotsInputFromSelection();
  updateFileCount();

  if (added > 0) {
    setError("");
    return added;
  }
  if (imageCount > 0) {
    setError("No new screenshots added (duplicates or already selected).");
  } else if (list.length > 0) {
    setError("No supported images found. Use PNG, JPG, JPEG, or WebP.");
  } else {
    setError("No files found in the drop.");
  }
  return added;
}

function selectedScreenshotCount() {
  return screenshotSelection.length;
}

function updateFileCount() {
  const count = selectedScreenshotCount();
  fileCount.textContent = count ? `${count} screenshot(s) selected` : "No screenshots selected";
  renderImagePreviews();
}

function removeScreenshotAtIndex(removeIndex) {
  if (removeIndex < 0 || removeIndex >= screenshotSelection.length) {
    return;
  }
  screenshotSelection.splice(removeIndex, 1);
  syncScreenshotsInputFromSelection();
  closeImageViewer();
  updateFileCount();
}

function truncateName(value, max = 22) {
  if (!value) {
    return "";
  }
  if (value.length <= max) {
    return value;
  }
  return `${value.slice(0, max - 1)}…`;
}

let selectedImagePreviews = [];

function clearImagePreviews() {
  selectedImagePreviews.forEach((item) => URL.revokeObjectURL(item.url));
  selectedImagePreviews = [];
}

function openImageViewer(url) {
  viewerImage.src = url;
  imageViewer.classList.remove("hidden");
}

function closeImageViewer() {
  imageViewer.classList.add("hidden");
  viewerImage.src = "";
}

function renderImagePreviews() {
  previewRow.innerHTML = "";
  clearImagePreviews();
  if (screenshotSelection.length === 0) {
    previewWrap.classList.add("hidden");
    return;
  }

  const frag = document.createDocumentFragment();
  screenshotSelection.forEach((file, index) => {
    const url = URL.createObjectURL(file);
    selectedImagePreviews.push({ url });

    const item = document.createElement("div");
    item.className = "preview-item";

    const card = document.createElement("button");
    card.type = "button";
    card.className = "preview-card";
    const img = document.createElement("img");
    img.className = "preview-thumb";
    img.src = url;
    img.alt = file.name;
    const nameEl = document.createElement("div");
    nameEl.className = "preview-name";
    nameEl.title = file.name;
    nameEl.textContent = truncateName(file.name);
    card.appendChild(img);
    card.appendChild(nameEl);
    card.addEventListener("click", () => openImageViewer(url));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "preview-remove";
    removeBtn.setAttribute("aria-label", `Remove ${file.name}`);
    removeBtn.title = "Remove from selection";
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      removeScreenshotAtIndex(index);
    });

    item.appendChild(card);
    item.appendChild(removeBtn);
    frag.appendChild(item);
  });
  previewRow.appendChild(frag);
  previewWrap.classList.remove("hidden");
}

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = "copy";
  }
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", async (event) => {
  event.preventDefault();
  dropZone.classList.remove("drag-over");
  try {
    const incoming = await collectFilesFromDataTransfer(event.dataTransfer);
    applyIncomingScreenshots(incoming);
  } catch {
    setError("Could not read dropped folder. Try choosing a folder instead.");
  }
});

screenshotsInput.addEventListener("change", () => {
  applyIncomingScreenshots(Array.from(screenshotsInput.files || []));
  screenshotsInput.value = "";
});

if (chooseFolderBtn && screenshotsFolderInput) {
  chooseFolderBtn.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    screenshotsFolderInput.click();
  });

  screenshotsFolderInput.addEventListener("change", () => {
    applyIncomingScreenshots(Array.from(screenshotsFolderInput.files || []));
    screenshotsFolderInput.value = "";
  });
}

imageViewer.addEventListener("click", (event) => {
  if (event.target === imageViewer) {
    closeImageViewer();
  }
});

function duplicateWorkbooksPayloadString() {
  return selectedDupCheckSheets.length > 0 ? JSON.stringify(selectedDupCheckSheets) : "null";
}

function closeSaveModeMenu() {
  saveModeDropdown.classList.remove("open");
  saveModeMenu.classList.add("hidden");
  saveModeDropdown.setAttribute("aria-expanded", "false");
}

function closeSaveRowScopeMenu() {
  saveRowScopeDropdown.classList.remove("open");
  saveRowScopeMenu.classList.add("hidden");
  saveRowScopeDropdown.setAttribute("aria-expanded", "false");
}

function openSaveModeMenu() {
  closeSaveTargetMenu();
  closeSaveRowScopeMenu();
  closeDupCheckMenu();
  saveModeDropdown.classList.add("open");
  saveModeMenu.classList.remove("hidden");
  saveModeDropdown.setAttribute("aria-expanded", "true");
  const idx = SAVE_MODE_CHOICES.findIndex((c) => c.value === selectedSaveMode);
  saveModeMenuActiveIdx = idx >= 0 ? idx : 0;
  highlightSaveModeOption();
}

function closeSaveTargetMenu() {
  saveTargetDropdown.classList.remove("open");
  saveTargetMenu.classList.add("hidden");
  saveTargetDropdown.setAttribute("aria-expanded", "false");
}

function openSaveTargetMenu() {
  closeSaveModeMenu();
  closeSaveRowScopeMenu();
  closeDupCheckMenu();
  saveTargetDropdown.classList.add("open");
  saveTargetMenu.classList.remove("hidden");
  saveTargetDropdown.setAttribute("aria-expanded", "true");
  if (availableTargetSheets.length === 0) {
    saveTargetMenuActiveIdx = -1;
    return;
  }
  const idx = availableTargetSheets.indexOf(selectedTargetSheet);
  saveTargetMenuActiveIdx = idx >= 0 ? idx : 0;
  highlightSaveTargetOption();
}

function closeAllSaveDropdowns() {
  closeSaveModeMenu();
  closeSaveRowScopeMenu();
  closeSaveTargetMenu();
}

function highlightSaveModeOption() {
  const options = Array.from(saveModeMenu.querySelectorAll(".dropdown-item"));
  options.forEach((opt, idx) => {
    opt.classList.toggle("active", idx === saveModeMenuActiveIdx);
    if (idx === saveModeMenuActiveIdx) {
      opt.scrollIntoView({ block: "nearest" });
    }
  });
}

function highlightSaveTargetOption() {
  const options = Array.from(saveTargetMenu.querySelectorAll(".dropdown-item"));
  options.forEach((opt, idx) => {
    opt.classList.toggle("active", idx === saveTargetMenuActiveIdx);
    if (idx === saveTargetMenuActiveIdx) {
      opt.scrollIntoView({ block: "nearest" });
    }
  });
}

function highlightSaveRowScopeOption() {
  const options = Array.from(saveRowScopeMenu.querySelectorAll(".dropdown-item"));
  options.forEach((opt, idx) => {
    opt.classList.toggle("active", idx === saveRowScopeMenuActiveIdx);
    if (idx === saveRowScopeMenuActiveIdx) {
      opt.scrollIntoView({ block: "nearest" });
    }
  });
}

function openSaveRowScopeMenu() {
  closeSaveModeMenu();
  closeSaveTargetMenu();
  closeDupCheckMenu();
  saveRowScopeDropdown.classList.add("open");
  saveRowScopeMenu.classList.remove("hidden");
  saveRowScopeDropdown.setAttribute("aria-expanded", "true");
  const idx = SAVE_ROW_SCOPE_CHOICES.findIndex((c) => c.value === selectedSaveRowScope);
  saveRowScopeMenuActiveIdx = idx >= 0 ? idx : 0;
  highlightSaveRowScopeOption();
}

function renderSaveModeMenuItems() {
  saveModeMenu.innerHTML = "";
  const frag = document.createDocumentFragment();
  SAVE_MODE_CHOICES.forEach((opt, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dropdown-item";
    btn.dataset.value = opt.value;
    btn.dataset.index = String(idx);
    btn.setAttribute("role", "option");
    btn.textContent = opt.label;
    btn.addEventListener("click", () => {
      void selectSaveMode(opt.value);
    });
    frag.appendChild(btn);
  });
  saveModeMenu.appendChild(frag);
}

function renderSaveRowScopeMenuItems() {
  saveRowScopeMenu.innerHTML = "";
  const frag = document.createDocumentFragment();
  SAVE_ROW_SCOPE_CHOICES.forEach((opt, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dropdown-item";
    btn.dataset.value = opt.value;
    btn.dataset.index = String(idx);
    btn.setAttribute("role", "option");
    btn.textContent = opt.label;
    btn.addEventListener("click", () => {
      selectSaveRowScope(opt.value);
    });
    frag.appendChild(btn);
  });
  saveRowScopeMenu.appendChild(frag);
}

function renderSaveTargetMenuItems() {
  saveTargetMenu.innerHTML = "";
  const frag = document.createDocumentFragment();
  if (availableTargetSheets.length === 0) {
    const empty = document.createElement("div");
    empty.className = "dropdown-empty";
    empty.textContent = "No .xlsx files in MASTER folder";
    saveTargetMenu.appendChild(empty);
    return;
  }
  availableTargetSheets.forEach((name, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dropdown-item";
    btn.dataset.value = name;
    btn.dataset.index = String(idx);
    btn.setAttribute("role", "option");
    btn.textContent = name;
    btn.addEventListener("click", () => selectTargetSheet(name));
    frag.appendChild(btn);
  });
  saveTargetMenu.appendChild(frag);
}

async function selectSaveMode(value) {
  selectedSaveMode = value;
  const choice = SAVE_MODE_CHOICES.find((c) => c.value === value);
  selectedSaveModeText.textContent = choice ? choice.label : TEXT_CHOOSE_SAVE;
  closeSaveModeMenu();
  saveTargetWrap.classList.add("hidden");
  selectedTargetSheet = "";
  selectedSaveTargetText.textContent = TEXT_SELECT_SHEET;
  saveConfirmBtn.classList.add("hidden");
  if (value === "existing") {
    saveTargetWrap.classList.remove("hidden");
    await populateSaveTargetSheets();
  }
  updateSaveConfirmVisibility();
}

function selectSaveRowScope(value) {
  selectedSaveRowScope = value;
  const choice = SAVE_ROW_SCOPE_CHOICES.find((c) => c.value === value);
  selectedSaveRowScopeText.textContent = choice ? choice.label : SAVE_ROW_SCOPE_CHOICES[0].label;
  closeSaveRowScopeMenu();
  updateSaveConfirmVisibility();
}

function selectTargetSheet(name) {
  selectedTargetSheet = name;
  selectedSaveTargetText.textContent = name || TEXT_SELECT_SHEET;
  closeSaveTargetMenu();
  updateSaveConfirmVisibility();
}

function resetSavePanel() {
  selectedSaveMode = "";
  selectedSaveModeText.textContent = TEXT_CHOOSE_SAVE;
  selectedSaveRowScope = "new";
  selectedSaveRowScopeText.textContent = SAVE_ROW_SCOPE_CHOICES[0].label;
  selectedTargetSheet = "";
  selectedSaveTargetText.textContent = TEXT_SELECT_SHEET;
  lastProcessCounts = { new: 0, duplicates: 0 };
  saveTargetWrap.classList.add("hidden");
  availableTargetSheets = [];
  saveTargetMenu.innerHTML = "";
  saveConfirmBtn.classList.add("hidden");
  saveConfirmBtn.disabled = false;
  saveConfirmBtn.removeAttribute("aria-disabled");
  saveScopeHint.textContent = "";
  saveScopeHint.classList.add("hidden");
  closeAllSaveDropdowns();
}

function hasRowsForSaveScope(scope) {
  const s = scope || "new";
  const n = lastProcessCounts.new || 0;
  const d = lastProcessCounts.duplicates || 0;
  if (s === "new") {
    return n > 0;
  }
  if (s === "duplicates") {
    return d > 0 || n > 0;
  }
  return n + d > 0;
}

function updateSaveConfirmVisibility() {
  saveScopeHint.textContent = "";
  saveScopeHint.classList.add("hidden");

  let showConfirm = false;
  if (selectedSaveMode === "new") {
    showConfirm = true;
  } else if (selectedSaveMode === "existing" && selectedTargetSheet) {
    showConfirm = true;
  }

  if (!showConfirm) {
    saveConfirmBtn.classList.add("hidden");
    saveConfirmBtn.disabled = false;
    saveConfirmBtn.removeAttribute("aria-disabled");
    return;
  }

  saveConfirmBtn.classList.remove("hidden");

  const scope = selectedSaveRowScope || "new";
  if (!hasRowsForSaveScope(scope)) {
    saveConfirmBtn.disabled = true;
    saveConfirmBtn.setAttribute("aria-disabled", "true");
    if (scope === "new") {
      saveScopeHint.textContent =
        "Every lead matched your duplicate-check workbooks, so there are no “new only” rows to export. Choose “Duplicates only” or “All”, or narrow the duplicate-check list and process again.";
    } else {
      saveScopeHint.textContent =
        "No rows are available for this filter. Try another “Rows to save” option or process again.";
    }
    saveScopeHint.classList.remove("hidden");
    return;
  }

  saveConfirmBtn.disabled = false;
  saveConfirmBtn.removeAttribute("aria-disabled");
}

async function populateSaveTargetSheets() {
  try {
    const response = await fetch("/api/excel-sheets");
    const payload = await response.json();
    availableTargetSheets = payload.sheets || [];
  } catch (error) {
    availableTargetSheets = [];
  }
  renderSaveTargetMenuItems();
}

async function populateDupCheckSheets() {
  try {
    const response = await fetch("/api/excel-sheets");
    const payload = await response.json();
    availableDupCheckSheets = payload.sheets || [];
  } catch (error) {
    availableDupCheckSheets = [];
  }
  renderDupCheckMenuItems();
  updateDupCheckSummaryText();
}

function sortDedupeSheets(names) {
  return [...new Set(names)].sort((a, b) => a.localeCompare(b));
}

function updateDupCheckSummaryText() {
  if (selectedDupCheckSheets.length === 0) {
    selectedDupCheckText.textContent = TEXT_DUP_SOURCES_ALL;
  } else if (selectedDupCheckSheets.length === 1) {
    selectedDupCheckText.textContent = selectedDupCheckSheets[0];
  } else {
    selectedDupCheckText.textContent = `${selectedDupCheckSheets.length} workbooks`;
  }
}

function closeDupCheckMenu() {
  dupCheckDropdown.classList.remove("open");
  dupCheckMenu.classList.add("hidden");
  dupCheckDropdown.setAttribute("aria-expanded", "false");
}

function openDupCheckMenu() {
  closeSaveModeMenu();
  closeSaveRowScopeMenu();
  closeSaveTargetMenu();
  dupCheckDropdown.classList.add("open");
  dupCheckMenu.classList.remove("hidden");
  dupCheckDropdown.setAttribute("aria-expanded", "true");
}

function renderDupCheckMenuItems() {
  dupCheckMenu.innerHTML = "";
  const frag = document.createDocumentFragment();

  const hint = document.createElement("div");
  hint.className = "dropdown-dupe-hint";
  hint.textContent =
    "Leave all unchecked to compare against every .xlsx in the MASTER folder. Check one or more to limit duplicate checking.";
  frag.appendChild(hint);

  if (availableDupCheckSheets.length === 0) {
    const empty = document.createElement("div");
    empty.className = "dropdown-empty";
    empty.textContent = "No .xlsx files in MASTER folder";
    frag.appendChild(empty);
    dupCheckMenu.appendChild(frag);
    return;
  }

  availableDupCheckSheets.forEach((name) => {
    const row = document.createElement("label");
    row.className = "dropdown-check-row";
    const idSafe = `dupwb-${name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = idSafe;
    row.htmlFor = idSafe;
    cb.checked = selectedDupCheckSheets.includes(name);
    cb.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    cb.addEventListener("change", () => {
      const set = new Set(selectedDupCheckSheets);
      if (cb.checked) {
        set.add(name);
      } else {
        set.delete(name);
      }
      selectedDupCheckSheets = sortDedupeSheets(Array.from(set));
      updateDupCheckSummaryText();
      renderDupCheckMenuItems();
      if (!resultSection.classList.contains("hidden") && tableAllRows.length > 0) {
        void refreshSheetDuplicateOverlay();
      }
    });
    const span = document.createElement("span");
    span.className = "dropdown-check-label";
    span.textContent = name;
    row.appendChild(cb);
    row.appendChild(span);
    frag.appendChild(row);
  });
  dupCheckMenu.appendChild(frag);
}

saveModeButton.addEventListener("click", (event) => {
  event.stopPropagation();
  if (saveModeDropdown.classList.contains("open")) {
    closeSaveModeMenu();
    return;
  }
  openSaveModeMenu();
});

saveTargetButton.addEventListener("click", (event) => {
  event.stopPropagation();
  if (saveTargetDropdown.classList.contains("open")) {
    closeSaveTargetMenu();
    return;
  }
  openSaveTargetMenu();
});

saveRowScopeButton.addEventListener("click", (event) => {
  event.stopPropagation();
  if (saveRowScopeDropdown.classList.contains("open")) {
    closeSaveRowScopeMenu();
    return;
  }
  openSaveRowScopeMenu();
});

dupCheckButton.addEventListener("click", (event) => {
  event.stopPropagation();
  if (dupCheckDropdown.classList.contains("open")) {
    closeDupCheckMenu();
    return;
  }
  openDupCheckMenu();
});

dupCheckDropdown.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDupCheckMenu();
  }
});

saveModeDropdown.addEventListener("keydown", (event) => {
  if (SAVE_MODE_CHOICES.length === 0) {
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!saveModeDropdown.classList.contains("open")) {
      openSaveModeMenu();
    }
    saveModeMenuActiveIdx = Math.min(saveModeMenuActiveIdx + 1, SAVE_MODE_CHOICES.length - 1);
    highlightSaveModeOption();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (!saveModeDropdown.classList.contains("open")) {
      openSaveModeMenu();
    }
    saveModeMenuActiveIdx = Math.max(saveModeMenuActiveIdx - 1, 0);
    highlightSaveModeOption();
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (!saveModeDropdown.classList.contains("open")) {
      openSaveModeMenu();
      return;
    }
    const picked = SAVE_MODE_CHOICES[saveModeMenuActiveIdx];
    if (picked) {
      void selectSaveMode(picked.value);
    }
  } else if (event.key === "Escape") {
    closeSaveModeMenu();
  }
});

saveTargetDropdown.addEventListener("keydown", (event) => {
  if (availableTargetSheets.length === 0) {
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!saveTargetDropdown.classList.contains("open")) {
      openSaveTargetMenu();
    }
    saveTargetMenuActiveIdx = Math.min(saveTargetMenuActiveIdx + 1, availableTargetSheets.length - 1);
    highlightSaveTargetOption();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (!saveTargetDropdown.classList.contains("open")) {
      openSaveTargetMenu();
    }
    saveTargetMenuActiveIdx = Math.max(saveTargetMenuActiveIdx - 1, 0);
    highlightSaveTargetOption();
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (!saveTargetDropdown.classList.contains("open")) {
      openSaveTargetMenu();
      return;
    }
    const picked = availableTargetSheets[saveTargetMenuActiveIdx];
    if (picked) {
      selectTargetSheet(picked);
    }
  } else if (event.key === "Escape") {
    closeSaveTargetMenu();
  }
});

saveRowScopeDropdown.addEventListener("keydown", (event) => {
  if (SAVE_ROW_SCOPE_CHOICES.length === 0) {
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!saveRowScopeDropdown.classList.contains("open")) {
      openSaveRowScopeMenu();
    }
    saveRowScopeMenuActiveIdx = Math.min(saveRowScopeMenuActiveIdx + 1, SAVE_ROW_SCOPE_CHOICES.length - 1);
    highlightSaveRowScopeOption();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (!saveRowScopeDropdown.classList.contains("open")) {
      openSaveRowScopeMenu();
    }
    saveRowScopeMenuActiveIdx = Math.max(saveRowScopeMenuActiveIdx - 1, 0);
    highlightSaveRowScopeOption();
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (!saveRowScopeDropdown.classList.contains("open")) {
      openSaveRowScopeMenu();
      return;
    }
    const picked = SAVE_ROW_SCOPE_CHOICES[saveRowScopeMenuActiveIdx];
    if (picked) {
      selectSaveRowScope(picked.value);
    }
  } else if (event.key === "Escape") {
    closeSaveRowScopeMenu();
  }
});

document.addEventListener("click", (event) => {
  if (!saveModeDropdown.contains(event.target)) {
    closeSaveModeMenu();
  }
  if (!saveRowScopeDropdown.contains(event.target)) {
    closeSaveRowScopeMenu();
  }
  if (!saveTargetDropdown.contains(event.target)) {
    closeSaveTargetMenu();
  }
  if (!dupCheckDropdown.contains(event.target)) {
    closeDupCheckMenu();
  }
});

function sanitizeExportStem(raw) {
  return String(raw || "")
    .trim()
    .replace(/[^\w\-.]+/g, "_")
    .replace(/^[._]+|[._]+$/g, "");
}

function expectedExportFilenames(stem) {
  const safe = sanitizeExportStem(stem);
  if (!safe) {
    return [];
  }
  const scope = selectedSaveRowScope || "new";
  if (scope === "all") {
    return [`${safe}_new_leads.xlsx`, `${safe}_duplicate_leads.xlsx`];
  }
  const suffix = scope === "duplicates" ? "duplicate_leads" : "new_leads";
  return [`${safe}_${suffix}.xlsx`];
}

function updateExportNamePreview() {
  const names = expectedExportFilenames(exportNameInput.value);
  if (names.length === 0) {
    exportNamePreview.textContent = "";
    return;
  }
  exportNamePreview.textContent =
    names.length === 1 ? `Will save as: ${names[0]}` : `Will save as: ${names.join(" and ")}`;
}

function closeExportNameModal(result) {
  exportNameModal.classList.add("hidden");
  exportNameError.classList.add("hidden");
  exportNameError.textContent = "";
  document.body.classList.remove("modal-open");
  const resolve = exportNameResolver;
  exportNameResolver = null;
  if (resolve) {
    resolve(result);
  }
}

function openExportNameModal() {
  return new Promise((resolve) => {
    exportNameResolver = resolve;
    exportNameInput.value = "";
    exportNamePreview.textContent = "";
    exportNameError.classList.add("hidden");
    exportNameError.textContent = "";
    exportNameModal.classList.remove("hidden");
    document.body.classList.add("modal-open");
    updateExportNamePreview();
    exportNameInput.focus();
  });
}

function promptExportName() {
  return openExportNameModal();
}

exportNameInput.addEventListener("input", () => {
  updateExportNamePreview();
  exportNameError.classList.add("hidden");
});

exportNameCancel.addEventListener("click", () => {
  closeExportNameModal(null);
});

exportNameConfirm.addEventListener("click", () => {
  const stem = sanitizeExportStem(exportNameInput.value);
  if (!stem) {
    exportNameError.textContent = "Enter a name for this export.";
    exportNameError.classList.remove("hidden");
    exportNameInput.focus();
    return;
  }
  closeExportNameModal(stem);
});

exportNameModal.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    closeExportNameModal(null);
  } else if (event.key === "Enter" && event.target === exportNameInput) {
    event.preventDefault();
    exportNameConfirm.click();
  }
});

async function saveAsNewWorkbook(exportName) {
  const formData = new FormData();
  formData.append("token", pendingToken);
  formData.append("save_scope", selectedSaveRowScope || "new");
  formData.append("export_name", exportName);
  formData.append("duplicate_workbooks", duplicateWorkbooksPayloadString());
  const response = await fetch("/api/save-pending-new", { method: "POST", body: formData });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Could not save workbook on the server.");
  }
  await populateDupCheckSheets();
  await populateSaveTargetSheets();
  foldersIndexLoaded = false;
  if (!pageFolders.classList.contains("hidden")) {
    await loadFoldersIndex();
  }
  return payload.message || "Workbook saved on the server.";
}

saveConfirmBtn.addEventListener("click", async () => {
  if (!pendingToken) {
    setError("Nothing to save. Process screenshots first.");
    return;
  }

  const mode = selectedSaveMode;
  if (!mode) {
    setError("Choose how you want to save.");
    return;
  }

  setError("");

  if (mode === "new") {
    const exportName = await promptExportName();
    if (!exportName) {
      return;
    }
    setLoading(true, { message: "Saving workbook...", showProgress: false, detail: "Writing to storage" });
    saveConfirmBtn.disabled = true;
    try {
      const msg = await saveAsNewWorkbook(exportName);
      pendingToken = "";
      resultSection.classList.add("hidden");
      resetSavePanel();
      fileCount.textContent = msg;
    } catch (err) {
      setError(err.message || "Save was cancelled or failed.");
    } finally {
      setLoading(false);
      saveConfirmBtn.disabled = false;
    }
    return;
  }

  if (mode === "existing") {
    const target = selectedTargetSheet;
    if (!target) {
      setError("Select a sheet first.");
      return;
    }
    const formData = new FormData();
    formData.append("token", pendingToken);
    formData.append("target_sheet", target);
    formData.append("save_scope", selectedSaveRowScope || "new");
    formData.append("duplicate_workbooks", duplicateWorkbooksPayloadString());
    setLoading(true, { message: "Saving to sheet...", showProgress: false, detail: "Merging rows" });
    saveConfirmBtn.disabled = true;
    try {
      const response = await fetch("/api/save-to-existing", { method: "POST", body: formData });
      const payload = await response.json();
      if (!response.ok) {
        setError(payload.detail || "Save failed.");
        return;
      }
      pendingToken = "";
      resultSection.classList.add("hidden");
      resetSavePanel();
      fileCount.textContent = payload.message || "Results saved.";
      await populateDupCheckSheets();
      await populateSaveTargetSheets();
      foldersIndexLoaded = false;
      if (!pageFolders.classList.contains("hidden")) {
        await loadFoldersIndex();
      }
    } catch (err) {
      setError("Could not save to the selected sheet.");
    } finally {
      setLoading(false);
      saveConfirmBtn.disabled = false;
    }
  }
});

processBtn.addEventListener("click", async () => {
  setError("");
  resultSection.classList.add("hidden");
  resetSavePanel();

  if (selectedScreenshotCount() === 0) {
    setError("Please upload at least one screenshot.");
    return;
  }

  const files = await prepareScreenshotsForUpload([...screenshotSelection]);
  const total = files.length;
  const chunks = chunkFiles(files, PROCESS_CHUNK_SIZE);
  const dupWorkbooks = duplicateWorkbooksPayloadString();

  const mergedNew = [];
  const mergedDup = [];
  const mergedFailed = [];
  let sessionToken = "";
  let processedCount = 0;

  setLoading(true);
  setLoadingProgress(0, total, "Preparing screenshots...");
  processBtn.disabled = true;
  processBtn.textContent = "Processing...";

  try {
    for (let i = 0; i < chunks.length; i += 1) {
      const chunk = chunks[i];
      const chunkStart = processedCount + 1;
      const chunkEnd = Math.min(processedCount + chunk.length, total);
      setLoadingProgress(
        processedCount,
        total,
        `Processing batch ${i + 1}/${chunks.length} (${chunkStart}–${chunkEnd} of ${total})...`
      );

      const formData = new FormData();
      formData.append("duplicate_workbooks", dupWorkbooks);
      if (sessionToken) {
        formData.append("continuation_token", sessionToken);
      }
      chunk.forEach((file) => {
        formData.append("screenshots", file);
      });

      const response = await fetchProcessWithRetry(formData, {
        current: processedCount,
        total,
      });
      const { payload, nonJsonBody } = await parseProcessResponse(response);
      if (!response.ok || !payload) {
        setError(processErrorMessage(response, payload, nonJsonBody, null));
        return;
      }

      mergedNew.push(...(payload.new_rows || []));
      mergedDup.push(...(payload.duplicate_rows || []));
      mergedFailed.push(...(payload.failed_rows || []));
      sessionToken = payload.token || sessionToken;
      processedCount += chunk.length;

      setLoadingProgress(
        processedCount,
        total,
        processedCount < total ? "Continuing..." : "Finishing..."
      );
    }

    pendingToken = sessionToken;
    setTableData(mergedNew, mergedDup, mergedFailed);
    syncResultStatsFromTable();

    if (mergedFailed.length > 0) {
      const firstErr = String(mergedFailed[0].Error || mergedFailed[0].error || "").trim();
      const label =
        mergedFailed.length === 1
          ? "1 screenshot failed to extract."
          : `${mergedFailed.length} screenshots failed to extract.`;
      setError(firstErr ? `${label} ${firstErr}` : `${label} Hover the Failed status in the table for details.`);
    } else {
      setError("");
    }

    resultSection.classList.remove("hidden");
    await refreshSheetDuplicateOverlay();
    updateSaveConfirmVisibility();
  } catch (err) {
    setError(processErrorMessage(null, null, "", err));
  } finally {
    setLoading(false);
    processBtn.disabled = false;
    processBtn.textContent = "Process";
  }
});

cancelResultsBtn.addEventListener("click", async () => {
  if (!pendingToken) {
    resultSection.classList.add("hidden");
    resetSavePanel();
    return;
  }
  const formData = new FormData();
  formData.append("token", pendingToken);
  try {
    await fetch("/api/cancel", { method: "POST", body: formData });
  } catch (err) {
    // no-op
  }
  pendingToken = "";
  resultSection.classList.add("hidden");
  resetSavePanel();
  setError("");
});

paginationFirst.addEventListener("click", () => {
  tableCurrentPage = 1;
  renderResultsTable();
});

paginationPrev.addEventListener("click", () => {
  tableCurrentPage = Math.max(1, tableCurrentPage - 1);
  renderResultsTable();
});

paginationNext.addEventListener("click", () => {
  const totalPages = Math.max(1, Math.ceil(tableAllRows.length / tablePageSize));
  tableCurrentPage = Math.min(totalPages, tableCurrentPage + 1);
  renderResultsTable();
});

paginationLast.addEventListener("click", () => {
  const totalPages = Math.max(1, Math.ceil(tableAllRows.length / tablePageSize));
  tableCurrentPage = totalPages;
  renderResultsTable();
});

renderSaveModeMenuItems();
renderSaveRowScopeMenuItems();
void populateDupCheckSheets();
initPageSizeButtons();

copyNewLeadsBtn.addEventListener("click", () => {
  void copyLeadsToClipboard("new");
});
copyDupLeadsBtn.addEventListener("click", () => {
  void copyLeadsToClipboard("dup");
});
copyAllLeadsBtn.addEventListener("click", () => {
  void copyLeadsToClipboard("all");
});
