(function () {
  const seedInput = document.getElementById("urlSeedInput");
  const runBtn = document.getElementById("urlRunBtn");
  const cancelBtn = document.getElementById("urlCancelBtn");
  const errorEl = document.getElementById("urlError");
  const disabledEl = document.getElementById("urlPipelineDisabled");
  const maxSeedsEl = document.getElementById("urlMaxSeeds");
  const dupCheckList = document.getElementById("urlDupCheckList");

  const progressCard = document.getElementById("urlProgressCard");
  const progressMsg = document.getElementById("urlProgressMsg");
  const progressBar = document.getElementById("urlProgressBar");

  const resultSection = document.getElementById("urlResultSection");
  const resultSummary = document.getElementById("urlResultSummary");
  const tableBody = document.querySelector("#urlResultTable tbody");
  const newCountEl = document.getElementById("urlNewCount");
  const dupCountEl = document.getElementById("urlDupCount");
  const checkedCountEl = document.getElementById("urlCheckedCount");
  const followerCountEl = document.getElementById("urlFollowerCount");

  const copyNewBtn = document.getElementById("urlCopyNewBtn");
  const copyAllBtn = document.getElementById("urlCopyAllBtn");
  const copyFeedback = document.getElementById("urlCopyFeedback");

  const saveTarget = document.getElementById("urlSaveTarget");
  const saveExistingBtn = document.getElementById("urlSaveExistingBtn");
  const saveNewBtn = document.getElementById("urlSaveNewBtn");
  const saveFeedback = document.getElementById("urlSaveFeedback");

  if (!seedInput || !runBtn) return;

  let initialised = false;
  let polling = false;
  let activeJobId = null;
  let pollTimer = null;
  let currentToken = null;
  let currentRows = [];

  function apiDetail(data, fallback) {
    if (data && typeof data.detail === "string") return data.detail;
    return fallback;
  }

  function showError(msg) {
    if (!errorEl) return;
    errorEl.textContent = msg || "";
    errorEl.classList.toggle("hidden", !msg);
  }

  function flash(el, msg, ok) {
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("hidden", !msg);
    el.classList.toggle("copy-feedback--ok", !!ok);
  }

  async function loadStatus() {
    try {
      const res = await fetch("/api/url-pipeline-status");
      const data = await res.json();
      if (maxSeedsEl && data.max_seed_urls) maxSeedsEl.textContent = String(data.max_seed_urls);
      if (!data.enabled) {
        const missing = (data.missing || []).join(", ");
        disabledEl.textContent =
          "URL pipeline is not configured yet. Add these to your .env and restart: " + missing + ".";
        disabledEl.classList.remove("hidden");
        runBtn.disabled = true;
      } else {
        disabledEl.classList.add("hidden");
        runBtn.disabled = false;
      }
    } catch (err) {
      disabledEl.textContent = "Could not check pipeline status.";
      disabledEl.classList.remove("hidden");
    }
  }

  async function loadMasterSheets() {
    let sheets = [];
    try {
      const res = await fetch("/api/excel-sheets");
      const data = await res.json();
      sheets = Array.isArray(data.sheets) ? data.sheets : [];
    } catch (err) {
      sheets = [];
    }

    dupCheckList.innerHTML = "";
    if (!sheets.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No MASTER workbooks found. Upload contacted-lead workbooks under Folders → MASTER.";
      dupCheckList.appendChild(empty);
    } else {
      for (const name of sheets) {
        const label = document.createElement("label");
        label.className = "url-checkbox";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.value = name;
        cb.checked = true;
        cb.className = "url-dup-cb";
        label.appendChild(cb);
        const span = document.createElement("span");
        span.textContent = name;
        label.appendChild(span);
        dupCheckList.appendChild(label);
      }
    }

    saveTarget.innerHTML = "";
    if (!sheets.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No MASTER workbooks";
      saveTarget.appendChild(opt);
      saveExistingBtn.disabled = true;
    } else {
      saveExistingBtn.disabled = false;
      for (const name of sheets) {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        saveTarget.appendChild(opt);
      }
    }
  }

  function selectedDuplicateWorkbooks() {
    const boxes = [...dupCheckList.querySelectorAll(".url-dup-cb")];
    if (!boxes.length) return "";
    const checked = boxes.filter((b) => b.checked).map((b) => b.value);
    if (checked.length === 0 || checked.length === boxes.length) return "";
    return JSON.stringify(checked);
  }

  function setRunning(running) {
    runBtn.disabled = running;
    cancelBtn.classList.toggle("hidden", !running);
    seedInput.disabled = running;
    progressCard.classList.toggle("hidden", !running);
  }

  function statusLabel(status) {
    if (status === "duplicate") return { text: "Duplicate", cls: "status-pill--dup" };
    if (status === "batch_duplicate") return { text: "Repeat in batch", cls: "status-pill--dup" };
    return { text: "New", cls: "status-pill--new" };
  }

  function renderRows(rows) {
    tableBody.innerHTML = "";
    for (const row of rows) {
      const tr = document.createElement("tr");

      const statusTd = document.createElement("td");
      const info = statusLabel(row.status);
      const pill = document.createElement("span");
      pill.className = "status-pill " + info.cls;
      pill.textContent = info.text;
      statusTd.appendChild(pill);
      tr.appendChild(statusTd);

      for (const key of ["Business Name", "Mobile", "Email", "Instagram", "Source URL"]) {
        const td = document.createElement("td");
        const val = row[key] == null ? "" : String(row[key]);
        td.textContent = val;
        if (val.length > 36) td.title = val;
        tr.appendChild(td);
      }
      tableBody.appendChild(tr);
    }
  }

  function renderStats(stats, rows) {
    const newCount = rows.filter((r) => r.status === "new").length;
    const dupCount = rows.length - newCount;
    newCountEl.textContent = String(newCount);
    dupCountEl.textContent = String(dupCount);
    checkedCountEl.textContent = String(stats.profiles_checked || 0);
    followerCountEl.textContent = String(stats.followers_found || 0);

    const bits = [];
    bits.push(`${rows.length} lead(s) from ${stats.profiles_checked || 0} profiles checked`);
    if (stats.skipped_not_business) bits.push(`${stats.skipped_not_business} not business`);
    if (stats.skipped_has_link) bits.push(`${stats.skipped_has_link} had a link`);
    if (stats.skipped_no_phone) bits.push(`${stats.skipped_no_phone} no phone`);
    if (stats.skipped_private) bits.push(`${stats.skipped_private} private`);
    if (stats.errors) bits.push(`${stats.errors} error(s)`);
    if (stats.capped) bits.push("daily cap reached");
    resultSummary.textContent = bits.join(" · ");

    copyNewBtn.disabled = newCount === 0;
    copyAllBtn.disabled = rows.length === 0;
  }

  function stopPolling() {
    polling = false;
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  async function pollJob() {
    if (!activeJobId) return;
    try {
      const res = await fetch(`/api/url-jobs/${activeJobId}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showError(apiDetail(data, "Lost track of the job."));
        stopPolling();
        setRunning(false);
        return;
      }
      const job = await res.json();
      const prog = job.progress || { done: 0, total: 0 };
      progressMsg.textContent = job.message || job.stage || "Working…";
      const pct = prog.total ? Math.round((prog.done / prog.total) * 100) : 5;
      progressBar.style.width = `${Math.max(5, Math.min(100, pct))}%`;

      if (job.status === "running") {
        pollTimer = setTimeout(pollJob, 1500);
        return;
      }

      stopPolling();
      setRunning(false);

      if (job.status === "error") {
        showError(job.error || "The pipeline failed.");
        return;
      }
      if (job.status === "cancelled") {
        showError("Run cancelled.");
        return;
      }

      currentToken = job.token || null;
      currentRows = Array.isArray(job.rows) ? job.rows : [];
      renderRows(currentRows);
      renderStats(job.stats || {}, currentRows);
      resultSection.classList.remove("hidden");
      if (job.invalid_inputs && job.invalid_inputs.length) {
        showError(`Ignored invalid input(s): ${job.invalid_inputs.join(", ")}`);
      }
    } catch (err) {
      pollTimer = setTimeout(pollJob, 2000);
    }
  }

  async function startRun() {
    showError("");
    flash(saveFeedback, "", false);
    flash(copyFeedback, "", false);
    resultSection.classList.add("hidden");

    const urls = (seedInput.value || "").trim();
    if (!urls) {
      showError("Paste at least one Instagram profile URL.");
      return;
    }

    const form = new FormData();
    form.append("urls", urls);
    const dup = selectedDuplicateWorkbooks();
    if (dup) form.append("duplicate_workbooks", dup);

    setRunning(true);
    progressMsg.textContent = "Starting…";
    progressBar.style.width = "5%";

    try {
      const res = await fetch("/api/url-jobs/start", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setRunning(false);
        showError(apiDetail(data, "Could not start the run."));
        return;
      }
      activeJobId = data.job_id;
      polling = true;
      pollJob();
    } catch (err) {
      setRunning(false);
      showError("Could not reach the server.");
    }
  }

  async function cancelRun() {
    if (!activeJobId) return;
    cancelBtn.disabled = true;
    try {
      await fetch(`/api/url-jobs/${activeJobId}/cancel`, { method: "POST" });
    } catch (err) {
      /* ignore */
    }
    cancelBtn.disabled = false;
  }

  function leadsToTsv(rows) {
    const header = ["Business Name", "Mobile", "Email", "Instagram"].join("\t");
    const lines = rows.map((r) =>
      [r["Business Name"], r["Mobile"], r["Email"], r["Instagram"]]
        .map((v) => String(v == null ? "" : v).replace(/\t/g, " ").replace(/\r?\n/g, " "))
        .join("\t"),
    );
    return [header, ...lines].join("\n");
  }

  async function copyLeads(onlyNew) {
    const rows = onlyNew ? currentRows.filter((r) => r.status === "new") : currentRows;
    if (!rows.length) {
      flash(copyFeedback, "Nothing to copy.", false);
      return;
    }
    const text = leadsToTsv(rows);
    try {
      await navigator.clipboard.writeText(text);
      flash(copyFeedback, `Copied ${rows.length} lead(s).`, true);
    } catch (err) {
      flash(copyFeedback, "Copy failed — your browser blocked clipboard access.", false);
    }
  }

  async function saveToExisting() {
    if (!currentToken) {
      flash(saveFeedback, "Run the pipeline first.", false);
      return;
    }
    const target = saveTarget.value;
    if (!target) {
      flash(saveFeedback, "Choose a MASTER workbook to append to.", false);
      return;
    }
    const form = new FormData();
    form.append("token", currentToken);
    form.append("target_sheet", target);
    form.append("save_scope", "new");
    const dup = selectedDuplicateWorkbooks();
    if (dup) form.append("duplicate_workbooks", dup);

    saveExistingBtn.disabled = true;
    try {
      const res = await fetch("/api/save-to-existing", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        flash(saveFeedback, apiDetail(data, "Save failed."), false);
        return;
      }
      flash(saveFeedback, data.message || "Saved.", true);
      currentToken = null;
    } catch (err) {
      flash(saveFeedback, "Could not save to the selected workbook.", false);
    } finally {
      saveExistingBtn.disabled = false;
    }
  }

  async function saveAsNew() {
    if (!currentToken) {
      flash(saveFeedback, "Run the pipeline first.", false);
      return;
    }
    const name = window.prompt("Name for the new workbook (saved to NEW folder):", "url_leads");
    if (name === null) return;
    const clean = name.trim();
    if (!clean) {
      flash(saveFeedback, "Enter a name for the workbook.", false);
      return;
    }
    const form = new FormData();
    form.append("token", currentToken);
    form.append("save_scope", "new");
    form.append("export_name", clean);
    const dup = selectedDuplicateWorkbooks();
    if (dup) form.append("duplicate_workbooks", dup);

    saveNewBtn.disabled = true;
    try {
      const res = await fetch("/api/save-pending-new", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        flash(saveFeedback, apiDetail(data, "Save failed."), false);
        return;
      }
      flash(saveFeedback, data.message || "Saved.", true);
      currentToken = null;
    } catch (err) {
      flash(saveFeedback, "Could not save the workbook.", false);
    } finally {
      saveNewBtn.disabled = false;
    }
  }

  runBtn.addEventListener("click", startRun);
  cancelBtn.addEventListener("click", cancelRun);
  copyNewBtn.addEventListener("click", () => copyLeads(true));
  copyAllBtn.addEventListener("click", () => copyLeads(false));
  saveExistingBtn.addEventListener("click", saveToExisting);
  saveNewBtn.addEventListener("click", saveAsNew);

  document.addEventListener("urls:show", async () => {
    await loadStatus();
    await loadMasterSheets();
    if (!initialised) initialised = true;
  });
})();
