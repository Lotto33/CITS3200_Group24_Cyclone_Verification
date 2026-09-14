(function () {
  "use strict";

  const CATEGORY_COLORS = {
    "1": "#3ddc84", "2": "#ffd24f", "3": "#ff9f43",
    "4": "#ff5d5d", "5": "#b06bff"
  };
  const DEFAULT_CATEGORY_COLOR = "#8892a6";

  const AREA_STYLE = {
    tcWindArea:     { color: "#8892a6", fillColor: "#8892a6", fillOpacity: 0.12, weight: 1.5, layerKey: "windArea" },
    tcForecastArea: { color: "#ff9f43", fillColor: "#ff9f43", fillOpacity: 0.08, weight: 1.5, layerKey: "forecastArea" },
    tcWarningArea:  { color: "#b06bff", fillColor: "#b06bff", fillOpacity: 0.12, weight: 1.5, layerKey: "warningArea" },
    tcWatchArea:    { color: "#ffe14f", fillColor: "#ffe14f", fillOpacity: 0.10, weight: 1.5, layerKey: "watchArea" },
  };
  const WIND_AREA_COLORS = { Current: "#ff5d5d", Forecast: "#4fa8ff" };

  const els = {
    cyclone: document.getElementById("cycloneSelect"),
    season: document.getElementById("seasonSelect"),
    state: document.getElementById("stateSelect"),
    slider: document.getElementById("bulletinSlider"),
    label: document.getElementById("bulletinLabel"),
    prev: document.getElementById("prevBtn"),
    next: document.getElementById("nextBtn"),
    play: document.getElementById("playBtn"),
    info: document.getElementById("info"),
    status: document.getElementById("status"),
    categoryLegend: document.getElementById("categoryLegend"),
    layers: {
      tracks: document.getElementById("layer-tracks"),
      fixes: document.getElementById("layer-fixes"),
      windArea: document.getElementById("layer-windArea"),
      forecastArea: document.getElementById("layer-forecastArea"),
      warningArea: document.getElementById("layer-warningArea"),
      watchArea: document.getElementById("layer-watchArea"),
      allBulletins: document.getElementById("layer-allBulletins"),
      bestTrack: document.getElementById("layer-bestTrack"),
    },
  };

  Object.entries(CATEGORY_COLORS).forEach(([cat, color]) => {
    const chip = document.createElement("span");
    chip.className = "legend-chip";
    chip.innerHTML = `<span class="swatch" style="background:${color}"></span>Cat ${cat}`;
    els.categoryLegend.appendChild(chip);
  });

  const map = L.map("map", { worldCopyJump: true }).setView([-20, 133], 4);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);

  const bulletinLayer = L.layerGroup().addTo(map);
  const ghostLayer = L.layerGroup().addTo(map);
  const bestTrackLayer = L.layerGroup().addTo(map);

  let index = null;
  let cyclonesById = new Map();
  let currentBulletins = [];
  let currentBestTrack = null;
  let currentIdx = 0;
  let playTimer = null;

  const sidebar = document.getElementById("sidebar");
  const optionsToggle = document.getElementById("optionsToggle");
  const verificationTab = document.getElementById("verificationTab");

  function setSidebarOpen(isOpen) {
    sidebar.hidden = !isOpen;
    optionsToggle.setAttribute("aria-expanded", String(isOpen));
    optionsToggle.innerHTML = isOpen
      ? 'Visualizer Options <span aria-hidden="true">◀</span>'
      : 'Visualizer Options <span aria-hidden="true">▶</span>';
    requestAnimationFrame(() => map.invalidateSize());
  }

  function openVerificationTab() {
    const bulletin = currentBulletins[currentIdx];
    localStorage.setItem("cycloneVerification", JSON.stringify({
      distId: bulletin?.distId || els.cyclone.value,
      distName: bulletin?.distName,
      region: els.state.value || null,
      season: els.season.value || null,
      bulletin: bulletin ? `${currentIdx + 1}/${currentBulletins.length} — ${fmtTime(bulletin.issueTime)}` : null,
    }));
    window.open("verification.html", "cycloneVerification");
  }

  optionsToggle.addEventListener("click", () => setSidebarOpen(sidebar.hidden));
  verificationTab.addEventListener("click", openVerificationTab);
  setSidebarOpen(true);

  function setStatus(msg, isError) {
    els.status.textContent = msg || "";
    els.status.className = isError ? "error" : "";
  }

  function toLatLngs(coords) {
    return coords.map(([lon, lat]) => [lat, lon]);
  }

  function categoryColor(cat) {
    if (!cat) return DEFAULT_CATEGORY_COLOR;
    return CATEGORY_COLORS[String(cat).trim()] || DEFAULT_CATEGORY_COLOR;
  }

  function fmtTime(t) {
    return t ? t.replace("T", " ").replace("Z", " UTC") : "—";
  }

  async function loadIndex() {
    setStatus("Loading index…");
    const res = await fetch("data/index.json");
    if (!res.ok) throw new Error(`Failed to load data/index.json (${res.status})`);
    index = await res.json();
    setStatus("");
    populateCyclones();
  }

  function populateCyclones() {
    cyclonesById = new Map();
    Object.entries(index.regions || {}).forEach(([region, cyclones]) => {
      cyclones.forEach(cyclone => {
        const existing = cyclonesById.get(cyclone.distId) || {
          ...cyclone, regions: [], bulletinCount: 0, hasBestTrack: false,
        };
        existing.regions.push(region);
        existing.bulletinCount += cyclone.bulletinCount || 0;
        existing.hasBestTrack ||= Boolean(cyclone.hasBestTrack);
        if (!existing.distName && cyclone.distName) existing.distName = cyclone.distName;
        if (!existing.firstIssue || (cyclone.firstIssue && cyclone.firstIssue < existing.firstIssue)) {
          existing.firstIssue = cyclone.firstIssue;
        }
        if (!existing.lastIssue || (cyclone.lastIssue && cyclone.lastIssue > existing.lastIssue)) {
          existing.lastIssue = cyclone.lastIssue;
        }
        cyclonesById.set(cyclone.distId, existing);
      });
    });

    const allCyclones = Array.from(cyclonesById.values());
    const seasons = [...new Set(allCyclones.map(c => c.firstIssue ? c.firstIssue.slice(0, 4) : "").filter(Boolean))].sort();
    const regions = [...new Set(allCyclones.flatMap(c => c.regions))].sort();
    const selectedSeason = els.season.value;
    const selectedState = els.state.value;
    els.season.replaceChildren(new Option("All seasons", ""), ...seasons.map(season => new Option(season, season)));
    els.state.replaceChildren(new Option("All states", ""), ...regions.map(region => new Option(region, region)));
    els.season.value = seasons.includes(selectedSeason) ? selectedSeason : "";
    els.state.value = regions.includes(selectedState) ? selectedState : "";

    const cyclones = allCyclones
      .filter(c => (!els.season.value || (c.firstIssue || "").startsWith(els.season.value))
        && (!els.state.value || c.regions.includes(els.state.value)))
      .sort((a, b) => (a.firstIssue || "").localeCompare(b.firstIssue || ""));
    const selectedId = els.cyclone.value;
    els.cyclone.replaceChildren(...cyclones.map(c => {
      const label = `${c.distName || c.distId} — ${c.distId} (${c.bulletinCount} bulletins, ${c.firstIssue ? c.firstIssue.slice(0,10) : "?"})${c.hasBestTrack ? " ★" : ""}`;
      return new Option(label, c.distId);
    }));
    if (cyclones.length) {
      els.cyclone.value = cyclones.some(c => c.distId === selectedId) ? selectedId : cyclones[0].distId;
      loadCyclone();
    } else {
      els.cyclone.replaceChildren(new Option("No cyclones match these filters", ""));
      currentBulletins = [];
      renderBulletin();
    }
  }

  async function loadCyclone() {
    stopPlay();
    const distId = els.cyclone.value;
    if (!distId) { currentBulletins = []; renderBulletin(); return; }
    const cyclone = cyclonesById.get(distId);
    const regions = cyclone ? cyclone.regions : [];
    setStatus(`Loading ${distId} across ${regions.length} data source${regions.length === 1 ? "" : "s"}…`);
    try {
      const results = await Promise.all(regions.map(async region => {
        const path = `data/${encodeURIComponent(region)}/${encodeURIComponent(distId)}.json`;
        const res = await fetch(path);
        if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
        return res.json();
      }));
      currentBulletins = results.flat().sort((a, b) =>
        (a.issueTime || "").localeCompare(b.issueTime || "") ||
        (a.source || "").localeCompare(b.source || "")
      );
      setStatus("");
    } catch (err) {
      currentBulletins = [];
      setStatus(`Could not load data (are you running a local server? see README) — ${err.message}`, true);
    }
    currentBestTrack = null;
    try {
      const btRes = await fetch(`data/best_track/${distId}.json`);
      if (btRes.ok) currentBestTrack = await btRes.json();
    } catch (err) {
      currentBestTrack = null;
    }
    currentIdx = 0;
    els.slider.min = 0;
    els.slider.max = Math.max(0, currentBulletins.length - 1);
    els.slider.value = 0;
    renderBulletin(true);
  }

  function drawGhostTrails() {
    ghostLayer.clearLayers();
    if (!els.layers.allBulletins.checked) return;
    currentBulletins.forEach((b, i) => {
      (b.tracks || []).forEach(track => {
        if (track.coords.length < 2) return;
        L.polyline(toLatLngs(track.coords), {
          color: i === currentIdx ? "transparent" : "#8892a6",
          weight: 1, opacity: 0.35, dashArray: track.trackType === "Observed" ? "3,4" : null,
        }).addTo(ghostLayer);
      });
    });
  }

  function drawBestTrack(bounds) {
    bestTrackLayer.clearLayers();
    if (!els.layers.bestTrack.checked || !currentBestTrack) return;
    const points = currentBestTrack.points || [];
    if (points.length < 2) return;
    const latlngs = points.map(p => [p.coord[1], p.coord[0]]);
    L.polyline(latlngs, { color: "#2fd4d9", weight: 3, opacity: 0.9 })
      .bindPopup(`<b>Best track</b>${currentBestTrack.name ? ` — ${currentBestTrack.name}` : ""}<br>
        ${points.length} points, ${fmtTime(points[0].time)} → ${fmtTime(points[points.length - 1].time)}`)
      .addTo(bestTrackLayer);
    points.forEach(p => {
      const [lon, lat] = p.coord;
      L.circleMarker([lat, lon], {
        radius: 3, color: "#111826", weight: 1, fillColor: "#2fd4d9", fillOpacity: 0.95,
      }).bindPopup(`<b>Best track fix</b><br>
        Time: ${fmtTime(p.time)}<br>Pressure: ${p.pressure ?? "—"} hPa<br>
        Max wind: ${p.windSpeed ?? "—"} kn`).addTo(bestTrackLayer);
    });
    bounds.push(...latlngs);
  }

  function renderBulletin(fitBounds) {
    bulletinLayer.clearLayers();
    drawGhostTrails();
    const b = currentBulletins[currentIdx];
    if (!b) {
      els.label.textContent = "No bulletins available.";
      els.info.textContent = "Select a cyclone to begin.";
      els.prev.disabled = els.next.disabled = true;
      drawBestTrack([]);
      return;
    }
    els.prev.disabled = currentIdx === 0;
    els.next.disabled = currentIdx === currentBulletins.length - 1;
    els.slider.value = currentIdx;
    els.label.innerHTML = `Bulletin <b>${currentIdx + 1}/${currentBulletins.length}</b> — issued ${fmtTime(b.issueTime)}`;
    els.info.innerHTML = `<b>${b.distName || ""}</b> (${b.distId})<br>
      Source: ${b.source}<br>Forecast base time: ${fmtTime(b.fcastTime)}<br>
      Issue time: ${fmtTime(b.issueTime)}<br>Expiry: ${b.expiryHrs || "?"} hrs<br>
      Tracks: ${b.tracks.length}, Fixes: ${b.fixes.length}, Areas: ${b.areas.length}<br>
      Best track: ${currentBestTrack ? `${currentBestTrack.points.length} points (post-event)` : "not available"}`;

    const bounds = [];
    if (els.layers.tracks.checked) {
      b.tracks.forEach(track => {
        if (track.coords.length < 2) return;
        const latlngs = toLatLngs(track.coords);
        L.polyline(latlngs, {
          color: track.trackType === "Forecast" ? "#4fa8ff" : "#ffd24f",
          weight: 3, opacity: 0.9, dashArray: track.trackType === "Observed" ? "6,5" : null,
        }).bindPopup(`<b>${track.trackType || "Track"}</b><br>${fmtTime(track.startTime)} → ${fmtTime(track.endTime)}`)
          .addTo(bulletinLayer);
        bounds.push(...latlngs);
      });
    }
    if (els.layers.fixes.checked) {
      b.fixes.forEach(fix => {
        const [lon, lat] = fix.coord;
        const marker = L.circleMarker([lat, lon], {
          radius: fix.fixType === "Current" ? 8 : 6, color: "#111826", weight: 1.5,
          fillColor: categoryColor(fix.category), fillOpacity: 0.95,
        }).bindPopup(`<b>${fix.fixType || "Fix"}</b> (${fix.symbol || "?"})<br>
          Category: ${fix.category ?? "—"}<br>Time: ${fmtTime(fix.fixTime)}<br>
          Offset: ${fix.timeOffset ?? "0"}h`);
        marker.addTo(bulletinLayer);
        bounds.push([lat, lon]);
      });
    }
    (b.areas || []).forEach(area => {
      const baseStyle = AREA_STYLE[area.kind];
      const windAreaColor = area.kind === "tcWindArea" ? WIND_AREA_COLORS[area.fixType] : null;
      const style = windAreaColor ? { ...baseStyle, color: windAreaColor, fillColor: windAreaColor } : baseStyle;
      if (!style || !els.layers[style.layerKey].checked) return;
      const popup = `<b>${area.kind}</b><br>
        ${area.areaType ? `Area type: ${area.areaType}<br>` : ""}
        ${area.extent ? `Extent: ${area.extent}<br>` : ""}
        ${area.windType ? `Wind type: ${area.windType}<br>` : ""}
        ${area.marineType ? `Marine type: ${area.marineType}<br>` : ""}
        ${area.fixType ? `Fix type: ${area.fixType}<br>` : ""}
        ${area.fixTime ? `Fix time: ${fmtTime(area.fixTime)}` : ""}`;
      area.polygons.forEach(rings => {
        const latlngRings = rings.map(toLatLngs);
        L.polygon(latlngRings, {
          color: style.color, fillColor: style.fillColor, fillOpacity: style.fillOpacity,
          weight: style.weight, smoothFactor: 0,
        }).bindPopup(popup).addTo(bulletinLayer);
        latlngRings.forEach(ring => bounds.push(...ring));
      });
    });
    drawBestTrack(bounds);
    if (fitBounds && bounds.length) map.fitBounds(L.latLngBounds(bounds), { padding: [30, 30], maxZoom: 9 });
  }

  function stopPlay() {
    if (playTimer) { clearInterval(playTimer); playTimer = null; els.play.textContent = "⏵"; }
  }

  function togglePlay() {
    if (playTimer) { stopPlay(); return; }
    if (!currentBulletins.length) return;
    els.play.textContent = "⏸";
    playTimer = setInterval(() => {
      if (currentIdx >= currentBulletins.length - 1) { stopPlay(); return; }
      currentIdx += 1;
      renderBulletin(false);
    }, 700);
  }

  els.cyclone.addEventListener("change", loadCyclone);
  els.season.addEventListener("change", populateCyclones);
  els.state.addEventListener("change", populateCyclones);
  els.slider.addEventListener("input", () => {
    stopPlay(); currentIdx = Number(els.slider.value); renderBulletin(false);
  });
  els.prev.addEventListener("click", () => { stopPlay(); if (currentIdx > 0) { currentIdx--; renderBulletin(false); } });
  els.next.addEventListener("click", () => { stopPlay(); if (currentIdx < currentBulletins.length - 1) { currentIdx++; renderBulletin(false); } });
  els.play.addEventListener("click", togglePlay);
  Object.values(els.layers).forEach(cb => cb.addEventListener("change", () => renderBulletin(false)));
  loadIndex().catch(err => setStatus(err.message, true));
})();
