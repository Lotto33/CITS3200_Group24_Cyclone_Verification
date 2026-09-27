"use strict";
/**
 * verification.html front end.
 *
 * Calls the FastAPI contingency-tables endpoint (POST /api/v1/contingency-tables/)
 * to build a real 2x2 contingency table + skill scores for the "Area
 * classification" tab. The other tabs (track accuracy, wind prediction,
 * warning lead time, summary metrics) have no backend endpoint yet, so they
 * stay as the illustrative dummy tables already in verification.html.
 *
 * The filters below are deliberately built around arrays of ids
 * (`selectedDisturbanceIds`) even though today's UI only exposes single
 * <select> elements: the backend request already accepts multiple
 * `disturbance_ids`, so swapping the typhoon/season controls for multi-select
 * later only means changing how `selectedDisturbanceIds`/`selectedSeasons`
 * are read, not the request-building or rendering code.
 *
 * File upload and download are out of scope here (tracked separately) --
 * this page only renders disabled placeholder controls for them.
 */
(function () {
    "use strict";
    const API_BASE = "api/v1";
    const ALL_VALUE = ""; // "All states" / "All seasons" / "None selected" sentinel
    const els = {
        typhoon: document.getElementById("typhoonSelect"),
        state: document.getElementById("stateSelect"),
        season: document.getElementById("seasonSelect"),
        xHours: document.getElementById("xHoursInput"),
        yHours: document.getElementById("yHoursInput"),
        coastalBuffer: document.getElementById("coastalBufferInput"),
        relevance: document.getElementById("relevanceInput"),
        generateButton: document.getElementById("generateButton"),
        uploadButton: document.getElementById("uploadButton"),
        downloadList: document.getElementById("downloadList"),
        matchedDisturbances: document.getElementById("matchedDisturbances"),
        apiStatus: document.getElementById("apiStatus"),
        context: document.getElementById("context"),
        backToVisualizer: document.getElementById("backToVisualizer"),
        cellTP: document.getElementById("cellTP"),
        cellFP: document.getElementById("cellFP"),
        cellFN: document.getElementById("cellFN"),
        cellTN: document.getElementById("cellTN"),
        cellPredYesTotal: document.getElementById("cellPredYesTotal"),
        cellPredNoTotal: document.getElementById("cellPredNoTotal"),
        cellObsYesTotal: document.getElementById("cellObsYesTotal"),
        cellObsNoTotal: document.getElementById("cellObsNoTotal"),
        cellGrandTotal: document.getElementById("cellGrandTotal"),
        metricAccuracy: document.getElementById("metricAccuracy"),
        metricPrecision: document.getElementById("metricPrecision"),
        metricRecall: document.getElementById("metricRecall"),
        metricF1: document.getElementById("metricF1"),
        metricPod: document.getElementById("metricPod"),
        metricFar: document.getElementById("metricFar"),
        metricCsi: document.getElementById("metricCsi"),
        metricBias: document.getElementById("metricBias"),
    };
    const savedContext = JSON.parse(localStorage.getItem("cycloneVerification") || "null") || {};
    let disturbances = [];
    function setApiStatus(message, isError) {
        els.apiStatus.textContent = message;
        els.apiStatus.className = isError ? "api-status error" : "api-status";
    }
    // ---- Filter data -------------------------------------------------------
    async function fetchAllDisturbances() {
        const limit = 500;
        let offset = 0;
        const items = [];
        for (;;) {
            const res = await fetch(`${API_BASE}/disturbances?limit=${limit}&offset=${offset}`);
            if (!res.ok)
                throw new Error(`GET /disturbances failed (HTTP ${res.status})`);
            const page = await res.json();
            items.push(...page.items);
            offset += page.items.length;
            if (offset >= page.total || page.items.length === 0)
                break;
        }
        return items;
    }
    function populateFilters() {
        const typhoonOptions = [...disturbances].sort((a, b) => a.disturbance_id.localeCompare(b.disturbance_id));
        els.typhoon.replaceChildren(new Option("— none (use season / state filters only) —", ALL_VALUE), ...typhoonOptions.map((d) => new Option(`${d.name || d.disturbance_id} — ${d.disturbance_id}`, d.disturbance_id)));
        const regions = Array.from(new Set(disturbances.map((d) => d.region).filter((r) => Boolean(r)))).sort();
        els.state.replaceChildren(new Option("All states", ALL_VALUE), ...regions.map((r) => new Option(r, r)));
        const seasons = Array.from(new Set(disturbances.map((d) => d.season).filter((s) => Boolean(s)))).sort()
            .reverse();
        els.season.replaceChildren(new Option("All seasons", ALL_VALUE), ...seasons.map((s) => new Option(s, s)));
        els.typhoon.value = savedContext.distId || ALL_VALUE;
        els.state.value = savedContext.region || ALL_VALUE;
        els.season.value = savedContext.season || ALL_VALUE;
        if (els.typhoon.value !== (savedContext.distId || ALL_VALUE)) {
            els.typhoon.value = ALL_VALUE; // saved cyclone no longer in the list
        }
    }
    function updateContextLine() {
        var _a;
        const typhoonLabel = els.typhoon.value === ALL_VALUE
            ? "any cyclone"
            : ((_a = els.typhoon.options[els.typhoon.selectedIndex]) === null || _a === void 0 ? void 0 : _a.text) || els.typhoon.value;
        const stateLabel = els.state.value === ALL_VALUE ? "all states" : els.state.value;
        const seasonLabel = els.season.value === ALL_VALUE ? "all seasons" : els.season.value;
        els.context.textContent = `Contingency table for ${typhoonLabel}, ${stateLabel}, ${seasonLabel}.`;
    }
    // ---- Request building ---------------------------------------------------
    function selectedDisturbanceIds() {
        // Single-select today; a future multi-select control would just return
        // more than one value here without touching anything downstream.
        return els.typhoon.value === ALL_VALUE ? [] : [els.typhoon.value];
    }
    function buildRequest() {
        return {
            disturbance_ids: selectedDisturbanceIds(),
            season: els.season.value === ALL_VALUE ? null : els.season.value,
            state: els.state.value === ALL_VALUE ? null : els.state.value,
            x_hours: Number(els.xHours.value) || 0,
            y_hours: Number(els.yHours.value) || 24,
            coastal_buffer_km: Number(els.coastalBuffer.value) || 20,
            relevance_km: Number(els.relevance.value) || 300,
        };
    }
    function validate(request) {
        if (request.disturbance_ids.length === 0 && !request.season) {
            return "Pick a cyclone, or a season, before generating the table.";
        }
        return null;
    }
    // ---- Rendering -----------------------------------------------------------
    function renderMatrix(stats) {
        const { hit, false_alarm, miss, correct_negative, total } = stats;
        els.cellTP.textContent = `${hit} (TP)`;
        els.cellFP.textContent = `${false_alarm} (FP)`;
        els.cellFN.textContent = `${miss} (FN)`;
        els.cellTN.textContent = `${correct_negative} (TN)`;
        els.cellPredYesTotal.textContent = String(hit + false_alarm);
        els.cellPredNoTotal.textContent = String(miss + correct_negative);
        els.cellObsYesTotal.textContent = String(hit + miss);
        els.cellObsNoTotal.textContent = String(false_alarm + correct_negative);
        els.cellGrandTotal.textContent = String(total);
    }
    function pct(numerator, denominator) {
        return denominator > 0 ? `${((numerator / denominator) * 100).toFixed(1)}%` : "—";
    }
    function renderMetrics(stats) {
        const { hit, false_alarm, miss, correct_negative, total } = stats;
        // Standard verification metrics.
        els.metricAccuracy.textContent = pct(hit + correct_negative, total);
        els.metricPrecision.textContent = pct(hit, hit + false_alarm);
        els.metricRecall.textContent = pct(hit, hit + miss);
        const precision = hit / (hit + false_alarm);
        const recall = hit / (hit + miss);
        els.metricF1.textContent =
            precision > 0 && recall > 0 && Number.isFinite(precision) && Number.isFinite(recall)
                ? `${(((2 * precision * recall) / (precision + recall)) * 100).toFixed(1)}%`
                : "—";
        // Meteorological skill scores, matching app/schemas/verification.py's
        // ContingencySummary computed_fields (pod/far/csi/bias) so this page uses
        // the same vocabulary as the API and gen_cont_tables.py output.
        els.metricPod.textContent = pct(hit, hit + miss);
        els.metricFar.textContent = pct(false_alarm, hit + false_alarm);
        els.metricCsi.textContent = pct(hit, hit + false_alarm + miss);
        els.metricBias.textContent =
            hit + miss > 0 ? ((hit + false_alarm) / (hit + miss)).toFixed(2) : "—";
    }
    function renderMatchedDisturbances(ids) {
        els.matchedDisturbances.textContent =
            ids.length > 0
                ? `Matched ${ids.length} disturbance${ids.length === 1 ? "" : "s"}: ${ids.join(", ")}`
                : "";
    }
    function renderFiles(files) {
        const filenames = Object.keys(files);
        els.downloadList.replaceChildren(...(filenames.length
            ? filenames.map((name) => {
                const li = document.createElement("li");
                const button = document.createElement("button");
                button.type = "button";
                button.className = "placeholder-button";
                button.textContent = `Download ${name}`;
                button.disabled = true;
                button.title = "File download is not wired up yet";
                li.appendChild(button);
                return li;
            })
            : [(() => {
                    const li = document.createElement("li");
                    li.className = "layer-note";
                    li.textContent = "No CSV files reported for this run.";
                    return li;
                })()]));
    }
    // ---- Main action ---------------------------------------------------------
    async function generateContingencyTable() {
        const request = buildRequest();
        const validationError = validate(request);
        if (validationError) {
            setApiStatus(validationError, true);
            return;
        }
        els.generateButton.disabled = true;
        setApiStatus("Generating contingency table…");
        try {
            const res = await fetch(`${API_BASE}/contingency-tables/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(request),
            });
            const body = await res.json();
            if (!res.ok) {
                throw new Error((body === null || body === void 0 ? void 0 : body.detail) || `HTTP ${res.status}`);
            }
            const response = body;
            renderMatrix(response.stats);
            renderMetrics(response.stats);
            renderMatchedDisturbances(response.disturbance_ids);
            renderFiles(response.files);
            setApiStatus(`Done — ${response.status}.`);
        }
        catch (err) {
            setApiStatus(`Could not generate contingency table — ${err.message}`, true);
        }
        finally {
            els.generateButton.disabled = false;
        }
    }
    // ---- Tabs (unchanged behaviour, just moved out of inline <script>) ------
    function wireTabs() {
        const tabButtons = [...document.querySelectorAll(".tab-button")];
        const tablePanels = [...document.querySelectorAll(".table-panel")];
        tabButtons.forEach((button, index) => {
            button.addEventListener("click", () => {
                tabButtons.forEach((tab) => {
                    const isSelected = tab === button;
                    tab.classList.toggle("active", isSelected);
                    tab.setAttribute("aria-selected", String(isSelected));
                    tab.tabIndex = isSelected ? 0 : -1;
                });
                tablePanels.forEach((panel) => {
                    panel.hidden = panel.getAttribute("aria-labelledby") !== button.id;
                });
            });
            button.addEventListener("keydown", (event) => {
                var _a;
                if (event.key !== "ArrowRight" && event.key !== "ArrowLeft")
                    return;
                event.preventDefault();
                const offset = event.key === "ArrowRight" ? 1 : -1;
                (_a = tabButtons[(index + offset + tabButtons.length) % tabButtons.length]) === null || _a === void 0 ? void 0 : _a.focus();
            });
        });
    }
    // ---- Init -----------------------------------------------------------------
    async function init() {
        wireTabs();
        els.backToVisualizer.addEventListener("click", () => {
            window.location.href = "visualize.html";
        });
        els.uploadButton.addEventListener("click", () => {
            setApiStatus("File upload is not implemented yet.", true);
        });
        [els.typhoon, els.state, els.season].forEach((select) => select.addEventListener("change", updateContextLine));
        els.generateButton.addEventListener("click", () => {
            void generateContingencyTable();
        });
        setApiStatus("Loading cyclones…");
        try {
            disturbances = await fetchAllDisturbances();
            populateFilters();
            updateContextLine();
            setApiStatus("");
            if (selectedDisturbanceIds().length > 0 || els.season.value !== ALL_VALUE) {
                await generateContingencyTable();
            }
        }
        catch (err) {
            setApiStatus(`Could not load cyclone list — ${err.message}`, true);
        }
    }
    void init();
})();
