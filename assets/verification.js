"use strict";
// The API accepts one state and season per request; selected filters expand into request combinations.
(function () {
    "use strict";
    const API_BASE = "/api/v1";
    const ALL_VALUE = "__all__";
    const tableInstances = document.getElementById("tableInstances");
    const firstInstance = tableInstances === null || tableInstances === void 0 ? void 0 : tableInstances.querySelector(".table-instance");
    const savedContext = JSON.parse(localStorage.getItem("cycloneVerification") || "null") || {};
    let disturbances = [];
    let states = [];
    let latestFiles = [];
    const filesByInstance = new Map();
    const initializedInstances = new WeakSet();
    if (!tableInstances || !firstInstance)
        return;
    function byId(id) {
        const element = document.getElementById(id);
        if (!element)
            throw new Error(`Missing page element: ${id}`);
        return element;
    }
    function status(message, isError = false) {
        const element = byId("uploadStatus");
        element.textContent = message;
        element.classList.toggle("error", isError);
    }
    function updateUploadProgress(phase, detail, percentage) {
        const container = byId("uploadProgress");
        const label = byId("uploadPhase");
        const percentLabel = byId("uploadPercent");
        const progress = byId("uploadProgressBar");
        container.hidden = false;
        label.textContent = phase;
        status(detail);
        if (percentage === undefined) {
            progress.removeAttribute("value");
            percentLabel.textContent = "";
        }
        else {
            progress.value = percentage;
            percentLabel.textContent = `${percentage}%`;
        }
    }
    function uploadFile(file, endpoint, description) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const form = new FormData();
            form.append("file", file);
            xhr.open("POST", `${API_BASE}/datasets/${endpoint}`);
            xhr.responseType = "json";
            xhr.upload.addEventListener("progress", (event) => {
                if (!event.lengthComputable) {
                    updateUploadProgress("Uploading file", `${file.name} — ${formatBytes(event.loaded)} sent.`);
                    return;
                }
                const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
                updateUploadProgress("Uploading file", `${file.name} — ${formatBytes(event.loaded)} of ${formatBytes(event.total)} transferred.`, percent);
            });
            xhr.upload.addEventListener("load", () => {
                updateUploadProgress("Processing on server", `${file.name} uploaded. The server is validating and processing the ${description}; this may take a little while.`);
            });
            xhr.addEventListener("load", () => {
                const payload = xhr.response;
                if (xhr.status < 200 || xhr.status >= 300) {
                    reject(new Error((payload === null || payload === void 0 ? void 0 : payload.detail) || `Upload failed (HTTP ${xhr.status}).`));
                    return;
                }
                resolve();
            });
            xhr.addEventListener("error", () => reject(new Error("Network error while uploading. Check your connection and try again.")));
            xhr.addEventListener("abort", () => reject(new Error("Upload was cancelled.")));
            xhr.send(form);
        });
    }
    function formatBytes(bytes) {
        if (bytes < 1024)
            return `${bytes} B`;
        const units = ["KB", "MB", "GB"];
        let size = bytes / 1024;
        let unit = units[0];
        for (let index = 1; size >= 1024 && index < units.length; index += 1) {
            size /= 1024;
            unit = units[index];
        }
        return `${size.toFixed(1)} ${unit}`;
    }
    async function requestJson(path, init) {
        const response = await fetch(`${API_BASE}${path}`, init);
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
            const detail = typeof payload === "object" && payload !== null && "detail" in payload
                ? String(payload.detail)
                : `HTTP ${response.status}`;
            throw new Error(detail);
        }
        return payload;
    }
    async function loadDisturbances() {
        const result = [];
        let offset = 0;
        const limit = 500;
        while (true) {
            const page = await requestJson(`/disturbances?limit=${limit}&offset=${offset}`);
            result.push(...page.items);
            offset += page.items.length;
            if (offset >= page.total || page.items.length === 0)
                return result;
        }
    }
    async function loadFilterOptions() {
        const [disturbanceRows, townRows] = await Promise.all([
            loadDisturbances(),
            requestJson("/towns"),
        ]);
        disturbances = disturbanceRows;
        states = [...new Set(townRows.map((town) => town.state).filter(Boolean))].sort();
        document.querySelectorAll(".table-instance").forEach(populateInstanceFilters);
    }
    function selected(select) {
        return Array.from(select.selectedOptions).map((option) => option.value).filter((value) => value !== ALL_VALUE);
    }
    function populateSelect(select, options, defaults) {
        select.replaceChildren(...options.map(({ value, label }) => new Option(label, value)));
        const available = new Set(options.map((option) => option.value));
        const chosen = defaults.filter((value) => available.has(value));
        if (!chosen.length)
            chosen.push(ALL_VALUE);
        Array.from(select.options).forEach((option) => { option.selected = chosen.includes(option.value); });
    }
    function populateInstanceFilters(instance) {
        const cycloneSelect = instance.querySelector(".cyclone-select");
        const stateSelect = instance.querySelector(".state-select");
        const seasonSelect = instance.querySelector(".season-select");
        if (!cycloneSelect || !stateSelect || !seasonSelect)
            return;
        const cycloneOptions = disturbances.slice().sort((a, b) => a.disturbance_id.localeCompare(b.disturbance_id))
            .map((row) => ({ value: row.disturbance_id, label: `${row.name || row.disturbance_id} — ${row.disturbance_id}` }));
        populateSelect(cycloneSelect, [{ value: ALL_VALUE, label: "Any cyclone (select a season)" }, ...cycloneOptions], instance === firstInstance && savedContext.distId ? [savedContext.distId] : [ALL_VALUE]);
        populateSelect(stateSelect, [{ value: ALL_VALUE, label: "All states" }, ...states.map((value) => ({ value, label: value }))], [ALL_VALUE]);
        const seasons = [...new Set(disturbances.map((row) => row.season).filter((value) => Boolean(value)))].sort().reverse();
        populateSelect(seasonSelect, [{ value: ALL_VALUE, label: "All seasons" }, ...seasons.map((value) => ({ value, label: value }))], instance === firstInstance && savedContext.season ? [savedContext.season] : [ALL_VALUE]);
        updateContext();
    }
    function updateContext() {
        const context = byId("context");
        const descriptions = Array.from(tableInstances.querySelectorAll(".table-instance")).map((instance) => {
            const ids = selected(instance.querySelector(".cyclone-select"));
            const stateValues = selected(instance.querySelector(".state-select"));
            const seasons = selected(instance.querySelector(".season-select"));
            return `${ids.length ? `${ids.length} cyclone(s)` : "season-based selection"}; ${stateValues.length ? stateValues.join(", ") : "all states"}; ${seasons.length ? seasons.join(", ") : "all seasons"}`;
        });
        context.textContent = `Contingency table filters: ${descriptions.join(" | ")}${savedContext.bulletin ? `; visualizer bulletin ${savedContext.bulletin}` : ""}.`;
    }
    function instanceStatus(instance, message, isError = false) {
        const output = instance.querySelector(".instance-status");
        if (output) {
            output.textContent = message;
            output.classList.toggle("error", isError);
        }
    }
    function resetPanel(instance, panelSelector, label) {
        const panel = instance.querySelector(panelSelector);
        if (!panel)
            return null;
        panel.replaceChildren();
        const heading = document.createElement("p");
        heading.className = "layer-note";
        heading.textContent = label;
        panel.appendChild(heading);
        return panel;
    }
    function restorePanelPlaceholders(instance) {
        const number = instance.dataset.instance || "1";
        resetPanel(instance, `#panel-area-${number}`, "Generate tables to load Table A from the API.");
        ["track", "wind", "warning"].forEach((panel) => resetPanel(instance, `#panel-${panel}-${number}`, `Generate tables to load Table ${panel.toUpperCase()} from the API.`));
        resetPanel(instance, `#panel-summary-${number}`, "Generate tables to load the combined contingency matrix and skill scores.");
    }
    function csvRows(text) {
        const rows = [];
        let row = [];
        let cell = "";
        let quoted = false;
        for (let i = 0; i < text.length; i += 1) {
            const char = text[i];
            if (char === '"' && quoted && text[i + 1] === '"') {
                cell += '"';
                i += 1;
            }
            else if (char === '"')
                quoted = !quoted;
            else if (char === "," && !quoted) {
                row.push(cell);
                cell = "";
            }
            else if ((char === "\n" || char === "\r") && !quoted) {
                if (char === "\r" && text[i + 1] === "\n")
                    i += 1;
                row.push(cell);
                cell = "";
                if (row.some((value) => value.length))
                    rows.push(row);
                row = [];
            }
            else
                cell += char;
        }
        if (cell.length || row.length) {
            row.push(cell);
            rows.push(row);
        }
        return rows;
    }
    function renderCsv(panel, text) {
        const rows = csvRows(text);
        if (!rows.length)
            return;
        const table = document.createElement("table");
        table.className = "contingency-table api-result-table";
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
                if (index === 0)
                    cell.scope = "row";
                cell.textContent = value;
                tr.appendChild(cell);
            });
            body.appendChild(tr);
        });
        table.appendChild(body);
        panel.appendChild(table);
    }
    function formatPercent(numerator, denominator) {
        return denominator ? `${(numerator / denominator * 100).toFixed(1)}%` : "—";
    }
    function renderSummary(panel, stats) {
        const hit = stats.hit;
        const falseAlarm = stats.false_alarm;
        const miss = stats.miss;
        const correctNegative = stats.correct_negative;
        const precision = hit + falseAlarm ? hit / (hit + falseAlarm) : 0;
        const recall = hit + miss ? hit / (hit + miss) : 0;
        const items = [
            ["Accuracy", formatPercent(hit + correctNegative, stats.total)],
            ["Precision", formatPercent(hit, hit + falseAlarm)],
            ["Recall", formatPercent(hit, hit + miss)],
            ["F1 score", precision + recall ? `${(2 * precision * recall / (precision + recall) * 100).toFixed(1)}%` : "—"],
            ["POD", formatPercent(hit, hit + miss)],
            ["FAR", formatPercent(falseAlarm, hit + falseAlarm)],
            ["CSI", formatPercent(hit, hit + falseAlarm + miss)],
            ["Bias", hit + miss ? ((hit + falseAlarm) / (hit + miss)).toFixed(2) : "—"],
        ];
        const metrics = document.createElement("div");
        metrics.className = "metrics";
        items.forEach(([label, value]) => {
            const span = document.createElement("span");
            span.append(`${label} `);
            const strong = document.createElement("b");
            strong.textContent = value;
            span.appendChild(strong);
            metrics.appendChild(span);
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
                if (index === 0)
                    cell.scope = "row";
                cell.textContent = String(value);
                tr.appendChild(cell);
            });
            body.appendChild(tr);
        });
        table.appendChild(body);
        panel.append(table, metrics);
    }
    function isCurrentRunFile(name, ids) {
        return name.startsWith("combined_") || ids.some((id) => name.startsWith(`${id}_`));
    }
    async function downloadFile(filename) {
        const response = await fetch(`${API_BASE}/contingency-tables/files/${encodeURIComponent(filename)}`);
        if (!response.ok)
            throw new Error(`Could not download ${filename} (HTTP ${response.status})`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        anchor.click();
        URL.revokeObjectURL(url);
    }
    async function showRunFiles(instance, files, ids, stats) {
        const candidates = Object.keys(files).filter((name) => isCurrentRunFile(name, ids));
        const dates = candidates.map((name) => { var _a; return ((_a = name.match(/date-(\d{8})/)) === null || _a === void 0 ? void 0 : _a[1]) || ""; }).sort();
        const latestDate = dates[dates.length - 1] || "";
        latestFiles = candidates.filter((name) => !latestDate || name.includes(`date-${latestDate}`));
        filesByInstance.set(instance.dataset.instance || "1", latestFiles);
        const panelMap = {
            table_a: "#panel-area-1", table_b: "#panel-track-1", table_c: "#panel-wind-1", table_d: "#panel-warning-1",
        };
        for (const [suffix, baseSelector] of Object.entries(panelMap)) {
            const panel = resetPanel(instance, baseSelector.replace(/-1$/, `-${instance.dataset.instance}`), `No ${suffix.replace("table_", "Table ").toUpperCase()} CSV returned for this selection.`);
            const file = latestFiles.find((name) => name.endsWith(`_${suffix}.csv`));
            if (panel && file) {
                try {
                    const response = await fetch(`${API_BASE}/contingency-tables/files/${encodeURIComponent(file)}`);
                    if (!response.ok)
                        throw new Error(`Could not load ${file} (HTTP ${response.status})`);
                    renderCsv(panel, await response.text());
                }
                catch (error) {
                    instanceStatus(instance, error.message, true);
                }
            }
        }
        const matrixPanel = resetPanel(instance, `#panel-summary-${instance.dataset.instance}`, "Summary for generated contingency tables.");
        if (matrixPanel)
            renderSummary(matrixPanel, stats);
        const downloadBox = document.createElement("div");
        downloadBox.className = "results-downloads";
        const title = document.createElement("h3");
        title.textContent = "Download generated CSV files";
        downloadBox.appendChild(title);
        const list = document.createElement("ul");
        latestFiles.forEach((name) => {
            const li = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = `Download ${name}`;
            button.addEventListener("click", async () => {
                button.disabled = true;
                try {
                    await downloadFile(name);
                }
                catch (error) {
                    instanceStatus(instance, error.message, true);
                }
                finally {
                    button.disabled = false;
                }
            });
            li.appendChild(button);
            list.appendChild(li);
        });
        if (!latestFiles.length) {
            const li = document.createElement("li");
            li.textContent = "No CSV files returned for the current date.";
            list.appendChild(li);
        }
        downloadBox.appendChild(list);
        const target = matrixPanel || instance;
        target.appendChild(downloadBox);
    }
    async function generateForInstance(instance) {
        var _a, _b, _c, _d;
        const cycloneSelect = instance.querySelector(".cyclone-select");
        const stateSelect = instance.querySelector(".state-select");
        const seasonSelect = instance.querySelector(".season-select");
        if (!cycloneSelect || !stateSelect || !seasonSelect)
            return;
        const selectedIds = selected(cycloneSelect);
        const selectedStates = selected(stateSelect);
        const selectedSeasons = selected(seasonSelect);
        if (!selectedIds.length && !selectedSeasons.length) {
            instanceStatus(instance, "Choose one or more cyclones or seasons.", true);
            return;
        }
        const xHours = Number((_b = (_a = instance.querySelector(".x-hours")) === null || _a === void 0 ? void 0 : _a.value) !== null && _b !== void 0 ? _b : 0);
        const yHours = Number((_d = (_c = instance.querySelector(".y-hours")) === null || _c === void 0 ? void 0 : _c.value) !== null && _d !== void 0 ? _d : 24);
        if (!Number.isInteger(xHours) || xHours < 0 || !Number.isInteger(yHours) || yHours <= xHours) {
            instanceStatus(instance, "End offset must be a whole number greater than the start offset.", true);
            return;
        }
        const seasonsToRun = selectedSeasons.length ? selectedSeasons : [null];
        const statesToRun = selectedStates.length ? selectedStates : [null];
        const jobs = [];
        for (const season of seasonsToRun) {
            const seasonIds = selectedIds.length
                ? selectedIds.filter((id) => { var _a; return !season || ((_a = disturbances.find((row) => row.disturbance_id === id)) === null || _a === void 0 ? void 0 : _a.season) === season; })
                : disturbances.filter((row) => row.season === season).map((row) => row.disturbance_id);
            if (!seasonIds.length)
                continue;
            for (const state of statesToRun)
                jobs.push({ disturbance_ids: seasonIds, season, state, x_hours: xHours, y_hours: yHours });
        }
        if (!jobs.length) {
            instanceStatus(instance, "No cyclones match the selected season(s).", true);
            return;
        }
        const button = instance.querySelector(".generate-table");
        filesByInstance.delete(instance.dataset.instance || "1");
        if (button)
            button.disabled = true;
        instanceStatus(instance, `Generating ${jobs.length} table request(s)…`);
        try {
            // Multiple seasons/states are expanded to the backend's singular filters.
            const results = [];
            for (const body of jobs) {
                results.push(await requestJson("/contingency-tables/", {
                    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                }));
            }
            const combined = results.reduce((sum, result) => ({
                hit: sum.hit + result.stats.hit, false_alarm: sum.false_alarm + result.stats.false_alarm,
                miss: sum.miss + result.stats.miss, correct_negative: sum.correct_negative + result.stats.correct_negative,
                total: sum.total + result.stats.total,
            }), { hit: 0, false_alarm: 0, miss: 0, correct_negative: 0, total: 0 });
            const mergedFiles = Object.assign({}, ...results.map((result) => result.files));
            const ids = [...new Set(results.flatMap((result) => result.disturbance_ids))];
            await showRunFiles(instance, mergedFiles, ids, combined);
            instanceStatus(instance, `Generated ${results.length} request(s); ${ids.length} disturbance(s), ${combined.total} observations.`);
        }
        catch (error) {
            instanceStatus(instance, `Generation failed: ${error.message}`, true);
        }
        finally {
            if (button)
                button.disabled = false;
        }
    }
    function wireTabs(instance) {
        const tabs = [...instance.querySelectorAll(".tab-button")];
        const panels = [...instance.querySelectorAll(".table-panel")];
        tabs.forEach((button, index) => {
            button.addEventListener("click", () => {
                tabs.forEach((tab) => {
                    const active = tab === button;
                    tab.classList.toggle("active", active);
                    tab.setAttribute("aria-selected", String(active));
                    tab.tabIndex = active ? 0 : -1;
                });
                panels.forEach((panel) => { panel.hidden = panel.getAttribute("aria-labelledby") !== button.id; });
            });
            button.addEventListener("keydown", (event) => {
                var _a;
                if (event.key !== "ArrowRight" && event.key !== "ArrowLeft")
                    return;
                event.preventDefault();
                (_a = tabs[(index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length]) === null || _a === void 0 ? void 0 : _a.focus();
            });
        });
    }
    function initializeInstance(instance) {
        var _a;
        populateInstanceFilters(instance);
        if (initializedInstances.has(instance))
            return;
        initializedInstances.add(instance);
        wireTabs(instance);
        instance.querySelectorAll("select").forEach((select) => select.addEventListener("change", updateContext));
        (_a = instance.querySelector(".generate-table")) === null || _a === void 0 ? void 0 : _a.addEventListener("click", () => { void generateForInstance(instance); });
    }
    function updateTableControls() {
        const addButton = byId("addTableBtn");
        const maxed = tableInstances.children.length >= 5;
        addButton.disabled = maxed;
        tableInstances.querySelectorAll(".remove-instance").forEach((button) => {
            var _a;
            button.disabled = ((_a = button.closest(".table-instance")) === null || _a === void 0 ? void 0 : _a.dataset.instance) === "1";
        });
    }
    byId("addTableBtn").addEventListener("click", () => {
        if (tableInstances.children.length >= 5)
            return;
        const numbers = [...tableInstances.children].map((child) => Number(child.dataset.instance));
        const number = Math.max(...numbers) + 1;
        const clone = firstInstance.cloneNode(true);
        clone.dataset.instance = String(number);
        const heading = clone.querySelector("h2");
        if (heading)
            heading.textContent = `Verification table ${number}`;
        clone.querySelectorAll("[id], [for], [aria-controls], [aria-labelledby]").forEach((element) => {
            ["id", "for", "aria-controls", "aria-labelledby"].forEach((attribute) => {
                const value = element.getAttribute(attribute);
                if (value)
                    element.setAttribute(attribute, value.replace(/-1\b/g, `-${number}`));
            });
        });
        clone.querySelectorAll(".table-panel").forEach((panel, index) => {
            panel.hidden = index !== 0;
            panel.classList.toggle("active", index === 0);
        });
        clone.querySelectorAll(".tab-button").forEach((tab, index) => {
            tab.classList.toggle("active", index === 0);
            tab.setAttribute("aria-selected", String(index === 0));
            tab.tabIndex = index === 0 ? 0 : -1;
        });
        clone.querySelectorAll(".instance-status").forEach((output) => { output.textContent = ""; output.classList.remove("error"); });
        clone.querySelectorAll(".results-downloads").forEach((output) => output.remove());
        clone.querySelectorAll(".api-result-table").forEach((output) => output.remove());
        clone.querySelectorAll(".metrics").forEach((output) => output.remove());
        filesByInstance.delete(String(number));
        tableInstances.appendChild(clone);
        initializeInstance(clone);
        updateTableControls();
        updateContext();
    });
    tableInstances.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof Element))
            return;
        const button = target.closest(".remove-instance");
        if (button && !button.disabled) {
            const instance = button.closest(".table-instance");
            if (instance === null || instance === void 0 ? void 0 : instance.dataset.instance)
                filesByInstance.delete(instance.dataset.instance);
            instance === null || instance === void 0 ? void 0 : instance.remove();
            updateTableControls();
            updateContext();
        }
    });
    async function upload(file, endpoint, description) {
        updateUploadProgress("Preparing upload", `${file.name} · ${formatBytes(file.size)} · ${description}`, 0);
        await uploadFile(file, endpoint, description);
        updateUploadProgress("Refreshing cyclone and state filters", `${description} processed. Updating available filter options…`);
        await loadFilterOptions();
        updateUploadProgress("Complete", `${file.name} uploaded, processed, and filter options refreshed.`, 100);
    }
    function wireUpload(inputId, buttonId, endpoint, description) {
        const input = byId(inputId);
        const button = byId(buttonId);
        button.addEventListener("click", () => input.click());
        input.addEventListener("change", async () => {
            var _a;
            const file = (_a = input.files) === null || _a === void 0 ? void 0 : _a[0];
            if (!file)
                return;
            const otherButtonId = buttonId === "uploadGmlBtn" ? "uploadBestTrackBtn" : "uploadGmlBtn";
            const otherButton = byId(otherButtonId);
            button.disabled = true;
            otherButton.disabled = true;
            try {
                await upload(file, endpoint, description);
            }
            catch (error) {
                const message = `${description} upload failed: ${error.message}`;
                updateUploadProgress("Upload failed", message, 0);
                byId("uploadStatus").classList.add("error");
            }
            finally {
                input.value = "";
                button.disabled = false;
                otherButton.disabled = false;
            }
        });
    }
    byId("downloadContingencyBtn").addEventListener("click", async () => {
        const filenames = [...new Set([...filesByInstance.values()].flat())];
        if (!filenames.length) {
            status("Generate a contingency table before downloading its CSV files.", true);
            return;
        }
        const button = byId("downloadContingencyBtn");
        button.disabled = true;
        status(`Downloading ${filenames.length} contingency CSV file(s)…`);
        try {
            for (const filename of filenames)
                await downloadFile(filename);
            status(`Downloaded ${filenames.length} contingency CSV file(s).`);
        }
        catch (error) {
            status(`Contingency-table download failed: ${error.message}`, true);
        }
        finally {
            button.disabled = false;
        }
    });
    byId("resetBtn").addEventListener("click", () => {
        var _a;
        while (tableInstances.children.length > 1)
            (_a = tableInstances.lastElementChild) === null || _a === void 0 ? void 0 : _a.remove();
        for (const key of filesByInstance.keys())
            if (key !== "1")
                filesByInstance.delete(key);
        populateInstanceFilters(firstInstance);
        filesByInstance.delete("1");
        restorePanelPlaceholders(firstInstance);
        firstInstance.querySelectorAll(".table-panel").forEach((panel, index) => { panel.hidden = index !== 0; });
        firstInstance.querySelectorAll(".tab-button").forEach((tab, index) => {
            tab.classList.toggle("active", index === 0);
            tab.setAttribute("aria-selected", String(index === 0));
            tab.tabIndex = index === 0 ? 0 : -1;
        });
        firstInstance.querySelectorAll(".instance-status").forEach((el) => { el.textContent = ""; el.classList.remove("error"); });
        firstInstance.querySelector(".x-hours").value = "0";
        firstInstance.querySelector(".y-hours").value = "24";
        byId("gmlUploadInput").value = "";
        byId("bestTrackUploadInput").value = "";
        byId("uploadProgress").hidden = true;
        status("");
        updateTableControls();
        updateContext();
    });
    byId("backToVisualizer").addEventListener("click", () => { window.location.href = "visualize.html"; });
    wireUpload("gmlUploadInput", "uploadGmlBtn", "upload", "GML archive");
    wireUpload("bestTrackUploadInput", "uploadBestTrackBtn", "upload-best-track", "best-track CSV");
    initializeInstance(firstInstance);
    updateTableControls();
    updateContext();
    status("Loading cyclone and state filters…");
    void loadFilterOptions().then(() => {
        status("");
        const cyclone = firstInstance.querySelector(".cyclone-select");
        if (savedContext.distId && cyclone && selected(cyclone).length)
            void generateForInstance(firstInstance);
    }).catch((error) => status(`Could not load filter options: ${error.message}`, true));
})();
