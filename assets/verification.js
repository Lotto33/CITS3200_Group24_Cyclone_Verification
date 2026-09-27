const API_BASE = "api/v1";
const savedContext = JSON.parse(localStorage.getItem("cycloneVerification") || "null") || {};
const tableInstances = document.getElementById("tableInstances");
const firstInstance = tableInstances.querySelector(".table-instance");
const selects = {
  cyclone: firstInstance.querySelector(".cyclone-select"),
  state: firstInstance.querySelector(".state-select"),
  season: firstInstance.querySelector(".season-select"),
};

const cycloneOptions = [
  { value: "AU202526_34U", label: "Alfred - AU202526_34U" },
  { value: "Cyclone Alfred", label: "Alfred - Cyclone Alfred" },
  { value: "Cyclone Jasper", label: "Jasper - Cyclone Jasper" },
  { value: "Cyclone Ilsa", label: "Ilsa - Cyclone Ilsa" },
];
const stateOptions = ["All states", "Western Australia", "Northern Territory", "Queensland", "New South Wales"];
const seasonOptions = ["All seasons", "2025-26", "2024-25", "2023-24"];

function formatCycloneLabel(name, distId) {
  if (!name) return distId;
  const cleanName = String(name).replace(/^Cyclone\s+/i, "").trim();
  return `${cleanName} - ${distId}`;
}

function populateMultiSelect(select, options, defaultSelections) {
  select.innerHTML = "";
  options.forEach((option) => {
    const value = typeof option === "string" ? option : option.value;
    const label = typeof option === "string" ? option : option.label;
    select.add(new Option(label, value));
  });
  const defaults = Array.isArray(defaultSelections) ? defaultSelections : [defaultSelections];
  Array.from(select.options).forEach((option) => {
    option.selected = defaults.includes(option.value);
  });
}

function getSelectedValues(select) {
  return [...select.selectedOptions].map((option) => option.value).filter(Boolean);
}

function describeSelections(select, allLabel) {
  const values = getSelectedValues(select);
  if (!values.length) return allLabel;
  if (values.includes(allLabel)) return allLabel;
  return values.join(", ");
}

populateMultiSelect(selects.cyclone, cycloneOptions, [savedContext.distId || cycloneOptions[0].value]);
populateMultiSelect(selects.state, stateOptions, ["All states"]);
populateMultiSelect(selects.season, seasonOptions, ["All seasons"]);

function updateContext() {
  const cycloneNames = getSelectedValues(selects.cyclone);
  const selectedCyclones = cycloneNames.length ? cycloneNames.map((value) => {
    const option = cycloneOptions.find((entry) => entry.value === value);
    return option ? option.label : value;
  }) : [cycloneOptions[0].label];
  const stateLabel = describeSelections(selects.state, "All states");
  const seasonLabel = describeSelections(selects.season, "All seasons");
  document.getElementById("context").textContent = `Illustrative contingency table for ${selectedCyclones.join(", ")}; state(s): ${stateLabel}; season(s): ${seasonLabel}; bulletin ${savedContext.bulletin || "—"}.`;
}

Object.values(selects).forEach((select) => select.addEventListener("change", updateContext));
updateContext();

function initializeTabs(instance) {
  const tabButtons = [...instance.querySelectorAll(".tab-button")];
  const tablePanels = [...instance.querySelectorAll(".table-panel")];
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
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      event.preventDefault();
      const offset = event.key === "ArrowRight" ? 1 : -1;
      tabButtons[(index + offset + tabButtons.length) % tabButtons.length].focus();
    });
  });
}

function initializeInstance(instance) {
  const instanceSelects = [
    instance.querySelector(".cyclone-select"),
    instance.querySelector(".state-select"),
    instance.querySelector(".season-select"),
  ];
  populateMultiSelect(instanceSelects[0], cycloneOptions, [savedContext.distId || cycloneOptions[0].value]);
  populateMultiSelect(instanceSelects[1], stateOptions, ["All states"]);
  populateMultiSelect(instanceSelects[2], seasonOptions, ["All seasons"]);
  instanceSelects.forEach((select) => select.addEventListener("change", updateContext));
  initializeTabs(instance);
}

function updateTableControls() {
  const isAtLimit = tableInstances.children.length >= 5;
  const addButton = document.getElementById("addTableBtn");
  addButton.disabled = isAtLimit;
  addButton.setAttribute("aria-label", isAtLimit ? "Maximum of five tables reached" : "Add another verification table");
  tableInstances.querySelectorAll(".remove-instance").forEach((button) => {
    button.disabled = button.closest(".table-instance").dataset.instance === "1";
  });
}

function addTableInstance() {
  if (tableInstances.children.length >= 5) return;
  const instanceNumbers = [...tableInstances.children].map((instance) => Number(instance.dataset.instance));
  const instanceNumber = Math.max(...instanceNumbers) + 1;
  const newInstance = firstInstance.cloneNode(true);
  newInstance.dataset.instance = String(instanceNumber);
  newInstance.querySelector("h2").textContent = `Verification table ${instanceNumber}`;
  newInstance.querySelector(".remove-instance").disabled = false;
  newInstance.querySelectorAll("[id], [for], [aria-controls], [aria-labelledby]").forEach((element) => {
    ["id", "for", "aria-controls", "aria-labelledby"].forEach((attribute) => {
      if (element.hasAttribute(attribute)) {
        element.setAttribute(attribute, element.getAttribute(attribute).replace(/-1\b/g, `-${instanceNumber}`));
      }
    });
  });
  tableInstances.appendChild(newInstance);
  initializeInstance(newInstance);
  updateTableControls();
}

tableInstances.addEventListener("click", (event) => {
  const removeButton = event.target.closest(".remove-instance");
  if (!removeButton || removeButton.disabled) return;
  removeButton.closest(".table-instance").remove();
  updateTableControls();
});
document.getElementById("addTableBtn").addEventListener("click", addTableInstance);
initializeTabs(firstInstance);
updateTableControls();

document.getElementById("resetBtn").addEventListener("click", () => {
  while (tableInstances.children.length > 1) {
    tableInstances.lastElementChild.remove();
  }
  populateMultiSelect(selects.cyclone, cycloneOptions, [savedContext.distId || cycloneOptions[0].value]);
  populateMultiSelect(selects.state, stateOptions, ["All states"]);
  populateMultiSelect(selects.season, seasonOptions, ["All seasons"]);
  const firstTab = firstInstance.querySelector(".tab-button");
  firstInstance.querySelectorAll(".tab-button").forEach((tab, index) => {
    tab.classList.toggle("active", index === 0);
    tab.setAttribute("aria-selected", String(index === 0));
    tab.tabIndex = index === 0 ? 0 : -1;
  });
  firstInstance.querySelectorAll(".table-panel").forEach((panel) => {
    panel.hidden = panel.getAttribute("aria-labelledby") !== firstTab.id;
  });
  document.getElementById("gmlUploadInput").value = "";
  document.getElementById("bestTrackUploadInput").value = "";
  setUploadStatus("");
  updateContext();
  updateTableControls();
});

function setUploadStatus(message, isError = false) {
  const status = document.getElementById("uploadStatus");
  status.textContent = message || "";
  status.classList.toggle("error", Boolean(isError));
}

async function uploadDataset(file, endpoint, label) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  setUploadStatus(`Uploading ${label}…`);
  try {
    const response = await fetch(`${API_BASE}/datasets/${endpoint}`, { method: "POST", body: formData });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `Failed to upload ${label}.`);
    }
    setUploadStatus(`${label} uploaded successfully.`);
  } catch (error) {
    setUploadStatus(error.message || `Could not upload ${label}.`, true);
    throw error;
  }
}

document.getElementById("uploadGmlBtn").addEventListener("click", () => {
  document.getElementById("gmlUploadInput").click();
});
document.getElementById("gmlUploadInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    await uploadDataset(file, "upload", "GML archive");
  } finally {
    event.target.value = "";
  }
});

document.getElementById("uploadBestTrackBtn").addEventListener("click", () => {
  document.getElementById("bestTrackUploadInput").click();
});
document.getElementById("bestTrackUploadInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    await uploadDataset(file, "upload-best-track", "best track CSV");
  } finally {
    event.target.value = "";
  }
});

function csvValue(value) {
  const text = value == null ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

document.getElementById("downloadBestTrackBtn").addEventListener("click", async () => {
  const distId = selects.cyclone.value || savedContext.distId || cycloneOptions[0].value;
  const button = document.getElementById("downloadBestTrackBtn");
  button.disabled = true;
  setUploadStatus("Preparing best track CSV...");
  try {
    const response = await fetch(`${API_BASE}/cyclones/${encodeURIComponent(distId)}/best-track`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not download the best track.");
    const records = Array.isArray(payload) ? payload : (payload.fixes || []);
    const rows = records.map((fix) => ({
      distId: payload.distId || distId,
      fixTime: fix.fixTime,
      longitude: Array.isArray(fix.coord) ? fix.coord[0] : "",
      latitude: Array.isArray(fix.coord) ? fix.coord[1] : "",
      fixType: fix.fixType,
      symbol: fix.symbol,
      category: fix.category,
      timeOffset: fix.timeOffset,
    }));
    const columns = ["distId", "fixTime", "longitude", "latitude", "fixType", "symbol", "category", "timeOffset"];
    const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => csvValue(row[column])).join(","))].join("\r\n");
    const downloadUrl = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${distId}_best_track.csv`;
    link.click();
    URL.revokeObjectURL(downloadUrl);
    setUploadStatus("Best track CSV downloaded.");
  } catch (error) {
    setUploadStatus(error.message || "Could not download the best track.", true);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("backToVisualizer").addEventListener("click", () => {
  window.location.href = "visualize.html";
});
