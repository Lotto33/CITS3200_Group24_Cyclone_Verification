// The API accepts one state and season per request; selected filters expand into request combinations.
(function () {
  "use strict";

  interface Disturbance {
    disturbance_id: string;
    name: string | null;
    region: string | null;
    season: string | null;
  }

  interface Page<T> {
    items: T[];
    total: number;
    limit: number;
    offset: number;
  }

  interface Stats { hit: number; false_alarm: number; miss: number; correct_negative: number; total: number }
  interface ContingencyResponse { status: string; disturbance_ids: string[]; stats: Stats; files: Record<string, string> }
  interface Town { state: string }
  interface UploadJobStatus {
    job_id: string; description: string; status: "queued" | "running" | "completed" | "failed";
    messages: string[]; next: number; error: string | null;
    result: { interpolation_error?: string | null } | null;
  }
  interface ContingencyJobAccepted { job_id: string; status: string }
  interface ContingencyJobStatus extends Omit<UploadJobStatus, "result"> {
    result: ContingencyResponse | null;
  }
  interface RequestError extends Error { status?: number }
  interface SavedContext { distId?: string; distName?: string; region?: string; season?: string; bulletin?: string }
  interface TableRequest {
    disturbance_ids: string[]; season: string | null; state: string | null;
    x_hours: number; y_hours: number; base_time_hours: number[]; forecast_level: string;
  }

  const API_BASE = "/api/v1";
  const ALL_VALUE = "__all__";
  const SUPPORTED_STATES = ["NT", "QLD", "WA"];
  // Project scope: verification period 2016/17 to 2025/26.
  const FIRST_SEASON = "2016-17";
  const LAST_SEASON = "2025-26";

  const tableInstances = document.getElementById("tableInstances");
  const firstInstance = tableInstances?.querySelector<HTMLElement>(".table-instance");
  const savedContext: SavedContext = JSON.parse(localStorage.getItem("cycloneVerification") || "null") || {};
  let disturbances: Disturbance[] = [];
  let states: string[] = [];
  let latestFiles: string[] = [];
  const filesByInstance = new Map<string, string[]>();
  const combinedFilesByInstance = new Map<string, Array<{ filename: string; content: string }>>();
  const initializedInstances = new WeakSet<HTMLElement>();

  if (!tableInstances || !firstInstance) return;

  function byId<T extends HTMLElement>(id: string): T {
    const element = document.getElementById(id);
    if (!element) throw new Error(`Missing page element: ${id}`);
    return element as T;
  }

  function status(message: string, isError = false): void {
    const element = byId<HTMLDivElement>("uploadStatus");
    element.textContent = message;
    element.classList.toggle("error", isError);
  }

  function updateUploadProgress(phase: string, detail: string, percentage?: number): void {
    const container = byId<HTMLDivElement>("uploadProgress");
    const label = byId<HTMLElement>("uploadPhase");
    const progress = byId<HTMLDivElement>("uploadProgressBar");
    container.hidden = false;
    label.textContent = phase;
    status(detail);
    if (percentage === undefined) {
      progress.style.width = "35%";
      progress.removeAttribute("aria-valuenow");
      progress.setAttribute("aria-valuetext", "Processing");
      progress.classList.add("progress-bar-striped", "progress-bar-animated");
      progress.classList.add("progress-bar-indeterminate");
    } else {
      progress.style.width = `${percentage}%`;
      progress.setAttribute("aria-valuenow", String(percentage));
      progress.removeAttribute("aria-valuetext");
      progress.classList.remove("progress-bar-indeterminate");
      progress.classList.toggle("progress-bar-striped", percentage < 100);
      progress.classList.toggle("progress-bar-animated", percentage < 100);
    }
  }

  function uploadFile(file: File | null, endpoint: string, description: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      if (file) form.append("file", file);
      xhr.open("POST", `${API_BASE}/datasets/${endpoint}`);
      xhr.responseType = "json";
      xhr.upload.addEventListener("progress", (event) => {
        if (!file) return;
        if (!event.lengthComputable) {
          updateUploadProgress("Uploading file", `${file.name} — ${formatBytes(event.loaded)} sent.`);
          return;
        }
        const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
        updateUploadProgress("Uploading file", `${file.name} — ${formatBytes(event.loaded)} of ${formatBytes(event.total)} transferred.`, percent);
      });
      xhr.upload.addEventListener("load", () => {
        if (!file) return;
        updateUploadProgress(
          file ? "Processing on server" : "Fetching from BOM",
          file
            ? `${file.name} uploaded. The server is validating and processing the ${description}; this may take a little while.`
            : `Request accepted. The server is downloading and processing the ${description}; this may take a little while.`,
        );
      });
      xhr.addEventListener("load", () => {
        const payload = xhr.response as { detail?: string; job_id?: string } | null;
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(payload?.detail || `Upload failed (HTTP ${xhr.status}).`));
          return;
        }
        if (!payload?.job_id) {
          reject(new Error("The backend accepted the file but did not return a processing job ID."));
          return;
        }
        void waitForUploadJob(
          payload.job_id,
          file?.name || "BOM best-track data",
          description,
        ).then(resolve, reject);
      });
      xhr.addEventListener("error", () => reject(new Error("Network error while uploading. Check your connection and try again.")));
      xhr.addEventListener("abort", () => reject(new Error("Upload was cancelled.")));
      xhr.send(file ? form : null);
    });
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB"];
    let size = bytes / 1024;
    let unit = units[0];
    for (let index = 1; size >= 1024 && index < units.length; index += 1) {
      size /= 1024;
      unit = units[index];
    }
    return `${size.toFixed(1)} ${unit}`;
  }

  function appendBackendMessages(messages: string[]): void {
    const log = byId<HTMLOListElement>("uploadBackendMessages");
    messages.forEach((message) => {
      const line = document.createElement("li");
      line.textContent = message || " ";
      log.appendChild(line);
    });
    log.scrollTop = log.scrollHeight;
  }

  async function waitForUploadJob(jobId: string, filename: string, description: string): Promise<void> {
    let offset = 0;
    let refreshStage: { label: string; percentage: number } | null = null;
    const deadline = Date.now() + 30 * 60 * 1000;
    while (Date.now() < deadline) {
      let job: UploadJobStatus;
      try {
        job = await requestJson<UploadJobStatus>(`/datasets/jobs/${encodeURIComponent(jobId)}?since=${offset}`);
      } catch (error) {
        const requestError = error as RequestError;
        if (requestError.status === 404) {
          throw new Error("The upload job is no longer available. The server may have restarted; please upload the file again.");
        }
        throw error;
      }
      appendBackendMessages(job.messages);
      offset = job.next;
      for (const message of job.messages) {
        const stage = uploadProgressStage(message, description);
        if (stage) refreshStage = stage;
      }
      if (job.status === "completed") {
        const interpolationError = job.result?.interpolation_error;
        updateUploadProgress(
          description.toLowerCase().includes("bom")
            ? "Step 5 of 5 · Complete"
            : interpolationError
              ? "Upload complete with warning"
              : "Step 5 of 5 · Complete",
          interpolationError
            ? `${filename}: uploaded successfully, but interpolation was skipped: ${interpolationError}`
            : `${filename}: ${description} processing completed successfully.`,
          100,
        );
        return;
      }
      if (job.status === "failed") throw new Error(job.error || `${description} processing failed.`);
      const latestMessage = job.messages[job.messages.length - 1]
        || `${filename}: waiting for backend pipeline messages.`;
      if (refreshStage) {
        updateUploadProgress(refreshStage.label, latestMessage, refreshStage.percentage);
      } else {
        updateUploadProgress(
          job.status === "queued" ? "Waiting for backend" : "Backend processing",
          latestMessage,
        );
      }
      await new Promise<void>((resolve) => window.setTimeout(resolve, 650));
    }
    throw new Error("The upload job exceeded the 30-minute polling limit. Check the backend logs and try again.");
  }

  async function waitForContingencyJob(instance: HTMLElement, jobId: string, requestNumber: number, requestCount: number): Promise<ContingencyResponse> {
    let offset = 0;
    const deadline = Date.now() + 30 * 60 * 1000;
    while (Date.now() < deadline) {
      let job: ContingencyJobStatus;
      try {
        job = await requestJson<ContingencyJobStatus>(
          `/contingency-tables/jobs/${encodeURIComponent(jobId)}?since=${offset}`,
        );
      } catch (error) {
        const requestError = error as RequestError;
        if (requestError.status === 404) {
          throw new Error("The generation job is no longer available. The server may have restarted; please run it again.");
        }
        throw error;
      }
      offset = job.next;
      if (job.status === "completed") {
        if (!job.result) throw new Error("The generation job completed without returning table results.");
        return job.result;
      }
      if (job.status === "failed") throw new Error(job.error || "Contingency-table generation failed.");
      const latestMessage = job.messages[job.messages.length - 1] || "Starting table generation…";
      instanceStatus(
        instance,
        `Generating request ${requestNumber} of ${requestCount} (${job.status}) — ${latestMessage}`,
      );
      await new Promise<void>((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new Error("The generation job exceeded the 30-minute polling limit. Check the backend logs and try again.");
  }

  function uploadProgressStage(message: string, description: string): { label: string; percentage: number } | null {
    const normalized = message.toLowerCase();
    if (description.toLowerCase().includes("bom")) {
      if (normalized.startsWith("starting bom best-track refresh")) {
        return { label: "Step 1 of 5 · Preparing refresh", percentage: 10 };
      }
      if (normalized.startsWith("downloading current bom best-track csv")) {
        return { label: "Step 2 of 5 · Downloading best-track data from BOM", percentage: 25 };
      }
      if (normalized.startsWith("downloaded ")) {
        return { label: "Step 2 of 5 · Downloading best-track data from BOM", percentage: 40 };
      }
      if (normalized.startsWith("validating downloaded best-track csv")) {
        return { label: "Step 3 of 5 · Validating the downloaded CSV", percentage: 50 };
      }
      if (normalized.startsWith("=== database ingest: best-track observations ===")) {
        return { label: "Step 4 of 5 · Importing best-track observations", percentage: 65 };
      }
      if (normalized.startsWith("database best-track ingest:")) {
        return { label: "Step 4 of 5 · Best-track observations imported", percentage: 75 };
      }
      if (normalized.startsWith("=== database interpolation ===")) {
        return { label: "Step 5 of 5 · Interpolating track positions and wind radii", percentage: 85 };
      }
      if (normalized.startsWith("database interpolation:")) {
        return { label: "Step 5 of 5 · Interpolated track saved", percentage: 95 };
      }
      return null;
    }

    if (normalized.startsWith("starting gml archive processing")) {
      return { label: "Step 1 of 5 · Preparing GML archive", percentage: 10 };
    }
    if (normalized.startsWith("step 1 of 5")) {
      return { label: "Step 1 of 5 · Extracting GML archive", percentage: 20 };
    }
    if (normalized.startsWith("extracted ")) {
      return { label: "Step 2 of 5 · Checking extracted GML files", percentage: 30 };
    }
    if (normalized.startsWith("step 3 of 5")) {
      return { label: "Step 3 of 5 · Generating viewer datasets", percentage: 45 };
    }
    if (normalized.startsWith("converting gml bulletins")) {
      return { label: "Step 3 of 5 · Converting GML to JSON and GeoJSON", percentage: 55 };
    }
    if (normalized.startsWith("static datasets ready:")) {
      return { label: "Step 4 of 5 · Loading bulletins into the database", percentage: 75 };
    }
    if (normalized.startsWith("step 4 of 5")) {
      return { label: "Step 4 of 5 · Loading bulletins into the database", percentage: 80 };
    }
    if (normalized.startsWith("database gml ingest:")) {
      return { label: "Step 5 of 5 · Saving complete", percentage: 95 };
    }
    return null;
  }

  async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, init);
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
      const error = new Error(detail) as RequestError;
      error.status = response.status;
      throw error;
    }
    return payload as T;
  }

  async function loadDisturbances(): Promise<Disturbance[]> {
    const result: Disturbance[] = [];
    let offset = 0;
    const limit = 500;
    while (true) {
      const page = await requestJson<Page<Disturbance>>(`/disturbances?limit=${limit}&offset=${offset}`);
      result.push(...page.items);
      offset += page.items.length;
      if (offset >= page.total || page.items.length === 0) return result;
    }
  }

  async function loadFilterOptions(): Promise<void> {
    const [disturbanceRows, townRows] = await Promise.all([
      loadDisturbances(),
      requestJson<Town[]>("/towns"),
    ]);
    disturbances = disturbanceRows.filter((row) =>
      Boolean(row.season) && row.season! >= FIRST_SEASON && row.season! <= LAST_SEASON);
    states = [...new Set([
      ...SUPPORTED_STATES,
      ...townRows.map((town) => town.state).filter(Boolean),
    ])].sort((a, b) => {
      const rank = (state: string) => {
        const index = SUPPORTED_STATES.indexOf(state);
        return index < 0 ? SUPPORTED_STATES.length : index;
      };
      return rank(a) - rank(b) || a.localeCompare(b);
    });
    document.querySelectorAll<HTMLElement>(".table-instance").forEach(populateInstanceFilters);
  }

  function selected(select: HTMLSelectElement): string[] {
    return Array.from(select.selectedOptions).map((option) => option.value).filter((value) => value !== ALL_VALUE);
  }

  interface SelectState { options: Array<{ value: string; label: string }>; selected: Set<string>; query: string }
  const selectStates = new WeakMap<HTMLSelectElement, SelectState>();

  // Selected options always stay visible so searching never drops a selection.
  function renderSelect(select: HTMLSelectElement): void {
    const state = selectStates.get(select);
    if (!state) return;
    const query = state.query.trim().toLowerCase();
    const visible = state.options.filter((option) =>
      option.value === ALL_VALUE || state.selected.has(option.value) || !query || option.label.toLowerCase().includes(query));
    select.replaceChildren(...visible.map(({ value, label }) => {
      const option = new Option(label, value);
      option.selected = state.selected.has(value);
      return option;
    }));
  }

  // "All" is exclusive: picking it clears the rest, picking anything else clears it.
  function applySelection(select: HTMLSelectElement, next: Set<string>, added: string[]): void {
    const state = selectStates.get(select);
    if (!state) return;
    if (next.has(ALL_VALUE) && next.size > 1) {
      if (added.includes(ALL_VALUE)) { next.clear(); next.add(ALL_VALUE); }
      else next.delete(ALL_VALUE);
    }
    if (next.size === 0) next.add(ALL_VALUE);
    state.selected = next;
    renderSelect(select);
  }

  function wireMultiSelect(select: HTMLSelectElement, searchInput: HTMLInputElement | null): void {
    // Plain clicks toggle an option; the native list box needs Cmd/Ctrl-click.
    select.addEventListener("mousedown", (event) => {
      const option = event.target;
      const state = selectStates.get(select);
      if (!(option instanceof HTMLOptionElement) || !state) return;
      event.preventDefault();
      select.focus();
      const next = new Set(state.selected);
      if (next.has(option.value)) next.delete(option.value); else next.add(option.value);
      applySelection(select, next, [option.value]);
      select.dispatchEvent(new Event("change"));
    });
    // Keyboard selection still goes through the native change event.
    select.addEventListener("change", () => {
      const state = selectStates.get(select);
      if (!state) return;
      const current = new Set(Array.from(select.selectedOptions).map((option) => option.value));
      const added = [...current].filter((value) => !state.selected.has(value));
      applySelection(select, current, added);
    });
    searchInput?.addEventListener("input", () => {
      const state = selectStates.get(select);
      if (!state) return;
      state.query = searchInput.value;
      renderSelect(select);
    });
  }

  function populateSelect(select: HTMLSelectElement, options: Array<{ value: string; label: string }>, defaults: string[]): void {
    const available = new Set(options.map((option) => option.value));
    const chosen = defaults.filter((value) => available.has(value));
    if (!chosen.length) chosen.push(ALL_VALUE);
    selectStates.set(select, { options, selected: new Set(chosen), query: "" });
    renderSelect(select);
  }

  function populateInstanceFilters(instance: HTMLElement): void {
    const cycloneSelect = instance.querySelector<HTMLSelectElement>(".cyclone-select");
    const stateSelect = instance.querySelector<HTMLSelectElement>(".state-select");
    const seasonSelect = instance.querySelector<HTMLSelectElement>(".season-select");
    if (!cycloneSelect || !stateSelect || !seasonSelect) return;
    const cycloneOptions = disturbances.slice().sort((a, b) => a.disturbance_id.localeCompare(b.disturbance_id))
      .map((row) => ({ value: row.disturbance_id, label: `${row.name || row.disturbance_id} — ${row.disturbance_id}` }));
    populateSelect(cycloneSelect, [{ value: ALL_VALUE, label: "Any cyclone (select a season)" }, ...cycloneOptions],
      instance === firstInstance && savedContext.distId ? [savedContext.distId] : [ALL_VALUE]);
    populateSelect(stateSelect, [{ value: ALL_VALUE, label: "All states" }, ...states.map((value) => ({ value, label: value }))], [ALL_VALUE]);
    const seasons = [...new Set(disturbances.map((row) => row.season).filter((value): value is string => Boolean(value)))].sort().reverse();
    populateSelect(seasonSelect, [{ value: ALL_VALUE, label: "All seasons" }, ...seasons.map((value) => ({ value, label: value }))],
      instance === firstInstance && savedContext.season ? [savedContext.season] : [ALL_VALUE]);
    instance.querySelectorAll<HTMLInputElement>(".cyclone-search").forEach((input) => { input.value = ""; });
    updateContext();
  }

  function updateContext(): void {
    const context = byId<HTMLParagraphElement>("context");
    const descriptions = Array.from(tableInstances!.querySelectorAll<HTMLElement>(".table-instance")).map((instance) => {
      const ids = selected(instance.querySelector<HTMLSelectElement>(".cyclone-select")!);
      const stateValues = selected(instance.querySelector<HTMLSelectElement>(".state-select")!);
      const seasons = selected(instance.querySelector<HTMLSelectElement>(".season-select")!);
      const baseTimes = Array.from(instance.querySelectorAll<HTMLInputElement>(".base-time-hour:checked"))
        .map((input) => `${input.value.padStart(2, "0")}:00`);
      return `${ids.length ? `${ids.length} cyclone(s)` : "season-based selection"}; ${stateValues.length ? stateValues.join(", ") : "all states"}; ${seasons.length ? seasons.join(", ") : "all seasons"}; base times ${baseTimes.join(", ") || "none"} UTC`;
    });
    context.textContent = `Contingency table filters: ${descriptions.join(" | ")}${savedContext.bulletin ? `; visualizer bulletin ${savedContext.bulletin}` : ""}.`;
  }

  function instanceStatus(instance: HTMLElement, message: string, isError = false): void {
    const output = instance.querySelector<HTMLElement>(".instance-status");
    if (output) {
      output.textContent = message;
      output.classList.toggle("error", isError);
    }
  }

  function resetPanel(instance: HTMLElement, panelSelector: string, label: string): HTMLElement | null {
    const panel = instance.querySelector<HTMLElement>(panelSelector);
    if (!panel) return null;
    panel.replaceChildren();
    const heading = document.createElement("p");
    heading.className = "layer-note";
    heading.textContent = label;
    panel.appendChild(heading);
    return panel;
  }

  function restorePanelPlaceholders(instance: HTMLElement): void {
    const number = instance.dataset.instance || "1";
    resetPanel(instance, `#panel-area-${number}`, "Generate tables to load Table A from the API.");
    ["track", "wind", "warning"].forEach((panel) => resetPanel(instance, `#panel-${panel}-${number}`, `Generate tables to load Table ${panel.toUpperCase()} from the API.`));
    resetPanel(instance, `#panel-summary-${number}`, "Generate tables to load the combined contingency matrix and skill scores.");
  }

  function csvRows(text: string): string[][] {
    const rows: string[][] = [];
    let row: string[] = [];
    let cell = "";
    let quoted = false;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (char === '"' && quoted && text[i + 1] === '"') { cell += '"'; i += 1; }
      else if (char === '"') quoted = !quoted;
      else if (char === "," && !quoted) { row.push(cell); cell = ""; }
      else if ((char === "\n" || char === "\r") && !quoted) {
        if (char === "\r" && text[i + 1] === "\n") i += 1;
        row.push(cell); cell = "";
        if (row.some((value) => value.length)) rows.push(row);
        row = [];
      } else cell += char;
    }
    if (cell.length || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }

  function combineCsvTexts(texts: string[]): string {
    const parsedFiles = texts.map(csvRows).filter((rows) => rows.length > 0);
    if (!parsedFiles.length) return "";
    const headers = parsedFiles[0][0];
    const dataRows = parsedFiles.flatMap((rows) => {
      const header = rows[0];
      if (header.length !== headers.length || header.some((value, index) => value !== headers[index])) {
        throw new Error("Generated CSV files for this table have different columns and cannot be combined.");
      }
      return rows.slice(1);
    });
    return [headers, ...dataRows]
      .map((row) => row.map((value) => /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value).join(","))
      .join("\r\n");
  }

  function renderCsv(panel: HTMLElement, texts: string[]): void {
    const combined = combineCsvTexts(texts);
    const rows = csvRows(combined);
    if (!rows.length) return;
    const table = document.createElement("table");
    table.className = "contingency-table api-result-table";
    const caption = document.createElement("caption");
    const sourceCount = texts.filter((text) => csvRows(text).length > 0).length;
    caption.textContent = `Combined rows from ${sourceCount} generated CSV file${sourceCount === 1 ? "" : "s"}`;
    table.appendChild(caption);
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    rows[0].forEach((value) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = value; headRow.appendChild(th); });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const body = document.createElement("tbody");
    rows.slice(1).forEach((values) => {
      const tr = document.createElement("tr");
      values.forEach((value, index) => {
        const cell = document.createElement(index === 0 ? "th" : "td");
        if (index === 0) (cell as HTMLTableCellElement).scope = "row";
        cell.textContent = value;
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    panel.appendChild(table);
  }

  function formatPercent(numerator: number, denominator: number): string {
    return denominator ? `${(numerator / denominator * 100).toFixed(1)}%` : "—";
  }

  function renderSummary(panel: HTMLElement, stats: Stats): void {
    const hit = stats.hit;
    const falseAlarm = stats.false_alarm;
    const miss = stats.miss;
    const correctNegative = stats.correct_negative;
    const precision = hit + falseAlarm ? hit / (hit + falseAlarm) : 0;
    const recall = hit + miss ? hit / (hit + miss) : 0;
    const items: Array<[string, string]> = [
      ["Accuracy", formatPercent(hit + correctNegative, stats.total)],
      ["Precision", formatPercent(hit, hit + falseAlarm)],
      ["Recall", formatPercent(hit, hit + miss)],
      ["F1 score", precision + recall ? `${(2 * precision * recall / (precision + recall) * 100).toFixed(1)}%` : "—"],
      ["FAR", formatPercent(falseAlarm, hit + falseAlarm)],
      ["CSI", formatPercent(hit, hit + falseAlarm + miss)],
      ["Bias", hit + miss ? ((hit + falseAlarm) / (hit + miss)).toFixed(2) : "—"],
    ];
    const metrics = document.createElement("div");
    metrics.className = "metrics";
    items.forEach(([label, value]) => {
      const span = document.createElement("span");
      span.append(`${label} `);
      const strong = document.createElement("b"); strong.textContent = value; span.appendChild(strong); metrics.appendChild(span);
    });
    const table = document.createElement("table");
    table.className = "contingency-table";
    table.innerHTML = "<caption>Combined contingency matrix</caption><thead><tr><th scope=\"col\">Forecast</th><th scope=\"col\">Observed: Yes</th><th scope=\"col\">Observed: No</th><th scope=\"col\">Total</th></tr></thead>";
    const body = document.createElement("tbody");
    const matrixRows = [
      ["Yes", hit, falseAlarm, hit + falseAlarm],
      ["No", miss, correctNegative, miss + correctNegative],
      ["Total", hit + miss, falseAlarm + correctNegative, stats.total],
    ];
    matrixRows.forEach((values) => {
      const tr = document.createElement("tr");
      values.forEach((value, index) => {
        const cell = document.createElement(index === 0 ? "th" : "td");
        if (index === 0) (cell as HTMLTableCellElement).scope = "row";
        cell.textContent = String(value);
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    panel.append(table, metrics);
  }

  function isCurrentRunFile(name: string, ids: string[], baseTimeHours: number[]): boolean {
    const identifierMatches = name.startsWith("combined_") || ids.some((id) => name.startsWith(`${id}_`));
    const baseTimeTag = `base-times-${baseTimeHours.slice().sort((a, b) => a - b).map((hour) => String(hour).padStart(2, "0")).join("-")}`;
    return identifierMatches && name.includes(baseTimeTag);
  }

  async function downloadFile(filename: string): Promise<void> {
    const response = await fetch(`${API_BASE}/contingency-tables/files/${encodeURIComponent(filename)}`);
    if (!response.ok) throw new Error(`Could not download ${filename} (HTTP ${response.status})`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = filename; anchor.click();
    URL.revokeObjectURL(url);
  }

  function downloadCsvContent(filename: string, content: string): void {
    const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function showRunFiles(instance: HTMLElement, files: Record<string, string>, ids: string[], stats: Stats, baseTimeHours: number[]): Promise<void> {
    const candidates = Object.keys(files).filter((name) => isCurrentRunFile(name, ids, baseTimeHours));
    const dates = candidates.map((name) => name.match(/date-(\d{8})/)?.[1] || "").sort();
    const latestDate = dates[dates.length - 1] || "";
    latestFiles = candidates.filter((name) => !latestDate || name.includes(`date-${latestDate}`));
    const instanceKey = instance.dataset.instance || "1";
    filesByInstance.set(instanceKey, latestFiles);
    const combinedDownloads: Array<{ filename: string; content: string }> = [];
    const panelMap: Record<string, string> = {
      table_a: "#panel-area-1", table_b: "#panel-track-1", table_c: "#panel-wind-1", table_d: "#panel-warning-1",
    };
    for (const [suffix, baseSelector] of Object.entries(panelMap)) {
      const panel = resetPanel(instance, baseSelector.replace(/-1$/, `-${instance.dataset.instance}`), `No ${suffix.replace("table_", "Table ").toUpperCase()} CSV returned for this selection.`);
      const matchingFiles = latestFiles.filter((name) =>
        !name.startsWith("combined_") && name.endsWith(`_${suffix}.csv`));
      if (panel && matchingFiles.length) {
        try {
          const texts = await Promise.all(matchingFiles.map(async (file) => {
            const response = await fetch(`${API_BASE}/contingency-tables/files/${encodeURIComponent(file)}`);
            if (!response.ok) throw new Error(`Could not load ${file} (HTTP ${response.status})`);
            return response.text();
          }));
          if (matchingFiles.length > 1 && ["table_a", "table_b", "table_c"].includes(suffix)) {
            combinedDownloads.push({
              filename: `combined_${suffix}_${latestDate}.csv`,
              content: combineCsvTexts(texts),
            });
          }
          panel.querySelector(".layer-note")?.remove();
          renderCsv(panel, texts);
        }
        catch (error) { instanceStatus(instance, (error as Error).message, true); }
      }
    }
    combinedFilesByInstance.set(instanceKey, combinedDownloads);
    const matrixPanel = resetPanel(instance, `#panel-summary-${instance.dataset.instance}`, "Summary for generated contingency tables.");
    if (matrixPanel) renderSummary(matrixPanel, stats);
    const downloadBox = document.createElement("div"); downloadBox.className = "results-downloads";
    const title = document.createElement("h3"); title.textContent = "Download individual CSVs and existing combined Table D"; downloadBox.appendChild(title);
    const list = document.createElement("ul");
    latestFiles.forEach((name) => {
      const li = document.createElement("li");
      const button = document.createElement("button"); button.type = "button"; button.textContent = `Download ${name}`;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try { await downloadFile(name); } catch (error) { instanceStatus(instance, (error as Error).message, true); }
        finally { button.disabled = false; }
      });
      li.appendChild(button); list.appendChild(li);
    });
    if (!latestFiles.length) { const li = document.createElement("li"); li.textContent = "No CSV files returned for the current date."; list.appendChild(li); }
    downloadBox.appendChild(list);
    if (combinedDownloads.length) {
      const combinedTitle = document.createElement("h3");
      combinedTitle.textContent = "Download combined Tables A–C";
      downloadBox.appendChild(combinedTitle);
      const combinedList = document.createElement("ul");
      combinedDownloads.forEach(({ filename, content }) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `Download ${filename}`;
        button.addEventListener("click", () => downloadCsvContent(filename, content));
        li.appendChild(button);
        combinedList.appendChild(li);
      });
      downloadBox.appendChild(combinedList);
    }
    const target = matrixPanel || instance;
    target.appendChild(downloadBox);
  }

  async function generateForInstance(instance: HTMLElement): Promise<void> {
    const cycloneSelect = instance.querySelector<HTMLSelectElement>(".cyclone-select");
    const stateSelect = instance.querySelector<HTMLSelectElement>(".state-select");
    const seasonSelect = instance.querySelector<HTMLSelectElement>(".season-select");
    if (!cycloneSelect || !stateSelect || !seasonSelect) return;
    const selectedIds = selected(cycloneSelect);
    const selectedStates = selected(stateSelect);
    const selectedSeasons = selected(seasonSelect);
    const baseTimeHours = Array.from(instance.querySelectorAll<HTMLInputElement>(".base-time-hour:checked"))
      .map((input) => Number(input.value));
    if (!selectedIds.length && !selectedSeasons.length) {
      instanceStatus(instance, "Choose one or more cyclones or seasons.", true); return;
    }
    if (!baseTimeHours.length) {
      instanceStatus(instance, "Select at least one UTC base time.", true); return;
    }
    const xHours = Number(instance.querySelector<HTMLInputElement>(".x-hours")?.value ?? 0);
    const yHours = Number(instance.querySelector<HTMLInputElement>(".y-hours")?.value ?? 24);
    if (!Number.isInteger(xHours) || xHours < 0 || !Number.isInteger(yHours) || yHours <= xHours) {
      instanceStatus(instance, "End offset must be a whole number greater than the start offset.", true); return;
    }

    const seasonsToRun = selectedSeasons.length ? selectedSeasons : [null];
    const statesToRun: Array<string | null> = selectedStates.length ? selectedStates : [null];
    const jobs: TableRequest[] = [];
    for (const season of seasonsToRun) {
      const seasonIds = selectedIds.length
        ? selectedIds.filter((id) => !season || disturbances.find((row) => row.disturbance_id === id)?.season === season)
        : disturbances.filter((row) => row.season === season).map((row) => row.disturbance_id);
      if (!seasonIds.length) continue;
      for (const state of statesToRun) {
        jobs.push({
          disturbance_ids: seasonIds,
          season,
          state,
          x_hours: xHours,
          y_hours: yHours,
          base_time_hours: baseTimeHours,
          forecast_level: instance.querySelector<HTMLSelectElement>(".warning-level")?.value || "warning",
        });
      }
    }
    if (!jobs.length) { instanceStatus(instance, "No cyclones match the selected season(s).", true); return; }

    const button = instance.querySelector<HTMLButtonElement>(".generate-table");
    const instanceKey = instance.dataset.instance || "1";
    filesByInstance.delete(instanceKey);
    combinedFilesByInstance.delete(instanceKey);
    if (button) button.disabled = true;
    instanceStatus(instance, `Generating ${jobs.length} table request(s)…`);
    try {
      // The API runs each expensive request as a background job so the browser
      // never holds Azure's front-end connection open for the full calculation.
      const results: ContingencyResponse[] = [];
      for (const [index, body] of jobs.entries()) {
        instanceStatus(instance, `Starting table request ${index + 1} of ${jobs.length}…`);
        const accepted = await requestJson<ContingencyJobAccepted>("/contingency-tables/", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        results.push(await waitForContingencyJob(instance, accepted.job_id, index + 1, jobs.length));
      }
      const combined: Stats = results.reduce((sum, result) => ({
        hit: sum.hit + result.stats.hit, false_alarm: sum.false_alarm + result.stats.false_alarm,
        miss: sum.miss + result.stats.miss, correct_negative: sum.correct_negative + result.stats.correct_negative,
        total: sum.total + result.stats.total,
      }), { hit: 0, false_alarm: 0, miss: 0, correct_negative: 0, total: 0 });
      const mergedFiles = Object.assign({}, ...results.map((result) => result.files));
      const ids = [...new Set(results.flatMap((result) => result.disturbance_ids))];
      await showRunFiles(instance, mergedFiles, ids, combined, baseTimeHours);
      instanceStatus(instance, `Generated ${results.length} request(s) for ${baseTimeHours.map((hour) => `${String(hour).padStart(2, "0")}:00`).join(", ")} UTC; ${ids.length} disturbance(s), ${combined.total} observations.`);
    } catch (error) {
      instanceStatus(instance, `Generation failed: ${(error as Error).message}`, true);
    } finally { if (button) button.disabled = false; }
  }

  function wireTabs(instance: HTMLElement): void {
    const tabs = [...instance.querySelectorAll<HTMLButtonElement>(".tab-button")];
    const panels = [...instance.querySelectorAll<HTMLElement>(".table-panel")];
    tabs.forEach((button, index) => {
      button.addEventListener("click", () => {
        tabs.forEach((tab) => {
          const active = tab === button;
          tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active)); tab.tabIndex = active ? 0 : -1;
        });
        panels.forEach((panel) => { panel.hidden = panel.getAttribute("aria-labelledby") !== button.id; });
      });
      button.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        event.preventDefault(); tabs[(index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length]?.focus();
      });
    });
  }

  function initializeInstance(instance: HTMLElement): void {
    populateInstanceFilters(instance);
    if (initializedInstances.has(instance)) return;
    initializedInstances.add(instance);
    wireTabs(instance);
    const cycloneSearch = instance.querySelector<HTMLInputElement>(".cyclone-search");
    const warningLevel = instance.querySelector<HTMLSelectElement>(".warning-level");
    // Warning = 0-24 h and Watch = 24-48 h of the base time.
    warningLevel?.addEventListener("change", () => {
      const hours = { warning: [0, 24], watch: [24, 48] }[warningLevel.value as "warning" | "watch"];
      if (!hours) return;
      instance.querySelector<HTMLInputElement>(".x-hours")!.value = String(hours[0]);
      instance.querySelector<HTMLInputElement>(".y-hours")!.value = String(hours[1]);
    });
    instance.querySelectorAll<HTMLSelectElement>("select:not(.warning-level)").forEach((select) => {
      wireMultiSelect(select, select.classList.contains("cyclone-select") ? cycloneSearch : null);
      select.addEventListener("change", updateContext);
    });
    instance.querySelectorAll<HTMLInputElement>(".base-time-hour").forEach((input) => input.addEventListener("change", updateContext));
    instance.querySelector<HTMLButtonElement>(".generate-table")?.addEventListener("click", () => { void generateForInstance(instance); });
  }

  function updateTableControls(): void {
    const addButton = byId<HTMLButtonElement>("addTableBtn");
    const maxed = tableInstances!.children.length >= 5;
    addButton.disabled = maxed;
    tableInstances!.querySelectorAll<HTMLButtonElement>(".remove-instance").forEach((button) => {
      button.disabled = button.closest<HTMLElement>(".table-instance")?.dataset.instance === "1";
    });
  }

  byId<HTMLButtonElement>("addTableBtn").addEventListener("click", () => {
    if (tableInstances.children.length >= 5) return;
    const numbers = [...tableInstances.children].map((child) => Number((child as HTMLElement).dataset.instance));
    const number = Math.max(...numbers) + 1;
    const clone = firstInstance.cloneNode(true) as HTMLElement;
    clone.dataset.instance = String(number);
    const heading = clone.querySelector("h2"); if (heading) heading.textContent = `Verification table ${number}`;
    clone.querySelectorAll<HTMLElement>("[id], [for], [aria-controls], [aria-labelledby]").forEach((element) => {
      ["id", "for", "aria-controls", "aria-labelledby"].forEach((attribute) => {
        const value = element.getAttribute(attribute); if (value) element.setAttribute(attribute, value.replace(/-1\b/g, `-${number}`));
      });
    });
    clone.querySelectorAll<HTMLElement>(".table-panel").forEach((panel, index) => {
      panel.hidden = index !== 0;
      panel.classList.toggle("active", index === 0);
    });
    clone.querySelectorAll<HTMLButtonElement>(".tab-button").forEach((tab, index) => {
      tab.classList.toggle("active", index === 0);
      tab.setAttribute("aria-selected", String(index === 0));
      tab.tabIndex = index === 0 ? 0 : -1;
    });
    clone.querySelectorAll<HTMLElement>(".instance-status").forEach((output) => { output.textContent = ""; output.classList.remove("error"); });
    clone.querySelectorAll(".results-downloads").forEach((output) => output.remove());
    clone.querySelectorAll(".api-result-table").forEach((output) => output.remove());
    clone.querySelectorAll(".metrics").forEach((output) => output.remove());
    filesByInstance.delete(String(number));
    combinedFilesByInstance.delete(String(number));
    tableInstances.appendChild(clone); initializeInstance(clone); updateTableControls(); updateContext();
  });

  tableInstances.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>(".remove-instance");
    if (button && !button.disabled) {
      const instance = button.closest<HTMLElement>(".table-instance");
      if (instance?.dataset.instance) {
        filesByInstance.delete(instance.dataset.instance);
        combinedFilesByInstance.delete(instance.dataset.instance);
      }
      instance?.remove(); updateTableControls(); updateContext();
    }
  });

  async function upload(file: File | null, endpoint: string, description: string): Promise<void> {
    byId<HTMLOListElement>("uploadBackendMessages").replaceChildren();
    updateUploadProgress(
      file ? "Preparing upload" : "Step 1 of 5 · Requesting BOM best track",
      file ? `${file.name} · ${formatBytes(file.size)} · ${description}` : description,
      file ? 0 : 10,
    );
    await uploadFile(file, endpoint, description);
    updateUploadProgress("Refreshing cyclone and state filters", `${description} processed. Updating available filter options…`);
    await loadFilterOptions();
    const sourceName = file?.name || "BOM best-track data";
    updateUploadProgress("Complete", `${sourceName} processed, and filter options refreshed.`, 100);
  }

  function wireUpload(inputId: string, buttonId: string, endpoint: string, description: string): void {
    const input = byId<HTMLInputElement>(inputId);
    const button = byId<HTMLButtonElement>(buttonId);
    button.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const file = input.files?.[0]; if (!file) return;
      const otherButton = byId<HTMLButtonElement>("refreshBestTrackBtn");
      button.disabled = true;
      otherButton.disabled = true;
      try { await upload(file, endpoint, description); }
      catch (error) {
        const message = `${description} upload failed: ${(error as Error).message}`;
        updateUploadProgress("Upload failed", message, 0);
        byId<HTMLDivElement>("uploadStatus").classList.add("error");
      }
      finally { input.value = ""; button.disabled = false; otherButton.disabled = false; }
    });
  }

  byId<HTMLButtonElement>("refreshBestTrackBtn").addEventListener("click", async () => {
    const button = byId<HTMLButtonElement>("refreshBestTrackBtn");
    const gmlButton = byId<HTMLButtonElement>("uploadGmlBtn");
    button.disabled = true;
    gmlButton.disabled = true;
    try {
      await upload(null, "refresh-best-track", "current BOM best-track CSV");
    } catch (error) {
      updateUploadProgress("Best-track refresh failed", (error as Error).message, 0);
      byId<HTMLDivElement>("uploadStatus").classList.add("error");
    } finally {
      button.disabled = false;
      gmlButton.disabled = false;
    }
  });

  byId<HTMLButtonElement>("downloadContingencyBtn").addEventListener("click", async () => {
    const filenames = [...new Set([...filesByInstance.values()].flat())];
    if (!filenames.length) { status("Generate a contingency table before downloading its CSV files.", true); return; }
    const button = byId<HTMLButtonElement>("downloadContingencyBtn"); button.disabled = true;
    const combinedFiles = [...combinedFilesByInstance.values()].flat();
    status(`Downloading ${filenames.length} individual and ${combinedFiles.length} combined contingency CSV file(s)…`);
    try {
      for (const filename of filenames) await downloadFile(filename);
      combinedFiles.forEach(({ filename, content }) => downloadCsvContent(filename, content));
      status(`Downloaded ${filenames.length} individual and ${combinedFiles.length} combined contingency CSV file(s).`);
    } catch (error) { status(`Contingency-table download failed: ${(error as Error).message}`, true); }
    finally { button.disabled = false; }
  });

  byId<HTMLButtonElement>("resetBtn").addEventListener("click", () => {
    while (tableInstances.children.length > 1) tableInstances.lastElementChild?.remove();
    for (const key of filesByInstance.keys()) if (key !== "1") filesByInstance.delete(key);
    for (const key of combinedFilesByInstance.keys()) if (key !== "1") combinedFilesByInstance.delete(key);
    populateInstanceFilters(firstInstance);
    filesByInstance.delete("1");
    combinedFilesByInstance.delete("1");
    restorePanelPlaceholders(firstInstance);
    firstInstance.querySelectorAll<HTMLElement>(".table-panel").forEach((panel, index) => { panel.hidden = index !== 0; });
    firstInstance.querySelectorAll<HTMLButtonElement>(".tab-button").forEach((tab, index) => {
      tab.classList.toggle("active", index === 0); tab.setAttribute("aria-selected", String(index === 0)); tab.tabIndex = index === 0 ? 0 : -1;
    });
    firstInstance.querySelectorAll<HTMLElement>(".instance-status").forEach((el) => { el.textContent = ""; el.classList.remove("error"); });
    firstInstance.querySelector<HTMLInputElement>(".x-hours")!.value = "0";
    firstInstance.querySelector<HTMLInputElement>(".y-hours")!.value = "24";
    firstInstance.querySelector<HTMLSelectElement>(".warning-level")!.value = "warning";
    firstInstance.querySelectorAll<HTMLInputElement>(".base-time-hour").forEach((input) => { input.checked = true; });
    byId<HTMLInputElement>("gmlUploadInput").value = "";
    byId<HTMLDivElement>("uploadProgress").hidden = true;
    status(""); updateTableControls(); updateContext();
  });

  byId<HTMLButtonElement>("backToVisualizer").addEventListener("click", () => { window.location.href = "visualize.html"; });
  wireUpload("gmlUploadInput", "uploadGmlBtn", "upload", "GML archive");
  initializeInstance(firstInstance);
  updateTableControls();
  updateContext();
  status("Loading cyclone and state filters…");
  void loadFilterOptions().then(() => {
    status("");
    const cyclone = firstInstance.querySelector<HTMLSelectElement>(".cyclone-select");
    if (savedContext.distId && cyclone && selected(cyclone).length) void generateForInstance(firstInstance);
  }).catch((error: unknown) => status(`Could not load filter options: ${(error as Error).message}`, true));
})();
